from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QFileDialog, QAction
from PyQt5.QtCore import pyqtSlot


class OfflineRecon:

    def __init__(self, parent):
        self.parent = parent

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

    @pyqtSlot(bool)
    def set_config_load_path(self):
        """
        Opens a FOLDER browser dialog
        :return:
        """
        print("CONNECTED SIGNAL")
        self.parent.le_path_to_config.setFocus()
        result = self._open_file_dialog(self.parent.config_path)

        # check that file is .yml type
        if '.yml' not in result:
            if self._warning_dialog_choice("configuration files must be of type .yml, continue?"):
                self.parent.config_path = result
                print("Config folder path changed to = "+str(self.parent.config_path))
            else:
                return
        else:
            self.parent.config_path = result



