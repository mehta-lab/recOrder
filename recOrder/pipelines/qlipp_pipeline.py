from recOrder.io.config_reader import ConfigReader
from waveorder.io.reader import MicromanagerReader
from waveorder.io.writer import WaveorderWriter
from recOrder.io.utils import load_bg
from recOrder.compute.qlipp_compute import reconstruct_qlipp_birefringence, reconstruct_qlipp_stokes, \
    reconstruct_qlipp_phase2D, reconstruct_qlipp_phase3D, initialize_reconstructor
import json
import numpy as np
from recOrder.pipelines.pipeline_interface import PipelineInterface


class qlipp_pipeline(PipelineInterface):

    """
    This class contains methods to reconstruct an entire dataset alongside pre/post-processing
    """

    def __init__(self, config: ConfigReader, data: MicromanagerReader, save_dir: str, name: str, mode: str, num_t: int):
        """
        Parameters
        ----------
        config:     (Object) initialized ConfigReader object
        data:       (Object) initialized MicromanagerReader object (data should be extracted already)
        save_dir:   (str) save directory
        name:       (str) name of the sample to pass for naming of folders, etc.
        mode:       (str) mode of operation, can be '2D', '3D', or 'stokes'
        """

        # Dataset Parameters
        self.config = config
        self.data = data
        self.name = name
        self.mode = mode
        self.save_dir = save_dir

        # Dimension Parameters
        self.t = num_t
        self.output_channels = self.config.output_channels
        self._check_output_channels(self.output_channels)

        if self.data.channels < 4:
            raise ValueError(f'Number of Channels is {data.channels}, cannot be less than 4')

        self.slices = self.data.slices
        self.focus_slice = None
        if self.mode == '2D':
            self.slices = 1
            self.focus_slice = self.config.focus_zidx

        self.img_dim = (self.data.height, self.data.width, self.data.slices)

        # Metadata
        self.chan_names = self.data.channel_names
        self.calib_meta = json.load(open(self.config.calibration_metadata)) \
            if self.config.calibration_metadata else None
        #todo: re-structure reading calib metadata when finalized
        self.calib_scheme = self.calib_meta['Summary']['~ Acquired Using'] if self.calib_meta \
            else '4-Frame Extinction'
        self.bg_path = self.config.background if self.config.background else None
        #todo: fix typo
        self.bg_roi = self.calib_meta['Summary']['ROI Used (x, y, width, height)'] if self.calib_meta else None

        # identify the image indicies corresponding to each polarization orientation
        self.s0_idx, self.s1_idx, \
        self.s2_idx, self.s3_idx, \
        self.s4_idx, self.fluor_idxs = self.parse_channel_idx(self.data.channel_names)

        # Writer Parameters
        self._file_writer = None
        self.data_shape = (self.t, len(self.output_channels), self.slices, self.img_dim[0], self.img_dim[1])
        self.chunk_size = (1, 1, 1, self.img_dim[0], self.img_dim[1])

        self.writer = WaveorderWriter(self.save_dir, 'physical')
        self.writer.create_zarr_root(f'{self.name}.zarr')
        self.writer.store.attrs.put(self.config.yaml_dict)

        # Initialize Reconstructor
        self.reconstructor = initialize_reconstructor((self.img_dim[0], self.img_dim[1]), self.config.wavelength,
                                                 self.calib_meta['Summary']['~ Swing (fraction)'],
                                                 len(self.calib_meta['Summary']['ChNames']),
                                                 self.config.qlipp_birefringence_only,
                                                 self.config.NA_objective, self.config.NA_condenser,
                                                 self.config.magnification, self.data.slices, self.data.z_step_size,
                                                 self.config.pad_z, self.config.pixel_size,
                                                 self.config.background_correction, self.config.n_objective_media,
                                                 self.mode, self.config.use_gpu, self.config.gpu_id)

        # Compute BG stokes if necessary
        if self.config.background_correction != None:
            bg_data = load_bg(self.bg_path, self.img_dim[0], self.img_dim[1], self.bg_roi)
            self.bg_stokes = self.reconstructor.Stokes_recon(bg_data)
            self.bg_stokes = self.reconstructor.Stokes_transform(self.bg_stokes)

    def _check_output_channels(self, output_channels):
        self.no_birefringence = True
        for channel in output_channels:
            if 'Retardance' in channel or 'Orientation' in channel or 'Brightfield' in channel:
                self.no_birefringence = False
            else:
                continue

    def reconstruct_stokes_volume(self, data):
        """
        This method reconstructs a stokes volume from raw data

        Parameters
        ----------
        data:           (nd-array) raw data volume at certain position, time.
                                  dimensions must be (C, Z, Y, X)

        Returns
        -------
        stokes:         (nd-array) stokes volume of dimensions (Z, 5, Y, X)
                                    where C is the stokes channels (S0..S3 + DOP)

        """

        if self.calib_scheme == '4-Frame Extinction':
            LF_array = np.zeros([4, self.data.slices, self.data.height, self.data.width])

            LF_array[0] = data[self.s0_idx]
            LF_array[1] = data[self.s1_idx]
            LF_array[2] = data[self.s2_idx]
            LF_array[3] = data[self.s3_idx]

        elif self.calib_scheme == '5-Frame':
            LF_array = np.zeros([5, self.data.slices, self.data.height, self.data.width])
            LF_array[0] = data[self.s0_idx]
            LF_array[1] = data[self.s1_idx]
            LF_array[2] = data[self.s2_idx]
            LF_array[3] = data[self.s3_idx]
            LF_array[3] = data[self.s4_idx]

        else:
            raise NotImplementedError(f"calibration scheme {self.calib_scheme} not implemented")

        stokes = reconstruct_qlipp_stokes(LF_array, self.reconstructor, self.bg_stokes)

        return stokes

    def reconstruct_phase_volume(self, stokes):
        """
        This method reconstructs a phase volume or 2D phase image given stokes stack

        Parameters
        ----------
        stokes:             (nd-array) stokes stack of (Z, C, Y, X) where C = stokes channel

        Returns
        -------
        phase3D:            (nd-array) 3D phase stack of (Z, Y, X)

        or

        phase2D:            (nd-array) 2D phase image of (Y, X)

        """
        phase2D = None
        phase3D = None

        if 'Phase3D' in self.output_channels:
            phase3D = reconstruct_qlipp_phase3D(np.transpose(stokes[:, 0], (1, 2, 0)),self.reconstructor,
                                                method=self.config.phase_denoiser_3D,
                                                reg_re=self.config.Tik_reg_ph_3D, rho=self.config.rho_3D,
                                                lambda_re=self.config.TV_reg_ph_3D, itr=self.config.itr_3D)

        if 'Phase2D' in self.output_channels:
            phase2D = reconstruct_qlipp_phase2D(np.transpose(stokes[:, 0], (1, 2, 0)), self.reconstructor,
                                                method=self.config.phase_denoiser_2D, reg_p=self.config.Tik_reg_ph_2D,
                                                rho=self.config.rho_2D, lambda_p=self.config.TV_reg_ph_2D,
                                                itr=self.config.itr_2D)


        return phase2D, phase3D

    def reconstruct_birefringence_volume(self, stokes):
        """
        This method reconstructs birefringence (Ret, Ori, BF, Pol)
        for given stokes

        Parameters
        ----------
        stokes:             (nd-array) stokes stack of (Z, C, Y, X) where C = stokes channel

        Returns
        -------
        birefringence:       (nd-array) birefringence stack of (C, Z, Y, X)
                                        where C = Retardance, Orientation, BF, Polarization

        """

        if self.no_birefringence:
            return None
        else:
            birefringence = reconstruct_qlipp_birefringence(stokes[slice(None) if self.slices != 1 else self.focus_slice],
                                                            self.reconstructor)
            return birefringence

    # todo: think about better way to write fluor/registered data?
    def write_data(self, pt, pt_data, stokes, birefringence, phase2D, phase3D, registered_stacks):

        t = pt[1]
        z = 0 if self.mode == '2D' else None
        _slice = self.focus_slice if self.mode == '2D' else slice(None)
        fluor_idx = 0

        for chan in range(len(self.output_channels)):
            if 'Retardance' in self.output_channels[chan]:
                ret = birefringence[0, _slice] / (2 * np.pi) * self.config.wavelength
                self.writer.write(ret, t=t, c=chan, z=z)
            elif 'Orientation' in self.output_channels[chan]:
                self.writer.write(birefringence[1, _slice], t=t, c=chan, z=z)
            elif 'Brightfield' in self.output_channels[chan]:
                self.writer.write(birefringence[2, _slice], t=t, c=chan, z=z)
            elif 'Phase3D' in self.output_channels[chan]:
                self.writer.write(phase3D, t=t, c=chan, z=z)
            elif 'Phase2D' in self.output_channels:
                self.writer.write(phase2D, t=t, c=chan, z=z)
            elif 'S0' in self.output_channels[chan]:
                self.writer.write(stokes[_slice, 0], t=t, c=chan, z=z)
            elif 'S1' in self.output_channels[chan]:
                self.writer.write(stokes[_slice, 1], t=t, c=chan, z=z)
            elif 'S2' in self.output_channels[chan]:
                self.writer.write(stokes[_slice, 2], t=t, c=chan, z=z)
            elif 'S3' in self.output_channels[chan]:
                self.writer.write(stokes[_slice, 3], t=t, c=chan, z=z)

            # Assume any other output channel in config is fluorescence
            else:
                if self.config.postprocessing.registration_use:
                    self.writer.write(registered_stacks[fluor_idx], t=t, c=chan, z=z)
                    fluor_idx += 1
                else:
                    self.writer.write(pt_data[self.fluor_idxs[fluor_idx]], t=t, c=chan, z=z)
                    fluor_idx += 1

    @property
    def writer(self):
        return self._file_writer

    @writer.setter
    def writer(self, writer_object: WaveorderWriter):
        self._file_writer = writer_object

    def parse_channel_idx(self, channel_list):
        fluor_idx = []
        s4_idx = None
        try:
            self.calib_meta['Summary']['PolScope_Plugin_Version']
            open_pol = True
        except:
            open_pol = False

        for channel in range(len(channel_list)):
            if 'State0' in channel_list[channel]:
                s0_idx = channel
            elif 'State1' in channel_list[channel]:
                s1_idx = channel
            elif 'State2' in channel_list[channel]:
                s2_idx = channel
            elif 'State3' in channel_list[channel]:
                s3_idx = channel
            elif 'State4' in channel_list[channel]:
                s4_idx = channel
            else:
                fluor_idx.append(channel)

        if open_pol:
            s1_idx, s2_idx, s3_idx, s4_idx = s4_idx, s3_idx, s1_idx, s2_idx

        return s0_idx, s1_idx, s2_idx, s3_idx, s4_idx, fluor_idx


