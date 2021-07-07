from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QFileDialog, QAction, QWidget
from PyQt5.QtCore import pyqtSlot
from recOrder.viewer.qtdesigner.recOrder_offline_06232021 import Ui_Form
from recOrder.viewer.viewer_manager import SignalManager
from recOrder.viewer.mappings import GUI_TO_CONFIG, DEFAULT_CONFIG
import yaml
import ast


class OfflineReconstructionGUI(QWidget, Ui_Form):

    def __init__(self, napari_viewer):
        super().__init__()
        self.viewer = napari_viewer
        self.setupUi(self)

        self.config_path = None

        # connect to buttons
        SignalManager('offline', self, self)
        # self.ui.qbutton_browse_config_file.clicked[bool].connect(self.set_config_load_path)

    @property
    def config_path(self):
        return self._config_file_path

    @config_path.setter
    def config_path(self, filename):
        self._config_file_path = filename
        self.le_path_to_config.setText(filename)

    # ==================================
    # FILE BROWSER TOOLS
    # ==================================
    def _open_folder_dialog(self, default_path):
        return self._open_dialog("select a folder",
                                 default_path,
                                 kind='Folder')

    # returns a list of file names
    def _open_file_dialog(self, default_path):
        return self._open_dialog("select a yml file",
                                 default_path,
                                 kind='File')[0]

    def _open_dialog(self, title, ref, kind='Folder'):
        options = QFileDialog.Options()

        options |= QFileDialog.DontUseNativeDialog
        if kind == 'Folder':
            path = QFileDialog.getExistingDirectory(None,
                                                    title,
                                                    ref,
                                                    options=options)
        elif kind == 'File':
            path = QFileDialog.getOpenFileName(None,
                                               title,
                                               ref,
                                               options=options)
        else:
            raise TypeError("keyword 'kind' required for dialog")
        return path

    def _save_dialog(self, title, ref):
        options = QFileDialog.Options()

        options |= QFileDialog.DontUseNativeDialog
        file = QFileDialog.getSaveFileName(None,
                                           title,
                                           ref,
                                           options=options)
        return file[0]

    # ==================================
    # DIALOG BOX WIDGET
    # ==================================

    def _warning_dialog(self, message: str):
        msg = QtWidgets.QMessageBox()
        msg.setIcon(QtWidgets.QMessageBox.Critical)
        buttonReply = msg.warning(None,
                                  "recOrder Warning Popup", message,
                                  QtWidgets.QMessageBox.Ok)

    def _warning_dialog_choice(self, message: str):
        msg = QtWidgets.QMessageBox()
        msg.setIcon(QtWidgets.QMessageBox.Critical)
        buttonReply = msg.warning(None,
                                  "recOrder Warning Popup", message,
                                  QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
        return buttonReply == QtWidgets.QMessageBox.Ok

    # =============================================================
    # ==================== OFFLINE recon methods ==================

    @pyqtSlot(bool)
    def set_config_load_path(self):
        """
        Opens a FOLDER browser dialog
        :return:
        """
        print("CONNECTED SIGNAL")
        self.le_path_to_config.setFocus()
        result = self._open_file_dialog(self.config_path)

        # check that file is .yml type
        if '.yml' not in result:
            if self._warning_dialog_choice("configuration files must be of type .yml, continue?"):
                self.config_path = result
                print("Config folder path changed to = "+str(self.config_path))
            else:
                return
        else:
            self.config_path = result

    @pyqtSlot(bool)
    def load_configuration_file(self):
        if self.config_path:
            # different pattern now:
            # this function now ONLY populates the GUI, does not populate the self.config
            with open(self.config_path, 'r') as f:
                yaml_config = yaml.load(f)
            if 'dataset' in yaml_config:
                self._assign_gui_from_config(yaml_config['dataset'])
            if 'processing' in yaml_config:
                self._assign_gui_from_config(yaml_config['processing'])
            if 'plotting' in yaml_config:
                self._assign_gui_from_config(yaml_config['plotting'])
        else:
            print("no config folder defined")
            # self.log_area.append("no config folder defined")
            self.logger.add_to_log('no config folder defined')
            return

    @pyqtSlot(bool)
    def load_default_config(self):
        self._assign_gui_from_config(DEFAULT_CONFIG)

    @pyqtSlot(bool)
    def save_configuration_file(self):
        """
        open a dialog box to navigate to a save path

        :return:
        """
        # result = self._open_file_dialog(self.config_path)
        result = self._save_dialog('save configuration file as .yml', self.config_path)
        # check that file is .yml type
        if '.yml' not in result and result:
            if self._warning_dialog("configuration files must be of type .yml, continue?"):
                self.config_path = result
                print("Config folder path changed to = "+str(self.config_path))
        if '.yml' in result and result:
            self.config_path = result
            try:
                # creates the self.config file and assigns it GUI values
                self._assign_config_from_gui()

                # writes the gui values
                self.config.write_config(self.config_path)

                self._warning_dialog(f"save {result} complete")

            except Exception as ex:
                self._warning_dialog(f"error writing config file : {ex}")
                self.logger.add_to_log("Excepting writing yaml config to disk + %s" % ex)
        else:
            print('no config file save path selected')

        # if self.config_save_path:
        #     try:
        #         # creates the self.config file and assigns it GUI values
        #         self._assign_config_from_gui()
        #
        #         # writes the gui values
        #         self.config.write_config(self.config_save_path)
        #
        #     except Exception as ex:
        #         self.logger.add_to_log("Excepting writing yaml config to disk + %s" % ex)
        # else:
        #     print('no config file save path defined')
        #     return

    def _assign_gui_from_config(self, config_dict):
        """
        updates the GUI with CONFIG values

        :param config_dict: dictionary
            usually from yaml

        :return:
        """

        # invert the key/value pair of the GUI_to_CONFIG
        config_to_gui = {v: k for k, v in GUI_TO_CONFIG.items()}

        for key, default_value in config_dict.items():
            try:
                # gui_element should be a QLineEdit
                gui_element = getattr(self, config_to_gui[key])
                if isinstance(gui_element, QtWidgets.QRadioButton):
                    gui_element.setChecked(default_value)
                elif isinstance(gui_element, QtWidgets.QComboBox):
                    if default_value == "Tikhonov":
                        gui_element.setCurrentIndex(0)
                    else:
                        gui_element.setCurrentIndex(1)
                else:
                    gui_element.setText(str(default_value))
            except AttributeError as ae:
                self.logger.add_to_log(str(ae))
                self.log_area.update()
                continue
            except Exception as ex:
                print(ex)
                continue

    def _assign_config_from_gui(self):
        """
        updates the CONFIG with values from the GUI

        :param gui: A Qt-object that contains GUI elements

        :return:
        """
        # should not be initialized yet
        # todo, use new config reader
        # self.config = ConfigReader()

        # iterate through all GUI fields and update the self.config appropriately
        for attr, config_attr in GUI_TO_CONFIG.items():
            try:
                # gui_element should be a QLineEdit, QRadioButton, or QComboBox
                gui_element = getattr(self, attr)
                if isinstance(gui_element, QtWidgets.QRadioButton) and gui_element.isChecked():
                    config_value = True
                elif isinstance(gui_element, QtWidgets.QRadioButton) and not gui_element.isChecked():
                    config_value = False
                elif isinstance(gui_element, QtWidgets.QComboBox) and gui_element.currentIndex() == 0:
                    config_value = 'Tikhonov'
                elif isinstance(gui_element, QtWidgets.QComboBox) and gui_element.currentIndex() == 1:
                    config_value = 'TV'
                else:
                    try:
                        config_value = ast.literal_eval(gui_element.text())
                    except ValueError as ve:
                        config_value = gui_element.text()
                    except SyntaxError as se:
                        config_value = gui_element.text()

                if config_value is None or config_value is '' or config_value is []:
                    continue

                # try to set the config value here, might throw exception
                if hasattr(self.config.dataset, config_attr):
                    setattr(self.config.dataset, config_attr, config_value)
                elif hasattr(self.config.processing, config_attr):
                    setattr(self.config.processing, config_attr, config_value)
                elif hasattr(self.config.plotting, config_attr):
                    setattr(self.config.plotting, config_attr, config_value)

            except AttributeError as ae:
                self.logger.add_to_log(str(ae))
                # self._warning_dialog(f"AttributeError creating ConfigReader. \n{ae}")
                raise AttributeError(f"AttributeError creating ConfigReader. \n{ae}")
            except Exception as ex:
                print("Error populating config from GUI "+str(ex))
                # self._warning_dialog(f"General Exception creating ConfigReader. \n{ex}")
                raise Exception(f"General Exception creating ConfigReader. \n{ex}")

