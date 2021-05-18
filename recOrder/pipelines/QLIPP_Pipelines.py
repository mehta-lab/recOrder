from recOrder.io.config_reader import ConfigReader
from waveorder.io.reader import MicromanagerReader
from waveorder.io.writer import WaveorderWriter
from recOrder.io.utils import load_bg
from waveorder.util import wavelet_softThreshold
from recOrder.compute.QLIPP_compute import *
from recOrder.postproc.post_processing import *
import json
import numpy as np
import time


class qlipp_3D_pipeline:
    """
    This class contains methods to reconstruct an entire dataset alongside pre/post-processing
    """

    def __init__(self, config, data: MicromanagerReader, sample: str):
        """
        Parameters
        ----------
        config:     (Object) initialized ConfigReader object
        data:       (Object) initialized MicromanagerReader object (data should be extracted already)
        sample:     (str) name of the sample to pass for naming of folders, etc.
        """

        self.config = config
        self.data = data

        #TODO: Parse if bg_ROI matches the data size
        self.calib_meta = json.load(open(self.config.calibration_metadata))
        self.sample = sample

        #TODO: Parse positions if not 'all', parse timepoints if not 'all'
        self.pos = data.get_num_positions() if self.config.positions == 'all' else NotImplementedError
        self.t = data.frames if self.config.timepoints == 'all' else NotImplementedError

        self.channels = self.config.output_channels
        self.chan_names = self.data.channel_names
        self.bg_path = self.config.background
        self.bg_roi = self.config.background_ROI
        self.bg_correction = self.config.background_correction
        self.img_dim = (self.data.height, self.data.width, self.data.slices)
        self.s0_idx, self.s1_idx, self.s2_idx, self.s3_idx, self.fluor_idxs = self.parse_channel_idx(self.chan_names)

        if self.data.channels < 4:
            raise ValueError(f'Number of Channels is {data.channels}, cannot be less than 4')

        bg_data = load_bg(self.bg_path, self.img_dim[0], self.img_dim[1], self.bg_roi)

        #TODO: read step size from metadata
        self.reconstructor = initialize_reconstructor((self.img_dim[0], self.img_dim[1]), self.config.wavelength,
                                                 self.calib_meta['Summary']['~ Swing (fraction)'],
                                                 len(self.calib_meta['Summary']['ChNames']),
                                                 self.config.NA_objective, self.config.NA_condenser,
                                                 self.config.magnification, self.img_dim[2], self.config.z_step,
                                                 self.config.pad_z, self.config.pixel_size,
                                                 self.config.background_correction, self.config.n_objective_media,
                                                 self.config.use_gpu, self.config.gpu_id)

        #TODO: Add check to make sure that State0..4 are the first 4 channels
        self.bg_stokes = self.reconstructor.Stokes_recon(bg_data)
        self.bg_stokes = self.reconstructor.Stokes_transform(self.bg_stokes)

        self.data_shape = (self.t, len(self.channels), self.img_dim[2], self.img_dim[0], self.img_dim[1])
        self.chunk_size = (1, 1, 1, self.img_dim[0], self.img_dim[1])

        self.writer = WaveorderWriter(self.config.processed_dir, 'physical')
        self.writer.create_zarr_root(f'{self.sample}.zarr')
        self.writer.store.attrs.put(self.config.yaml_config)

    def reconstruct_all(self):
        """
        This method will loop through every position/timepoint specified in config.

        Returns
        -------

        """

        print(f'Beginning Reconstruction...')
        #TODO: write fluorescence data from remaining channels, need to get their c_idx
        for pos in range(self.pos):

            self.writer.create_position(pos)
            self.writer.init_array(self.data_shape, self.chunk_size, self.channels)

            if pos != 0:
                pos_tot_time = (pos_end_time-pos_start_time)/60
                total_time = pos_tot_time*self.pos
                remaining_time = total_time - pos*pos_tot_time
                print(f'Estimated Time Remaining: {np.round(remaining_time,0):0.0f} min')

            pos_start_time = time.time()

            position_data = self.data.get_array(pos)

            for t in range(self.t):

                print(f'Reconstructing Position {pos}, Time {t}')
                time_start_time = time.time()

                # PERFORM RECONSTRUCTION
                self.reconstruct_z_stack(position_data, t)

                time_end_time = time.time()
                print(f'Finished Reconstructing Position {pos}, Time {t} '
                      f'({(time_end_time - time_start_time) / 60:0.1f} min)')

            pos_end_time = time.time()

    def reconstruct_z_stack(self, position_data, t):
        """
        This method performs reconstruction / pre / post processing for a single z-stack.

        Parameters
        ----------
        position_data:      (np.array) np.array of dimension (T, C, Z, Y, X)
        t:                  (int) index of the time-point to pull from position_data

        Returns
        -------
        written data to the processed directory specified in the config

        """

        ###### ADD PRE-PROCESSING ######

        # Add pre-proc denoising
        if self.config.preproc_denoise_use:
            stokes = reconstruct_QLIPP_stokes(position_data[t], self.reconstructor, self.bg_stokes)
            stokes = self.preproc_denoise(stokes)
            recon_data = self.bire_from_stokes(stokes)

        if not self.config.preproc_denoise_use:
            recon_data = reconstruct_QLIPP_birefringence(position_data[t], self.reconstructor, self.bg_stokes)

        if 'Phase3D' in self.channels:
            phase3D = self.reconstructor.Phase_recon_3D(np.transpose(recon_data[2], (1, 2, 0)),
                                                   method=self.config.phase_denoiser_3D,
                                                   reg_re=self.config.Tik_reg_ph_3D, rho=self.config.rho_3D,
                                                   lambda_re=self.config.TV_reg_ph_3D, itr=self.config.itr_3D,
                                                   verbose=False)

        if self.config.postproc_registration_use:
            registered_stacks = []
            for idx in self.config.postproc_registration_channel_idx:
                registered_stacks.append(translate_3D(position_data[t, idx],
                                                              self.config.postproc_registration_shift))

        #TODO: ASSIGN CHANNELS INDEX UPON INIT?
        #TODO: FIGURE OUT HOW TO WRITE FLUOR CHANNELS IN CORRECT ORDER
        fluor_idx = 0
        for chan in range(len(self.channels)):
            if 'Retardance' in self.channels[chan]:
                ret = recon_data[0] / (2 * np.pi) * self.config.wavelength
                self.writer.write(ret, t=t, c=chan)
            elif 'Orientation' in self.channels[chan]:
                self.writer.write(recon_data[1], t=t, c=chan)
            elif 'Brightfield' in self.channels[chan]:
                self.writer.write(recon_data[2], t=t, c=chan)
            elif 'Phase3D' in self.channels[chan]:
                self.writer.write(np.transpose(phase3D, (2,0,1)), t=t, c=chan)
            else:
                if self.config.postproc_registration_use:
                    self.writer.write(registered_stacks[fluor_idx], t=t, c=chan)
                    fluor_idx += 1
                else:
                  raise NotImplementedError(f'{self.channels[chan]} not available to write yet')

    def preproc_denoise(self, stokes):
        """
        This method performs pre-processing denoising on specified stokes channels

        Parameters
        ----------
        stokes:         (np.array) Stokes data of format (Z, C, Y, X)

        Returns
        -------
        stokes_denoised:    (np.array) denoised stokes data of format (Z, C, Y, X)

        """

        params = []

        for i in range(len(self.config.preproc_denoise_channels)):
            threshold = 0.1 if self.config.preproc_denoise_thresholds is None \
                else self.config.preproc_denoise_thresholds[i]
            level = 1 if self.config.preproc_denoise_levels is None \
                else self.config.preproc_denoise_levels[i]

            params.append([self.config.preproc_denoise_channels[i], threshold, level])

        stokes_denoised = np.copy(stokes)
        for chan in range(len(params)):

            if 'S0' in params[chan][0]:
                for z in range(len(stokes)):
                    stokes_denoised[z, 0, :, :] = wavelet_softThreshold(stokes[z, 0, :, :], 'db8',
                                                                        params[chan][1], params[chan][2])
            elif 'S1' in params[chan][0]:
                for z in range(len(stokes)):
                    stokes_denoised[z, 1, :, :] = wavelet_softThreshold(stokes[z, 1, :, :], 'db8',
                                                                        params[chan][1], params[chan][2])
            if 'S2' in params[chan][0]:
                for z in range(len(stokes)):
                    stokes_denoised[z, 2, :, :] = wavelet_softThreshold(stokes[z, 2, :, :], 'db8',
                                                                        params[chan][1], params[chan][2])

            if 'S3' in params[chan][0]:
                for z in range(len(stokes)):
                    stokes_denoised[z, 3, :, :] = wavelet_softThreshold(stokes[z, 3, :, :], 'db8',
                                                                        params[chan][1], params[chan][2])

        return stokes_denoised

    def bire_from_stokes(self, stokes):

        """
        quick method to calculate the birefringence from provided stokes.  Used after pre-proc denoising

        Parameters
        ----------
        stokes:         (np.array) Stokes data of format (Z, C, Y, X)

        Returns
        -------
        recon_data:     (np.array) reconstructed z-stack of dimensions (C, Z, Y, X).
                                    channels in order are [Retardance, Orientation, BF, Polarization]

        """

        recon_data = np.zeros([stokes.shape[0], 4, stokes.shape[-2], stokes.shape[-1]])
        for z in range(len(stokes)):

            recon_data[z, :, :, :] = self.reconstructor.Polarization_recon(stokes[z])

        return np.transpose(recon_data, (1,0,2,3))

    #TODO: name fluor channels based off metadata name?
    def parse_channel_idx(self, channel_list):
        fluor_idx = []
        for channel in range(len(channel_list)):
            if 'State0' in channel_list[channel]:
                s0_idx = channel
            elif 'State1' in channel_list[channel]:
                s1_idx = channel
            elif 'State2' in channel_list[channel]:
                s2_idx = channel
            elif 'State3' in channel_list[channel]:
                s3_idx = channel
            else:
                fluor_idx.append(channel)

        return s0_idx, s1_idx, s2_idx, s3_idx, fluor_idx


