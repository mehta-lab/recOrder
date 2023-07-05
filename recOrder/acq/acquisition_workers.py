# TODO: remove in Python 3.11
from __future__ import annotations

from qtpy.QtCore import Signal
from iohub import open_ome_zarr
from iohub.convert import TIFFConverter
from recOrder.cli import settings
from recOrder.cli.compute_transfer_function import (
    compute_transfer_function_cli,
)
from recOrder.cli.apply_inverse_transfer_function import (
    apply_inverse_transfer_function_cli,
)
from recOrder.acq.acq_functions import (
    generate_acq_settings,
    acquire_from_settings,
)
from recOrder.io.utils import model_to_yaml
from recOrder.io.utils import ram_message
from napari.qt.threading import WorkerBaseSignals, WorkerBase
from napari.utils.notifications import show_warning
import logging
import numpy as np
import os
import shutil

# type hint/check
from typing import TYPE_CHECKING

# avoid runtime import error
if TYPE_CHECKING:
    from recOrder.plugin.main_widget import MainWidget
    from recOrder.calib.Calibration import QLIPP_Calibration


def _generate_reconstruction_config_from_gui(
    reconstruction_config_path,
    mode,
    calib_window,
    input_channel_names,
):
    if mode == "birefringence" or "all":
        if calib_window.bg_option == "None":
            background_path = ""
            remove_estimated_background = False
        elif calib_window.bg_option == "Measured":
            background_path = calib_window.acq_bg_directory
            remove_estimated_background = False
        elif calib_window.bg_option == "Estimated":
            background_path = ""
            remove_estimated_background = True
        elif calib_window.bg_option == "Measured + Estimated":
            background_path = calib_window.acq_bg_directory
            remove_estimated_background = True

        birefringence_transfer_function_settings = (
            settings.BirefringenceTransferFunctionSettings(
                wavelength_illumination=calib_window.recon_wavelength / 1000,
                swing=calib_window.swing,
                scheme=calib_window.calib_scheme,
            )
        )
        birefringence_apply_inverse_settings = (
            settings.BirefringenceApplyInverseSettings(
                background_path=background_path,
                remove_estimated_background=remove_estimated_background,
            )
        )
        birefringence_settings = settings.BirefringenceSettings(
            birefringence_transfer_function_settings=birefringence_transfer_function_settings,
            birefringence_apply_inverse_settings=birefringence_apply_inverse_settings,
        )
    else:
        birefringence_settings = None

    if mode == "phase" or "all":
        phase_transfer_function_settings = (
            settings.PhaseTransferFunctionSettings(
                yx_pixel_size=calib_window.ps / calib_window.mag,
                z_pixel_size=calib_window.z_step,
                z_padding=calib_window.pad_z,
                index_of_refraction_media=calib_window.n_media,
                numerical_aperture_illumination=calib_window.cond_na,
                numerical_aperture_detection=calib_window.obj_na,
            )
        )
        phase_apply_inverse_settings = settings._PhaseApplyInverseSettings(
            reconstruction_algorithm=calib_window.phase_regularizer,
            strength=calib_window.ui.le_phase_strength.text(),
            TV_rho_strength=calib_window.ui.le_rho.text(),
            TV_iterations=calib_window.ui.le_itr.text(),
        )
        phase_settings = settings.PhaseSettings(
            phase_transfer_function_settings=phase_transfer_function_settings,
            phase_apply_inverse_settings=phase_apply_inverse_settings,
        )
    else:
        phase_settings = None

    reconstruction_settings = settings.ReconstructionSettings(
        input_channel_names=input_channel_names,
        reconstruction_dimension=str(calib_window.acq_mode[0]),
        birefringence=birefringence_settings,
        phase=phase_settings,
    )

    model_to_yaml(reconstruction_settings, reconstruction_config_path)


class PolarizationAcquisitionSignals(WorkerBaseSignals):
    """
    Custom Signals class that includes napari native signals
    """

    phase_image_emitter = Signal(object)
    bire_image_emitter = Signal(object)
    phase_reconstructor_emitter = Signal(object)
    aborted = Signal()


class BFAcquisitionSignals(WorkerBaseSignals):
    """
    Custom Signals class that includes napari native signals
    """

    phase_image_emitter = Signal(object)
    phase_reconstructor_emitter = Signal(object)
    aborted = Signal()


class ListeningSignals(WorkerBaseSignals):
    """
    Custom Signals class that includes napari native signals
    """

    store_emitter = Signal(object)
    dim_emitter = Signal(tuple)
    aborted = Signal()


class BFAcquisitionWorker(WorkerBase):
    """
    Class to execute a brightfield acquisition.  First step is to snap the images follow by a second
    step of reconstructing those images.
    """

    def __init__(self, calib_window: MainWidget):
        super().__init__(SignalsClass=BFAcquisitionSignals)

        # Save current state of GUI window
        self.calib_window = calib_window

        # Init Properties
        self.prefix = "recOrderPluginSnap"
        self.dm = self.calib_window.mm.displays()
        self.dim = (
            "2D"
            if self.calib_window.ui.cb_acq_mode.currentIndex() == 0
            else "3D"
        )
        self.img_dim = None

        save_dir = (
            self.calib_window.save_directory
            if self.calib_window.save_directory
            else self.calib_window.directory
        )

        if save_dir is None:
            raise ValueError(
                "save directory is empty, please specify a directory in the plugin"
            )

        # increment filename one more than last found saved snap
        i = 0
        prefix = self.calib_window.save_name
        snap_dir = (
            f"recOrderPluginSnap_{i}"
            if not prefix
            else f"{prefix}_recOrderPluginSnap_{i}"
        )
        while os.path.exists(os.path.join(save_dir, snap_dir)):
            i += 1
            snap_dir = (
                f"recOrderPluginSnap_{i}"
                if not prefix
                else f"{prefix}_recOrderPluginSnap_{i}"
            )

        self.snap_dir = os.path.join(save_dir, snap_dir)
        os.mkdir(self.snap_dir)

    def _check_abort(self):
        if self.abort_requested:
            self.aborted.emit()
            raise TimeoutError("Stop Requested")

    def _check_ram(self):
        """
        Show a warning if RAM < 32 GB.
        """
        is_warning, msg = ram_message()
        if is_warning:
            show_warning(msg)
        else:
            logging.info(msg)

    def work(self):
        """
        Function that runs the 2D or 3D acquisition and reconstructs the data
        """
        self._check_ram()
        logging.info("Running Acquisition...")
        self._check_abort()
        self.calib_window._dump_gui_state(self.snap_dir)

        channel_idx = self.calib_window.ui.cb_acq_channel.currentIndex()
        channel = self.calib_window.ui.cb_acq_channel.itemText(channel_idx)
        channel_group = None

        groups = self.calib_window.mmc.getAvailableConfigGroups()
        group_list = []
        for i in range(groups.size()):
            group_list.append(groups.get(i))

        for group in group_list:
            config = self.calib_window.mmc.getAvailableConfigs(group)
            for idx in range(config.size()):
                if channel in config.get(idx):
                    channel_group = group
                    break

        # Acquire 3D stack
        logging.debug("Acquiring 3D stack")

        # Generate MDA Settings
        settings = generate_acq_settings(
            self.calib_window.mm,
            channel_group=channel_group,
            channels=[channel],
            zstart=self.calib_window.z_start,
            zend=self.calib_window.z_end,
            zstep=self.calib_window.z_step,
            save_dir=self.snap_dir,
            prefix=self.prefix,
            keep_shutter_open_slices=True,
        )

        self._check_abort()

        # Acquire from MDA settings uses MM MDA GUI
        # Returns (1, 4/5, Z, Y, X) array
        stack = acquire_from_settings(
            self.calib_window.mm,
            settings,
            grab_images=True,
            restore_settings=True,
        )
        self._check_abort()

        # Cleanup acquisition by closing window, converting to zarr, and deleting temp directory
        self._cleanup_acq()

        # Reconstruct snapped images
        self.n_slices = stack.shape[2]

        phase = self._reconstruct()
        self._check_abort()

        # # Save images
        # logging.debug("Saving Images")
        # self._save_imgs(phase, meta)

        # self._check_abort()

        logging.info("Finished Acquisition")
        logging.debug("Finished Acquisition")

        # Emit the images and let thread know function is finished
        self.phase_image_emitter.emit(phase)

    def _reconstruct(self):
        """
        Method to reconstruct
        """
        self._check_abort()

        # Create config and i/o paths
        transfer_function_settings_path = os.path.join(
            self.snap_dir, "transfer_function_settings.yml"
        )
        transfer_function_path = os.path.join(
            self.snap_dir, "transfer_function.zarr"
        )
        apply_inverse_settings_path = os.path.join(
            self.snap_dir, "apply_inverse_settings.yml"
        )
        reconstruction_path = os.path.join(
            self.snap_dir, "reconstruction.zarr"
        )

        with open_ome_zarr(self.latest_out_path, mode="r") as dataset:
            zyx_shape = dataset["0/0/0/0"].shape[2:]

        _generate_reconstruction_config_from_gui(reconstruction_config_path=)

        _generate_transfer_function_config(
            transfer_function_settings_path,
            "phase",
            self.calib_window,
            zyx_shape,
        )
        compute_transfer_function_cli(
            transfer_function_settings_path, transfer_function_path
        )
        _generate_apply_inverse_config(
            apply_inverse_settings_path, self.calib_window
        )
        apply_inverse_transfer_function_cli(
            os.path.join(self.latest_out_path, "0", "0", "0"),
            transfer_function_path,
            apply_inverse_settings_path,
            reconstruction_path,
        )

        # Read reconstruction to pass to emitters
        with open_ome_zarr(reconstruction_path, mode="r") as dataset:
            phase = dataset["0"][0]

        return phase

    def _cleanup_acq(self):
        # Get display windows
        disps = self.dm.getAllDataViewers()

        # loop through display window and find one with matching prefix
        for i in range(disps.size()):
            disp = disps.get(i)

            # close the datastore and grab the path to where the data is saved
            if self.prefix in disp.getName():
                dp = disp.getDataProvider()
                dir_ = dp.getSummaryMetadata().getDirectory()
                prefix = dp.getSummaryMetadata().getPrefix()
                closed = False
                disp.close()
                while not closed:
                    closed = disp.isClosed()
                dp.close()

                # Try to delete the data, sometime it isn't cleaned up quickly enough and will
                # return an error.  In this case, catch the error and then try to close again (seems to work).
                try:
                    save_prefix = (
                        self.calib_window.save_name
                        if self.calib_window.save_name
                        else None
                    )
                    name = (
                        f"RawBFDataSnap.zarr"
                        if not save_prefix
                        else f"{save_prefix}_RawBFDataSnap.zarr"
                    )
                    self.latest_out_path = os.path.join(self.snap_dir, name)
                    converter = TIFFConverter(
                        os.path.join(dir_, prefix),
                        self.latest_out_path,
                        data_type="ometiff",
                        grid_layout=False,
                        label_positions=False,
                    )
                    converter.run()
                    shutil.rmtree(os.path.join(dir_, prefix))
                except PermissionError as ex:
                    dp.close()
                break
            else:
                continue


# TODO: Cache common OTF's on local computers and use those for reconstruction
class PolarizationAcquisitionWorker(WorkerBase):
    """
    Class to execute a birefringence/phase acquisition.  First step is to snap the images follow by a second
    step of reconstructing those images.
    """

    def __init__(
        self, calib_window: MainWidget, calib: QLIPP_Calibration, mode: str
    ):
        super().__init__(SignalsClass=PolarizationAcquisitionSignals)

        # Save current state of GUI window
        self.calib_window = calib_window

        # Init properties
        self.calib = calib
        self.mode = mode
        self.n_slices = None
        self.prefix = "recOrderPluginSnap"
        self.dm = self.calib_window.mm.displays()
        self.channel_group = self.calib_window.config_group

        # Determine whether 2D or 3D acquisition is needed
        if self.mode == "birefringence" and self.calib_window.acq_mode == "2D":
            self.dim = "2D"
        else:
            self.dim = "3D"

        save_dir = (
            self.calib_window.save_directory
            if self.calib_window.save_directory
            else self.calib_window.directory
        )

        if save_dir is None:
            raise ValueError(
                "save directory is empty, please specify a directory in the plugin"
            )

        # increment filename one more than last found saved snap
        i = 0
        prefix = self.calib_window.save_name
        snap_dir = (
            f"recOrderPluginSnap_{i}"
            if not prefix
            else f"{prefix}_recOrderPluginSnap_{i}"
        )
        while os.path.exists(os.path.join(save_dir, snap_dir)):
            i += 1
            snap_dir = (
                f"recOrderPluginSnap_{i}"
                if not prefix
                else f"{prefix}_recOrderPluginSnap_{i}"
            )

        self.snap_dir = os.path.join(save_dir, snap_dir)
        os.mkdir(self.snap_dir)

    def _check_abort(self):
        if self.abort_requested:
            self.aborted.emit()
            raise TimeoutError("Stop Requested")

    def _check_ram(self):
        """
        Show a warning if RAM < 32 GB.
        """
        is_warning, msg = ram_message()
        if is_warning:
            show_warning(msg)
        else:
            logging.info(msg)

    def work(self):
        """
        Function that runs the 2D or 3D acquisition and reconstructs the data
        """
        self._check_ram()
        logging.info("Running Acquisition...")
        self.calib_window._dump_gui_state(self.snap_dir)

        # List the Channels to acquire, if 5-state then append 5th channel
        channels = ["State0", "State1", "State2", "State3"]
        if self.calib.calib_scheme == "5-State":
            channels.append("State4")

        self._check_abort()

        # Acquire 2D stack
        if self.dim == "2D":
            logging.debug("Acquiring 2D stack")

            # Generate MDA Settings
            self.settings = generate_acq_settings(
                self.calib_window.mm,
                channel_group=self.channel_group,
                channels=channels,
                save_dir=self.snap_dir,
                prefix=self.prefix,
                keep_shutter_open_channels=True,
            )
            self._check_abort()
            # acquire images
            stack = self._acquire()

        # Acquire 3D stack
        else:
            logging.debug("Acquiring 3D stack")

            # Generate MDA Settings
            self.settings = generate_acq_settings(
                self.calib_window.mm,
                channel_group=self.channel_group,
                channels=channels,
                zstart=self.calib_window.z_start,
                zend=self.calib_window.z_end,
                zstep=self.calib_window.z_step,
                save_dir=self.snap_dir,
                prefix=self.prefix,
                keep_shutter_open_channels=True,
                keep_shutter_open_slices=True,
            )

            self._check_abort()

            # set acquisition order to channel-first
            self.settings["slicesFirst"] = False
            self.settings["acqOrderMode"] = 0  # TIME_POS_SLICE_CHANNEL

            # acquire images
            stack = self._acquire()

        # Cleanup acquisition by closing window, converting to zarr, and deleting temp directory
        self._cleanup_acq()

        # Reconstruct snapped images
        self._check_abort()
        self.n_slices = stack.shape[2]
        birefringence, phase = self._reconstruct()
        self._check_abort()

        if self.calib_window.orientation_offset:
            birefringence = self._orientation_offset(birefringence)

        # Save images
        # logging.debug("Saving Images")
        # self._save_imgs(birefringence, phase)

        # self._check_abort()

        logging.info("Finished Acquisition")
        logging.debug("Finished Acquisition")

        # Emit the images and let thread know function is finished
        self.bire_image_emitter.emit(birefringence)
        self.phase_image_emitter.emit(phase)

    def _orientation_offset(self, birefringence: np.ndarray):
        """Apply +90 degree orientation offset

        Parameters
        ----------
        birefringence : np.ndarray
            [2, Y, X] retardance and orientation

        Returns
        -------
        ndarray
            birefringence with offset
        """
        show_warning(
            (
                "Applying a +90 degree orientation offset to birefringence! "
                "This will affect both visualization and the saved reconstruction."
            )
        )

        # TODO: Move these to waveorder, connect to the `orientation_flip`
        # and `orientation_rotate` parameters, and connect to recOrder buttons.

        # 90 degree flip
        birefringence[1] = np.fmod(birefringence[1] + np.pi / 2, np.pi)

        # Reflection
        birefringence[1] = np.fmod(-birefringence[1], np.pi) + np.pi

        return birefringence

    def _check_exposure(self) -> None:
        """
        Check that all LF channels have the same exposure settings. If not, abort Acquisition.
        """
        # parse exposure times
        channel_exposures = []
        for channel in self.settings["channels"]:
            channel_exposures.append(channel["exposure"])
        logging.debug(f"Verifying exposure times: {channel_exposures}")
        channel_exposures = np.array(channel_exposures)
        # check if exposure times are equal
        if not np.all(channel_exposures == channel_exposures[0]):
            error_exposure_msg = (
                f"The MDA exposure times are not equal! Aborting Acquisition.\n"
                f"Please manually set the exposure times to the same value from the MDA menu."
            )

            raise ValueError(error_exposure_msg)

        self._check_abort()

    def _acquire(self) -> np.ndarray:
        """
        Acquire images.

        Returns
        -------
        stack:          (nd-array) Dimensions are (C, Z, Y, X). Z=1 for 2D acquisition.
        """
        # check if exposure times are the same
        self._check_exposure()

        # Acquire from MDA settings uses MM MDA GUI
        # Returns (1, 4/5, Z, Y, X) array
        stack = acquire_from_settings(
            self.calib_window.mm,
            self.settings,
            grab_images=True,
            restore_settings=True,
        )
        self._check_abort()

        return stack

    def _reconstruct(self):
        """
        Method to reconstruct.  First need to initialize the reconstructor given
        what type of acquisition it is (birefringence only skips a lot of heavy compute needed for phase).
        This function also checks to see if the reconstructor needs to be updated from previous acquisitions

        """
        self._check_abort()

        # Create config and i/o paths
        transfer_function_settings_path = os.path.join(
            self.snap_dir, "transfer_function_settings.yml"
        )
        transfer_function_path = os.path.join(
            self.snap_dir, "transfer_function.zarr"
        )
        apply_inverse_settings_path = os.path.join(
            self.snap_dir, "apply_inverse_settings.yml"
        )
        reconstruction_path = os.path.join(
            self.snap_dir, "reconstruction.zarr"
        )

        with open_ome_zarr(self.latest_out_path, mode="r") as dataset:
            zyx_shape = dataset["0/0/0/0"].shape[2:]

        _generate_transfer_function_config(
            transfer_function_settings_path,
            self.mode,
            self.calib_window,
            zyx_shape,
        )
        compute_transfer_function_cli(
            transfer_function_settings_path, transfer_function_path
        )
        _generate_apply_inverse_config(
            apply_inverse_settings_path, self.calib_window
        )
        apply_inverse_transfer_function_cli(
            os.path.join(self.latest_out_path, "0", "0", "0"),
            transfer_function_path,
            apply_inverse_settings_path,
            reconstruction_path,
        )

        # Read reconstruction to pass to emitters
        with open_ome_zarr(reconstruction_path, mode="r") as dataset:
            czyx_data = dataset["0"][0]
            birefringence = czyx_data[0:4]
            try:
                phase = czyx_data[4]
            except:
                phase = None

        return birefringence, phase

    def _cleanup_acq(self):
        # Get display windows
        disps = self.dm.getAllDataViewers()

        # loop through display window and find one with matching prefix
        for i in range(disps.size()):
            disp = disps.get(i)

            # close the datastore and grab the path to where the data is saved
            if self.prefix in disp.getName():
                dp = disp.getDataProvider()
                dir_ = dp.getSummaryMetadata().getDirectory()
                prefix = dp.getSummaryMetadata().getPrefix()
                closed = False
                disp.close()
                while not closed:
                    closed = disp.isClosed()
                dp.close()

                # Try to delete the data, sometime it isn't cleaned up quickly enough and will
                # return an error.  In this case, catch the error and then try to close again (seems to work).
                try:
                    save_prefix = (
                        self.calib_window.save_name
                        if self.calib_window.save_name
                        else None
                    )
                    name = (
                        f"RawPolDataSnap.zarr"
                        if not save_prefix
                        else f"{save_prefix}_RawPolDataSnap.zarr"
                    )
                    self.latest_out_path = os.path.join(self.snap_dir, name)
                    converter = TIFFConverter(
                        os.path.join(dir_, prefix),
                        self.latest_out_path,
                        data_type="ometiff",
                        grid_layout=False,
                        label_positions=False,
                    )
                    converter.run()
                    shutil.rmtree(os.path.join(dir_, prefix))
                except PermissionError as ex:
                    dp.close()
                break
            else:
                continue


# class ListeningWorker(WorkerBase):
#     """
#     Class to execute a birefringence/phase acquisition.  First step is to snap the images follow by a second
#     step of reconstructing those images.
#     """

#     def __init__(self, calib_window, bg_data):
#         super().__init__(SignalsClass=ListeningSignals)

#         # Save current state of GUI window
#         self.calib_window = calib_window

#         # Init properties
#         self.n_slices = None
#         self.n_channels = None
#         self.n_frames = None
#         self.n_pos = None
#         self.shape = None
#         self.dtype = None
#         self.root = None
#         self.prefix = None
#         self.store = None
#         self.save_directory = None
#         self.bg_data = bg_data
#         self.reconstructor = None

#     def _check_abort(self):
#         if self.abort_requested:
#             self.aborted.emit()
#             raise TimeoutError("Stop Requested")

#     def get_byte_offset(self, offsets, page):
#         """
#         Gets the byte offset from the tiff tag metadata.

#         210 accounts for header data + page header data.
#         162 accounts page header data

#         Parameters
#         ----------
#         offsets:             (dict) Offset dictionary list
#         page:               (int) Page to look at for the offset

#         Returns
#         -------
#         byte offset:        (int) byte offset for the image array

#         """

#         if page == 0:
#             array_offset = offsets[page] + 210
#         else:
#             array_offset = offsets[page] + 162

#         return array_offset

#     def listen_for_images(
#         self, array, file, offsets, interval, dim3, dim2, dim1, dim0, dim_order
#     ):
#         """

#         Parameters
#         ----------
#         array:          (nd-array) numpy array of size (C, Z)
#         file:           (string) filepath corresponding to the desired tiff image
#         offsets:        (dict) dictionary of offsets corresponding to byte offsets of pixel data in tiff image
#         interval:       (int) time interval between timepoints in seconds
#         dim3:           (int) outermost dimension to value begin at
#         dim2:           (int) first-inner dimension value to begin at
#         dim1:           (int) second-inner dimension value to begin at
#         dim0:           (int) innermost dimension value to begin at
#         dim_order:      (int) 1, 2, 3, or 4 corresponding to the dimensionality ordering of the acquisition (MM-provided)

#         Returns
#         -------
#         array:                      (nd-array) partially filled array of size (C, Z) to continue filling in next iteration
#         index:                      (int) current page number at end of function
#         dim3:                       (int) dimension values corresponding to where the next iteration should begin
#         dim2:                       (int) dimension values corresponding to where the next iteration should begin
#         dim1:                       (int) dimension values corresponding to where the next iteration should begin
#         dim0:                       (int) dimension values corresponding to where the next iteration should begin

#         """

#         # Order dimensions that we will loop through in order to match the acquisition
#         if dim_order == 0:
#             dims = [
#                 [dim3, self.n_frames],
#                 [dim2, self.n_pos],
#                 [dim1, self.n_slices],
#                 [dim0, self.n_channels],
#             ]
#             channel_dim = 0
#         elif dim_order == 1:
#             dims = [
#                 [dim3, self.n_frames],
#                 [dim2, self.n_pos],
#                 [dim1, self.n_channels],
#                 [dim0, self.n_slices],
#             ]
#             channel_dim = 1
#         elif dim_order == 2:
#             dims = [
#                 [dim3, self.n_pos],
#                 [dim2, self.n_frames],
#                 [dim1, self.n_slices],
#                 [dim0, self.n_channels],
#             ]
#             channel_dim = 0
#         else:
#             dims = [
#                 [dim3, self.n_pos],
#                 [dim2, self.n_frames],
#                 [dim1, self.n_channels],
#                 [dim0, self.n_slices],
#             ]
#             channel_dim = 1

#         # Loop through dimensions in the order they are acquired
#         idx = 0
#         for dim3 in range(dims[0][0], dims[0][1]):
#             for dim2 in range(dims[1][0], dims[1][1]):
#                 for dim1 in range(dims[2][0], dims[2][1]):
#                     for dim0 in range(dims[3][0], dims[3][1]):
#                         # GET OFFSET AND WAIT
#                         if idx > 0:
#                             try:
#                                 offset = self.get_byte_offset(offsets, idx)
#                             except IndexError:
#                                 # NEED TO STOP BECAUSE RAN OUT OF PAGES OR REACHED END OF ACQ
#                                 return array, idx, dim3, dim2, dim1, dim0

#                             # Checks if the offset in metadata is 0, but technically self.get_byte_offset() adds
#                             # 162 to every offset to account for tiff file header bytes
#                             while offset == 162:
#                                 self._check_abort()
#                                 tf = tiff.TiffFile(file)
#                                 time.sleep(interval)
#                                 offsets = tf.micromanager_metadata["IndexMap"][
#                                     "Offset"
#                                 ]
#                                 tf.close()
#                                 offset = self.get_byte_offset(offsets, idx)
#                         else:
#                             offset = self.get_byte_offset(offsets, idx)

#                         if idx < (
#                             self.n_slices
#                             * self.n_channels
#                             * self.n_frames
#                             * self.n_pos
#                         ):
#                             # Assign dimensions based off acquisition order to correctly add image to array
#                             if dim_order == 0:
#                                 t, p, c, z = dim3, dim2, dim0, dim1
#                             elif dim_order == 1:
#                                 t, p, c, z = dim3, dim2, dim1, dim0
#                             elif dim_order == 2:
#                                 t, p, c, z = dim2, dim3, dim0, dim1
#                             else:
#                                 t, p, c, z = dim2, dim3, dim1, dim0

#                             self._check_abort()

#                             # Add Image to array
#                             img = np.memmap(
#                                 file,
#                                 dtype=self.dtype,
#                                 mode="r",
#                                 offset=offset,
#                                 shape=self.shape,
#                             )
#                             array[c, z] = img

#                             # If Channel first, compute birefringence here
#                             if (
#                                 channel_dim == 0
#                                 and dim0 == self.n_channels - 1
#                             ):
#                                 self._check_abort()

#                                 # Compute birefringence
#                                 self.compute_and_save(array[:, z], p, t, z)

#                             idx += 1

#                     # Reset Range to 0 to account for starting this function in middle of a dimension
#                     if idx < (
#                         self.n_slices
#                         * self.n_channels
#                         * self.n_frames
#                         * self.n_pos
#                     ):
#                         dims[2][0] = 0
#                         dims[3][0] = 0

#                     # If z-first, compute the birefringence here
#                     if channel_dim == 1 and dim1 == self.n_channels - 1:
#                         # Assign dimensions based off acquisition order to correctly add image to array
#                         if dim_order == 0:
#                             t, p, c, z = dim3, dim2, dim0, dim1
#                         elif dim_order == 1:
#                             t, p, c, z = dim3, dim2, dim1, dim0
#                         elif dim_order == 2:
#                             t, p, c, z = dim2, dim3, dim0, dim1
#                         else:
#                             t, p, c, z = dim2, dim3, dim1, dim0

#                         self._check_abort()
#                         self.compute_and_save(array, p, t, dim0)
#                     else:
#                         continue

#                 # Reset range to 0 to account for starting this function in the middle of a dimension
#                 if idx < (
#                     self.n_slices
#                     * self.n_channels
#                     * self.n_frames
#                     * self.n_pos
#                 ):
#                     dims[1][0] = 0

#         # Return at the end of the acquisition
#         return array, idx, dim3, dim2, dim1, dim0

#     def compute_and_save(self, array, p, t, z):
#         if self.n_slices == 1:
#             array = array[:, 0]

#         birefringence = self.reconstructor.reconstruct(array)

#         # If the napari layer doesn't exist yet, create the zarr store to emit to napari
#         if self.prefix not in self.calib_window.viewer.layers:
#             self.store = zarr.open(
#                 os.path.join(self.root, self.prefix + ".zarr")
#             )
#             self.store.zeros(
#                 name="Birefringence",
#                 shape=(
#                     self.n_pos,
#                     self.n_frames,
#                     2,
#                     self.n_slices,
#                     self.shape[0],
#                     self.shape[1],
#                 ),
#                 chunks=(1, 1, 1, 1, self.shape[0], self.shape[1]),
#                 overwrite=True,
#             )

#             # Add data and send out the store.  Once the store has been emitted, we can add data to the store
#             # without needing to emit the store again (thanks to napari's handling of zarr datasets)
#             if len(birefringence.shape) == 4:
#                 self.store["Birefringence"][p, t] = birefringence
#             else:
#                 self.store["Birefringence"][p, t, :, z] = birefringence

#             self.store_emitter.emit(self.store)

#         else:
#             if len(birefringence.shape) == 4:
#                 self.store["Birefringence"][p, t] = birefringence
#             else:
#                 self.store["Birefringence"][p, t, :, z] = birefringence

#         # Emit the current dimensions so that we can update the napari dimension slider
#         self.dim_emitter.emit((p, t, z))

#     def work(self):
#         acq_man = self.calib_window.mm.acquisitions()

#         while not acq_man.isAcquisitionRunning():
#             pass

#         time.sleep(1)

#         # Get all of the dataset dimensions, settings
#         s = acq_man.getAcquisitionSettings()
#         self.root = s.root()
#         self.prefix = s.prefix()
#         self.n_frames, self.interval = (
#             (s.numFrames(), s.intervalMs() / 1000) if s.useFrames() else (1, 1)
#         )
#         self.n_channels = s.channels().size() if s.useChannels() else 1
#         self.n_slices = s.slices().size() if s.useChannels() else 1
#         self.n_pos = (
#             1
#             if not s.usePositionList()
#             else self.calib_window.mm.getPositionListManager()
#             .getPositionList()
#             .getNumberOfPositions()
#         )
#         dim_order = s.acqOrderMode()

#         # Get File Path corresponding to current dataset
#         path = os.path.join(self.root, self.prefix)
#         files = [fn for fn in glob.glob(path + "*") if ".zarr" not in fn]
#         index = max([int(x.strip(path + "_")) for x in files])

#         self.prefix = self.prefix + f"_{index}"
#         full_path = os.path.join(self.root, self.prefix)
#         first_file_path = os.path.join(
#             full_path, self.prefix + "_MMStack.ome.tif"
#         )

#         file = tiff.TiffFile(first_file_path)
#         file_path = first_file_path
#         self.shape = (
#             file.micromanager_metadata["Summary"]["Height"],
#             file.micromanager_metadata["Summary"]["Width"],
#         )
#         self.dtype = file.pages[0].dtype
#         offsets = file.micromanager_metadata["IndexMap"]["Offset"]
#         file.close()

#         self._check_abort()

#         # Init Reconstruction Class
#         self.reconstructor = QLIPPBirefringenceCompute(
#             self.shape,
#             self.calib_window.calib_scheme,
#             self.calib_window.wavelength,
#             self.calib_window.swing,
#             self.n_slices,
#             self.calib_window.bg_option,
#             self.bg_data,
#         )

#         self._check_abort()

#         # initialize dimensions / array for the loop
#         idx, dim3, dim2, dim1, dim0 = 0, 0, 0, 0, 0
#         array = np.zeros(
#             (self.n_channels, self.n_slices, self.shape[0], self.shape[1])
#         )
#         file_count = 0
#         total_idx = 0

#         # Run until the function has collected the totality of the data
#         while total_idx < (
#             self.n_slices * self.n_channels * self.n_frames * self.n_pos
#         ):
#             self._check_abort()

#             # this will loop through reading images in a single file as it's being written
#             # when it has successfully loaded all of the images from the file, it'll move on to the next
#             array, idx, dim3, dim2, dim1, dim0 = self.listen_for_images(
#                 array,
#                 file_path,
#                 offsets,
#                 self.interval,
#                 dim3,
#                 dim2,
#                 dim1,
#                 dim0,
#                 dim_order,
#             )

#             total_idx += idx

#             # If acquisition is not finished, grab the next file and listen for images
#             if (
#                 total_idx
#                 != self.n_slices * self.n_channels * self.n_frames * self.n_pos
#             ):
#                 time.sleep(1)
#                 file_count += 1
#                 file_path = os.path.join(
#                     full_path, self.prefix + f"_MMStack_{file_count}.ome.tif"
#                 )
#                 file = tiff.TiffFile(file_path)
#                 offsets = file.micromanager_metadata["IndexMap"]["Offset"]
#                 file.close()
