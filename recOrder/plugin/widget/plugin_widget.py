from recOrder.calib.Calibration import QLIPP_Calibration
from pycromanager import Bridge
from PyQt5.QtCore import pyqtSlot, pyqtSignal
from PyQt5.QtWidgets import QWidget, QFileDialog
from recOrder.plugin.calibration.calibration_workers import CalibrationWorker, BackgroundCaptureWorker
from recOrder.plugin.acquisition.acquisition_workers import AcquisitionWorker
from recOrder.plugin.widget.thread_worker import ThreadWorker
from recOrder.plugin.qtdesigner import recOrder_calibration_v4, recOrder_calibration_v5
from pathlib import Path
from napari import Viewer
from recOrder.calib.CoreFunctions import set_lc_state, snap_and_average
import os
import logging

#TODO
# Error Handling on the Calibration Thread
# Clear buffer before calibration?
# Check out using the 5state scheme individually

class recOrder_Widget(QWidget):

    mm_status_changed = pyqtSignal(bool)
    intensity_changed = pyqtSignal(float)
    log_changed = pyqtSignal(str)

    def __init__(self, napari_viewer: Viewer):
        super().__init__()
        self.viewer = napari_viewer

        # Setup GUI Elements
        self.ui = recOrder_calibration_v5.Ui_Form()
        self.ui.setupUi(self)

        # Setup Connections between elements
        # Recievers
        # =================================
        # Connect to Micromanager
        self.ui.qbutton_mm_connect.clicked[bool].connect(self.connect_to_mm)

        # Calibration Parameters
        self.ui.qbutton_browse.clicked[bool].connect(self.browse_dir_path)
        self.ui.le_directory.editingFinished.connect(self.enter_dir_path)
        self.ui.le_swing.editingFinished.connect(self.enter_swing)
        self.ui.le_wavelength.editingFinished.connect(self.enter_wavelength)
        self.ui.cb_calib_scheme.currentIndexChanged[int].connect(self.enter_calib_scheme)
        self.ui.chb_use_roi.stateChanged[int].connect(self.enter_use_cropped_roi)
        self.ui.qbutton_calibrate.clicked[bool].connect(self.run_calibration)
        self.ui.qbutton_calc_extinction.clicked[bool].connect(self.calc_extinction)

        # Capture Background
        self.ui.le_bg_folder.editingFinished.connect(self.enter_bg_folder_name)
        self.ui.le_n_avg.editingFinished.connect(self.enter_n_avg)
        self.ui.qbutton_capture_bg.clicked[bool].connect(self.capture_bg)

        # Advanced
        self.ui.cb_loglevel.currentIndexChanged[int].connect(self.enter_log_level)

        ######### Acquisition Tab #########
        self.ui.qbutton_browse_save_path.clicked[bool].connect(self.browse_save_path)
        self.ui.chb_save_imgs.stateChanged[int].connect(self.enter_save_imgs)
        self.ui.le_save_path.editingFinished.connect(self.enter_save_path)
        self.ui.le_zstart.editingFinished.connect(self.enter_zstart)
        self.ui.le_zend.editingFinished.connect(self.enter_zend)
        self.ui.le_zstep.editingFinished.connect(self.enter_zstep)
        self.ui.chb_use_gpu.stateChanged[int].connect(self.enter_use_gpu)
        self.ui.le_gpu_id.editingFinished.connect(self.enter_gpu_id)
        self.ui.le_obj_na.editingFinished.connect(self.enter_obj_na)
        self.ui.le_cond_na.editingFinished.connect(self.enter_cond_na)
        self.ui.le_mag.editingFinished.connect(self.enter_mag)
        self.ui.le_ps.editingFinished.connect(self.enter_ps)
        self.ui.le_n_media.editingFinished.connect(self.enter_n_media)
        self.ui.le_pad_z.editingFinished.connect(self.enter_pad_z)
        self.ui.cb_birefringence.currentIndexChanged[int].connect(self.enter_birefringence_dim)
        self.ui.cb_phase.currentIndexChanged[int].connect(self.enter_phase_dim)
        self.ui.cb_bg_method.currentIndexChanged[int].connect(self.enter_bg_correction)
        self.ui.le_bg_path.editingFinished.connect(self.enter_acq_bg_path)
        self.ui.qbutton_browse_bg_path.clicked[bool].connect(self.browse_acq_bg_path)
        self.ui.qbutton_acq_birefringence.clicked[bool].connect(self.acq_birefringence)
        self.ui.qbutton_acq_phase.clicked[bool].connect(self.acq_phase)
        self.ui.qbutton_acq_birefringence_phase.clicked[bool].connect(self.acq_birefringence_phase)

        # Logging
        log_box = QtLogger(self.ui.te_log)
        log_box.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
        logging.getLogger().addHandler(log_box)
        logging.getLogger().setLevel(logging.INFO)

        # Emitters
        # =================================#
        self.mm_status_changed.connect(self.handle_mm_status_update)

        #Other Properties:
        self.mm = None
        self.mmc = None
        self.home_path = str(Path.home())
        self.directory = None
        self.swing = 0.1
        self.wavelength = 532
        self.calib_scheme = '4-State'
        self.use_cropped_roi = False
        self.bg_folder_name = 'BG'
        self.n_avg = 20
        self.intensity_monitor = []
        self.save_imgs = False
        self.save_directory = None
        self.bg_option = 'None'
        self.birefringence_dim = '2D'
        self.phase_dim = '2D'
        self.z_start = None
        self.z_end = None
        self.z_step = None
        self.gpu_id = 0
        self.use_gpu = False
        self.obj_na = None
        self.cond_na = None
        self.mag = None
        self.ps = None
        self.n_media = 1.003
        self.pad_z = 0
        self.phase_reconstructor = None
        self.acq_bg_directory = None

        # Assessment attributes
        self.calib_assessment_level = None

        # Init Plot
        plot_item = self.ui.plot_widget.getPlotItem()
        plot_item.enableAutoRange()
        plot_item.setLabel('left', 'Intensity')
        self.ui.plot_widget.setBackground((32, 34, 40))

        # Init Logger
        self.ui.te_log.setStyleSheet('background-color: rgb(32,34,40);')

        #Init thread worker
        self.thread_worker = None

    @pyqtSlot(bool)
    def connect_to_mm(self):
        try:
            bridge = Bridge(convert_camel_case=False)
            self.mmc = bridge.get_core()
            self.mm = bridge.get_studio()
            self.calib = QLIPP_Calibration(self.mmc, self.mm)

            self.mm_status_changed.emit(True)
        except:
            self.mm_status_changed.emit(False)

    @pyqtSlot(bool)
    def handle_mm_status_update(self, value):
        if value:
            self.ui.le_mm_status.setText('Sucess!')
            # self.ui.le_mm_status.setStyleSheet("border: 1px solid green;")
            self.ui.le_mm_status.setStyleSheet("background-color: green;")
        else:
            self.ui.le_mm_status.setText('Failed.')
            self.ui.le_mm_status.setStyleSheet("background-color: rgb(200,0,0);")
            # self.ui.le_mm_status.setStyleSheet("border: 1px solid red;")

    @pyqtSlot(int)
    def handle_progress_update(self, value):
        self.ui.progress_bar.setValue(value)

    @pyqtSlot(str)
    def handle_extinction_update(self, value):
        self.ui.le_extinction.setText(value)

    @pyqtSlot(object)
    def handle_plot_update(self, value):
        self.intensity_monitor.append(value)
        self.ui.plot_widget.plot(self.intensity_monitor)
        self.ui.plot_widget.getPlotItem().autoRange()

    @pyqtSlot(str)
    def handle_calibration_assessment_update(self, value):
        self.calib_assessment_level = value

    @pyqtSlot(str)
    def handle_calibration_assessment_msg_update(self, value):
        self.ui.le_calib_assessment.setText(value)

        if self.calib_assessment_level == 'good':
            self.ui.le_calib_assessment.setStyleSheet("border: 1px solid green;")
        elif self.calib_assessment_level == 'okay':
            self.ui.le_calib_assessment.setStyleSheet("border: 1px solid rgb(252,190,3);")
        elif self.calib_assessment_level == 'bad':
            self.ui.le_calib_assessment.setStyleSheet("border: 1px solid rgb(200,0,0);")
        else:
            pass

    @pyqtSlot(object)
    def handle_bg_image_update(self, value):
        print(self.viewer.layers)
        if 'Background Images' in self.viewer.layers:
            self.viewer.layers['Background Images'].data = value
        else:
            self.viewer.add_image(value, name='Background Images', colormap='gray')

    @pyqtSlot(object)
    def handle_bg_bire_image_update(self, value):

        if 'Background Retardance' in self.viewer.layers:
            self.viewer.layers['Background Retardance'].data = value[0]
        else:
            self.viewer.add_image(value[0], name='Background Retardance', colormap='gray')

        if 'Background Orientation' in self.viewer.layers:
            self.viewer.layers['Background Orientation'].data = value[1]
        else:
            self.viewer.add_image(value[1], name='Background Orientation', colormap='gray')

    @pyqtSlot(object)
    def handle_bire_image_update(self, value):
        name = 'Birefringence2D' if self.birefringence_dim == '2D' else 'Birefringence3D'

        if name in self.viewer.layers:
            self.viewer.layers[name].data = value
        else:
            self.viewer.add_image(value, name=name, colormap='gray')

    @pyqtSlot(object)
    def handle_phase_image_update(self, value):
        name = 'Phase2D' if self.phase_dim == '2D' else 'Phase3D'

        if name in self.viewer.layers:
            self.viewer.layers[name].data = value
        else:
            self.viewer.add_image(value, name=name, colormap='gray')

    @pyqtSlot(object)
    def handle_reconstructor_update(self, value):
        self.phase_reconstructor = value

    @pyqtSlot(bool)
    def browse_dir_path(self):
        # self.ui.le_directory.setFocus()
        result = self._open_file_dialog(self.home_path)
        self.directory = result
        self.ui.le_directory.setText(result)

    @pyqtSlot(bool)
    def browse_save_path(self):
        # self.ui.le_directory.setFocus()
        result = self._open_file_dialog(self.home_path)
        self.save_directory = result
        self.ui.le_save_path.setText(result)

    @pyqtSlot()
    def enter_dir_path(self):
        path = self.ui.le_directory.text()
        if os.path.exists(path):
            self.directory = path
        else:
            self.ui.le_directory.setText('Path Does Not Exist')

    @pyqtSlot()
    def enter_swing(self):
        self.swing = float(self.ui.le_swing.text())

    @pyqtSlot()
    def enter_wavelength(self):
        self.wavelength = int(self.ui.le_wavelength.text())

    @pyqtSlot()
    def enter_calib_scheme(self):
        index = self.ui.cb_calib_scheme.currentIndex()
        if index == 0:
            self.calib_scheme = '4-State'
        else:
            self.calib_scheme = '5-State'

    @pyqtSlot()
    def enter_use_cropped_roi(self):
        state = self.ui.chb_use_roi.checkState()
        if state == 2:
            self.use_cropped_roi = True
        elif state == 0:
            self.use_cropped_roi = False

    @pyqtSlot()
    def enter_bg_folder_name(self):
        self.bg_folder_name = self.ui.le_bg_folder.text()

    @pyqtSlot()
    def enter_n_avg(self):
        self.n_avg = int(self.ui.le_n_avg.text())

    @pyqtSlot()
    def enter_log_level(self):
        index = self.ui.cb_loglevel.currentIndex()
        if index == 0:
            logging.getLogger().setLevel(logging.INFO)
        else:
            logging.getLogger().setLevel(logging.DEBUG)

    @pyqtSlot()
    def enter_save_imgs(self):
        state = self.ui.chb_save_imgs.checkState()
        if state == 2:
            self.save_imgs = True
        elif state == 0:
            self.save_imgs = False

    @pyqtSlot()
    def enter_save_path(self):
        path = self.ui.le_save_path.text()
        if os.path.exists(path):
            self.save_directory = path
        else:
            self.ui.le_directory.setText('Path Does Not Exist')

    @pyqtSlot()
    def enter_zstart(self):
        self.z_start = float(self.ui.le_zstart.text())

    @pyqtSlot()
    def enter_zend(self):
        self.z_end = float(self.ui.le_zend.text())

    @pyqtSlot()
    def enter_zstep(self):
        self.z_step = float(self.ui.le_zstep.text())

    @pyqtSlot()
    def enter_birefringence_dim(self):
        state = self.ui.cb_birefringence.currentIndex()
        if state == 0:
            self.birefringence_dim = '2D'
        elif state == 1:
            self.birefringence_dim = '3D'

    @pyqtSlot()
    def enter_phase_dim(self):
        state = self.ui.cb_phase.currentIndex()
        if state == 0:
            self.phase_dim = '2D'
        elif state == 1:
            self.phase_dim = '3D'

    @pyqtSlot()
    def enter_acq_bg_path(self):
        path = self.ui.le_bg_path.text()
        if os.path.exists(path):
            self.acq_bg_directory = path
        else:
            self.ui.le_bg_path.setText('Path Does Not Exist')

    @pyqtSlot(bool)
    def browse_acq_bg_path(self):
        result = self._open_file_dialog(self.home_path)
        self.acq_bg_directory = result
        self.ui.le_bg_path.setText(result)

    @pyqtSlot()
    def enter_bg_correction(self):
        state = self.ui.cb_bg_method.currentIndex()
        if state == 0:
            self.bg_option = 'None'
        elif state == 1:
            self.bg_option = 'global'
        elif state == 2:
            self.bg_option = 'local'

    @pyqtSlot()
    def enter_gpu_id(self):
        self.gpu_id = int(self.ui.le_gpu_id.text())

    @pyqtSlot()
    def enter_use_gpu(self):
        state = self.ui.chb_use_gpu.checkState()
        if state == 2:
            self.use_gpu = True
        elif state == 0:
            self.use_gpu = False

    @pyqtSlot()
    def enter_obj_na(self):
        self.obj_na = float(self.ui.le_obj_na.text())

    @pyqtSlot()
    def enter_cond_na(self):
        self.cond_na = float(self.ui.le_cond_na.text())

    @pyqtSlot()
    def enter_mag(self):
        self.mag = float(self.ui.le_mag.text())

    @pyqtSlot()
    def enter_ps(self):
        self.ps = float(self.ui.le_ps.text())

    @pyqtSlot()
    def enter_n_media(self):
        self.n_media = float(self.ui.le_n_media.text())

    @pyqtSlot()
    def enter_pad_z(self):
        self.pad_z = float(self.ui.le_pad_z.text())

    @pyqtSlot(bool)
    def calc_extinction(self):
        set_lc_state(self.mmc, 'State0')
        extinction = snap_and_average(self.calib.snap_manager)
        set_lc_state(self.mmc, 'State1')
        state1 = snap_and_average(self.calib.snap_manager)
        extinction = self.calib.calculate_extinction(self.swing, self.calib.I_Black, extinction, state1)
        self.ui.le_extinction.setText(str(extinction))

    @pyqtSlot(bool)
    def run_calibration(self):
        #TODO: clear calibration plot
        logging.info('Starting Calibration')
        self.ui.progress_bar.setValue(0)
        self.intensity_monitor = []
        self.calib.swing = self.swing
        self.calib.wavelength = self.wavelength
        self.calib.meta_file = os.path.join(self.directory, 'calibration_metadata.txt')


        if self.calib.snap_manager.getIsLiveModeOn():
            self.calib.snap_manager.setLiveModeOn(False)


        worker = CalibrationWorker(self, self.calib)
        self.thread_worker = ThreadWorker(self, worker)
        self.thread_worker.initalize()

        self.thread_worker.worker.progress_update.connect(self.handle_progress_update)
        self.thread_worker.worker.extinction_update.connect(self.handle_extinction_update)
        self.thread_worker.worker.intensity_update.connect(self.handle_plot_update)
        self.thread_worker.worker.calib_assessment.connect(self.handle_calibration_assessment_update)
        self.thread_worker.worker.calib_assessment_msg.connect(self.handle_calibration_assessment_msg_update)

        self.thread_worker._disable_buttons()
        self.thread_worker.thread.start()

    @pyqtSlot(bool)
    def capture_bg(self):

        worker = BackgroundCaptureWorker(self, self.calib)
        self.thread_worker = ThreadWorker(self, worker)
        self.thread_worker.initalize()

        self.thread_worker.worker.bg_image_emitter.connect(self.handle_bg_image_update)
        self.thread_worker.worker.bire_image_emitter.connect(self.handle_bg_bire_image_update)

        self.thread_worker._disable_buttons()
        self.thread_worker.thread.start()

    @pyqtSlot(bool)
    def acq_birefringence(self):

        worker = AcquisitionWorker(self, self.calib, 'birefringence')
        self.thread_worker = ThreadWorker(self, worker)
        self.thread_worker.initalize()

        self.thread_worker.worker.bire_image_emitter.connect(self.handle_bire_image_update)

        self.thread_worker._disable_buttons()
        self.thread_worker.thread.start()

    @pyqtSlot(bool)
    def acq_phase(self):

        worker = AcquisitionWorker(self, self.calib, 'phase')
        self.thread_worker = ThreadWorker(self, worker)
        self.thread_worker.initalize()

        self.thread_worker.worker.phase_image_emitter.connect(self.handle_phase_image_update)
        self.thread_worker.worker.phase_reconstructor_emitter.connect(self.handle_reconstructor_update)

        self.thread_worker._disable_buttons()
        self.thread_worker.thread.start()

    @pyqtSlot(bool)
    def acq_birefringence_phase(self):

        worker = AcquisitionWorker(self, self.calib, 'all')
        self.thread_worker = ThreadWorker(self, worker)
        self.thread_worker.initalize()

        self.thread_worker.worker.phase_image_emitter.connect(self.handle_phase_image_update)
        self.thread_worker.worker.bire_image_emitter.connect(self.handle_bire_image_update)
        self.thread_worker.worker.phase_reconstructor_emitter.connect(self.handle_reconstructor_update)

        self.thread_worker._disable_buttons()
        self.thread_worker.thread.start()

    def _open_file_dialog(self, default_path):
        return self._open_dialog("select a directory",
                                 default_path)

    def _open_dialog(self, title, ref):
        options = QFileDialog.Options()

        options |= QFileDialog.DontUseNativeDialog
        path = QFileDialog.getExistingDirectory(None,
                                                title,
                                                ref,
                                                options=options)
        return path


class QtLogger(logging.Handler):

    def __init__(self, widget):
        super().__init__()
        self.widget = widget

    def emit(self, record):
        msg = self.format(record)
        self.widget.appendPlainText(msg)
