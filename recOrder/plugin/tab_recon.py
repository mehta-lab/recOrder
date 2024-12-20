import os, json, subprocess, time, datetime, uuid
from pathlib import Path

from qtpy import QtCore
from qtpy.QtCore import Qt, QEvent, QThread
from qtpy.QtWidgets import *
from magicgui.widgets import *
from PyQt6.QtCore import pyqtSignal

from iohub.ngff import Plate, open_ome_zarr
from natsort import natsorted

from typing import List, Literal, Union, Final, Annotated
from magicgui import widgets
from magicgui.type_map import get_widget_class
import warnings

from recOrder.io import utils
from recOrder.cli import settings, main, jobs_mgmt
from napari.utils import notifications

from concurrent.futures import ThreadPoolExecutor

import importlib.metadata

import pydantic.v1, pydantic
from pydantic.v1 import (
    BaseModel,
    Extra,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveFloat,
    root_validator,
    validator,
)

try:
    # Use version specific pydantic import for ModelMetaclass
    # prefer to pin to 1.10.19
    version = importlib.metadata.version('pydantic')    
    # print("Your Pydantic library ver:{v}.".format(v=version))
    if version >= "2.0.0":
        print("Your Pydantic library ver:{v}. Recommended ver is: 1.10.19".format(v=version))
        from pydantic.main import ModelMetaclass
        from pydantic.main import ValidationError
        from pydantic.main import BaseModel
    elif version >= "1.10.19":
        from pydantic.main import ModelMetaclass
        from pydantic.main import ValidationError
        from pydantic.main import BaseModel
    else:
        print("Your Pydantic library ver:{v}. Recommended ver is: 1.10.19".format(v=version))
        from pydantic.v1.main import ModelMetaclass
        from pydantic.v1.main import ValidationError
        from pydantic.v1.main import BaseModel
except:
    print("Pydantic library was not found. Ver 1.10.19 is recommended.")

STATUS_submitted_pool = "Submitted_Pool"
STATUS_submitted_job = "Submitted_Job"
STATUS_running_pool = "Running_Pool"
STATUS_running_job = "Running_Job"
STATUS_finished_pool = "Finished_Pool"
STATUS_finished_job = "Finished_Job"
STATUS_errored_pool = "Errored_Pool"
STATUS_errored_job = "Errored_Job"
STATUS_user_cleared_job = "User_Cleared_Job"

MSG_SUCCESS = {'msg':'success'}
JOB_COMPLETION_STR = "Job completed successfully"
JOB_RUNNING_STR = "Starting with JobEnvironment"
JOB_TRIGGERED_EXC = "Submitted job triggered an exception"

_validate_alert = '⚠'
_validate_ok = '✔️'

# For now replicate CLI processing modes - these could reside in the CLI settings file as well
# for consistency
OPTION_TO_MODEL_DICT = {
    "birefringence": {"enabled":False, "setting":None},
    "phase": {"enabled":False, "setting":None},
    "fluorescence": {"enabled":False, "setting":None},
}

CONTAINERS_INFO = {}

# This keeps an instance of the MyWorker server that is listening
# napari will not stop processes and the Hide event is not reliable
HAS_INSTANCE = {"val": False, "instance": None}

# Main class for the Reconstruction tab
# Not efficient since instantiated from GUI
# Does not have access to common functions in main_widget
# ToDo : From main_widget and pass self reference
class Ui_ReconTab_Form(QWidget):
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._ui = parent

        if HAS_INSTANCE["val"]:
            self.current_dir_path = str(Path.cwd())
            self.current_save_path = HAS_INSTANCE["current_save_path"]
            self.input_directory = HAS_INSTANCE["input_directory"]
            self.save_directory = HAS_INSTANCE["save_directory"]
            self.model_directory = HAS_INSTANCE["model_directory"]
            self.yaml_model_file = HAS_INSTANCE["yaml_model_file"]
        else:
            self.current_dir_path = str(Path.cwd())
            self.current_save_path = str(Path.cwd())
            self.input_directory = str(Path.cwd())
            self.save_directory = str(Path.cwd())
            self.model_directory = str(Path.cwd())
            self.yaml_model_file = str(Path.cwd())   
        
        self.input_directory_dataset = None
        self.input_directory_datasetMeta = None

        # Top level parent
        self.recon_tab_widget = QWidget()
        self.recon_tab_layout = QVBoxLayout()
        self.recon_tab_layout.setAlignment(Qt.AlignTop)
        self.recon_tab_layout.setContentsMargins(0,0,0,0)
        self.recon_tab_layout.setSpacing(0) 
        self.recon_tab_widget.setLayout(self.recon_tab_layout)     

         # Top level - Data Input
        self.modes_widget2 = QWidget()
        self.modes_layout2 = QHBoxLayout()
        self.modes_layout2.setAlignment(Qt.AlignTop)
        self.modes_widget2.setLayout(self.modes_layout2)
        self.modes_widget2.setMaximumHeight(50)
        self.modes_widget2.setMinimumHeight(50)          

        self.reconstruction_input_data_loc = widgets.LineEdit(
                name="",
                value=self.input_directory
        )
        self.reconstruction_input_data_btn = widgets.PushButton(
                name="InputData",
                label="Input Data"
        )
        self.reconstruction_input_data_btn.clicked.connect(self.browse_dir_path_input)
        self.reconstruction_input_data_loc.changed.connect(self.readAndSetInputPathOnValidation)

        self.modes_layout2.addWidget(self.reconstruction_input_data_loc.native)
        self.modes_layout2.addWidget(self.reconstruction_input_data_btn.native)
        self.recon_tab_layout.addWidget(self.modes_widget2) 
                
        # Top level - Selection modes, model creation and running
        self.modes_widget = QWidget()
        self.modes_layout = QHBoxLayout()
        self.modes_layout.setAlignment(Qt.AlignTop)
        self.modes_widget.setLayout(self.modes_layout)
        self.modes_widget.setMaximumHeight(50)
        self.modes_widget.setMinimumHeight(50)
                        
        self.modes_selected = OPTION_TO_MODEL_DICT.copy()

        # Make a copy of the Reconstruction settings mode, these will be used as template
        for mode in self.modes_selected.keys():
            self.modes_selected[mode]["setting"] = None

        # Checkboxes for the modes to select single or combination of modes
        for mode in self.modes_selected.keys():
            self.modes_selected[mode]["Checkbox"] = widgets.Checkbox(
                name=mode,
                label=mode
            )
            self.modes_layout.addWidget(self.modes_selected[mode]["Checkbox"].native)

        # PushButton to create a copy of the model - UI
        self.reconstruction_mode_enabler = widgets.PushButton(
                name="CreateModel",
                label="Create Model"
        )
        self.reconstruction_mode_enabler.clicked.connect(self._create_acq_contols)

        # PushButton to validate and create the yaml file(s) based on selection
        self.build_button = widgets.PushButton(name="Build && Run Model")
        self.build_button.clicked.connect(self.build_model_and_run)
        
        # PushButton to clear all copies of models that are create for UI
        self.reconstruction_mode_clear = widgets.PushButton(
                name="ClearModels",
                label="Clear All Models"
        )
        self.reconstruction_mode_clear.clicked.connect(self._clear_all_models)

        # Editable List holding pydantic class(es) as per user selection
        self.pydantic_classes = list()
        self.index = 0

        self.modes_layout.addWidget(self.reconstruction_mode_enabler.native)
        self.modes_layout.addWidget(self.build_button.native)
        self.modes_layout.addWidget(self.reconstruction_mode_clear.native)
        self.recon_tab_layout.addWidget(self.modes_widget)

        _load_model_loc = widgets.LineEdit(
                name="",
                value=self.model_directory
        )
        _load_model_btn = widgets.PushButton(
                name="LoadModel",
                label="Load Model"
        )        

        # Passing model location label to model location selector
        _load_model_btn.clicked.connect(lambda: self.browse_dir_path_model(_load_model_loc))

        _clear_results_btn = widgets.PushButton(
                name="ClearResults",
                label="Clear Results"
        )
        _clear_results_btn.clicked.connect(self.clear_results_table)
        
        # HBox for Loading Model
        _hBox_widget_model = QWidget()
        _hBox_layout_model = QHBoxLayout()
        _hBox_layout_model.setAlignment(Qt.AlignTop)
        _hBox_widget_model.setLayout(_hBox_layout_model)
        _hBox_widget_model.setMaximumHeight(50)
        _hBox_widget_model.setMinimumHeight(50)
        _hBox_layout_model.addWidget(_load_model_loc.native)
        _hBox_layout_model.addWidget(_load_model_btn.native)
        _hBox_layout_model.addWidget(_clear_results_btn.native)
        self.recon_tab_layout.addWidget(_hBox_widget_model)

        # Line seperator between pydantic UI components
        _line = QFrame()
        _line.setMinimumWidth(1)
        _line.setFixedHeight(2)
        _line.setFrameShape(QFrame.HLine)
        _line.setFrameShadow(QFrame.Sunken)
        _line.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        _line.setStyleSheet("margin:1px; padding:2px; border:1px solid rgb(128,128,128); border-width: 1px;")
        self.recon_tab_layout.addWidget(_line)
        
        # Top level - Central scrollable component which will hold Editable/(vertical) Expanding UI
        self.recon_tab_scrollArea_settings = QScrollArea()
        # self.recon_tab_scrollArea_settings.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.recon_tab_scrollArea_settings.setWidgetResizable(True)
        self.recon_tab_qwidget_settings = QWidget()
        self.recon_tab_qwidget_settings_layout = QVBoxLayout()
        self.recon_tab_qwidget_settings_layout.setSpacing(10)
        self.recon_tab_qwidget_settings_layout.setAlignment(Qt.AlignTop)
        self.recon_tab_qwidget_settings.setLayout(self.recon_tab_qwidget_settings_layout)
        self.recon_tab_scrollArea_settings.setWidget(self.recon_tab_qwidget_settings)
        self.recon_tab_layout.addWidget(self.recon_tab_scrollArea_settings)

        _line2 = QFrame()
        _line2.setMinimumWidth(1)
        _line2.setFixedHeight(2)
        _line2.setFrameShape(QFrame.HLine)
        _line2.setFrameShadow(QFrame.Sunken)
        _line2.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        _line2.setStyleSheet("margin:1px; padding:2px; border:1px solid rgb(128,128,128); border-width: 1px;")
        self.recon_tab_layout.addWidget(_line2)
        
        _scrollArea = QScrollArea()
        # _scrollArea.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        _scrollArea.setWidgetResizable(True)   
        _scrollArea.setMaximumHeight(200)     
        _qwidget_settings = QWidget()
        _qwidget_settings_layout = QVBoxLayout()
        _qwidget_settings_layout.setAlignment(Qt.AlignTop)
        _qwidget_settings.setLayout(_qwidget_settings_layout)
        _scrollArea.setWidget(_qwidget_settings)
        self.recon_tab_layout.addWidget(_scrollArea)

        # Table for processing entries
        self.proc_table_QFormLayout = QFormLayout()
        self.proc_table_QFormLayout.setSpacing(0)
        self.proc_table_QFormLayout.setContentsMargins(0,0,0,0)
        _proc_table_widget = QWidget()
        _proc_table_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        _proc_table_widget.setLayout(self.proc_table_QFormLayout)
        _qwidget_settings_layout.addWidget(_proc_table_widget)   

        # Stores Model & Components values which cause validation failure - can be highlighted on the model field as Red
        self.modelHighlighterVals = {}

        # Flag to delete Process update table row on successful Job completion
        # self.autoDeleteRowOnCompletion = True

        # handle napari's close widget and avoid starting a second server
        if HAS_INSTANCE["val"]:
            self.worker:MyWorker = HAS_INSTANCE["MyWorker"]
            self.worker.setNewInstances(self.proc_table_QFormLayout, self, self._ui)
        else:
            self.worker = MyWorker(self.proc_table_QFormLayout, self, self._ui)
            HAS_INSTANCE["val"] = True
            HAS_INSTANCE["MyWorker"] = self.worker

        app = QApplication.instance()
        app.lastWindowClosed.connect(self.myCloseEvent)  # this line is connection to signal close        

    # our defined close event since napari doesnt do
    def myCloseEvent(self):
        event = QEvent(QEvent.Type.Close)
        self.closeEvent(event)

    # on napari close - cleanup
    def closeEvent(self, event):
        if event.type() == QEvent.Type.Close:
            self.worker.stopServer()

    def hideEvent(self, event):
        if event.type() == QEvent.Type.Hide and (self._ui is not None and self._ui.isVisible()):
            pass

    def showEvent(self, event):
        if event.type() == QEvent.Type.Show:
            pass

    def confirmDialog(self):
        qm = QMessageBox
        ret = qm.question(self.recon_tab_widget, "Confirm", "Confirm your selection ?", qm.Yes | qm.No)
        if ret == qm.Yes:
            return True
        else:
            return False

    # Copied from main_widget
    # ToDo: utilize common functions
    # Input data selector
    def browse_dir_path_input(self):
        result = self._open_file_dialog(self.input_directory, "dir")
        if result == '':
            return
        
        ret, ret_msg = self.validateInputData(result)
        if not ret:
            self.messageBox(ret_msg)
            return

        self.directory = result
        self.current_dir_path = result
        self.input_directory = result
        self.reconstruction_input_data_loc.value = result

        self.saveLastPaths()

    def browse_dir_path_inputBG(self, elem):
        result = self._open_file_dialog(self.directory, "dir")
        if result == '':
            return
        
        ret, ret_msg = self.validateInputData(result)
        if not ret:
            self.messageBox(ret_msg)
            return

        elem.value = result

    # not working - not used
    def validateInputData(self, input_data_folder: str, metadata=False) -> bool:
        # Sort and validate the input paths, expanding plates into lists of positions
        # return True, MSG_SUCCESS
        try:
            input_paths = Path(input_data_folder)
            with open_ome_zarr(input_paths, mode="r") as dataset:
                # ToDo: Metadata reading and implementation in GUI for
                # channel names, time indicies, etc.
                if metadata:
                    self.input_directory_dataset = dataset       
                return True, MSG_SUCCESS
            raise Exception("Dataset does not appear to be a valid ome-zarr storage")
        except Exception as exc:
            return False, exc.args

    # call back for input LineEdit path changed manually
    # include data validation
    def readAndSetInputPathOnValidation(self):
        if self.reconstruction_input_data_loc.value is None or len(self.reconstruction_input_data_loc.value) == 0:
            self.reconstruction_input_data_loc.value = self.input_directory
            self.messageBox("Input data path cannot be empty")
            return
        if not Path(self.reconstruction_input_data_loc.value).exists():
            self.reconstruction_input_data_loc.value = self.input_directory
            self.messageBox("Input data path must point to a valid location")
            return
        
        result = self.reconstruction_input_data_loc.value
        valid, ret_msg = self.validateInputData(result)

        if valid:
            self.directory = result
            self.current_dir_path = result
            self.input_directory = result

            self.saveLastPaths()
        else:
            self.reconstruction_input_data_loc.value = self.input_directory
            self.messageBox(ret_msg)

    # Copied from main_widget
    # ToDo: utilize common functions
    # Output data selector
    def browse_dir_path_output(self, elem):
        result = self._open_file_dialog(self.save_directory, "save")
        if result == '':
            return
        self.directory = result
        self.save_directory = result
        elem.value = self.save_directory

        self.saveLastPaths()

    # call back for output LineEdit path changed manually
    def readAndSetOutputPathOnValidation(self, elem):
        if elem.value is None or len(elem.value) == 0:
            elem.value = self.input_directory
            return        
        result = elem.value
        self.directory = result
        self.save_directory = result

        self.saveLastPaths()

    # Copied from main_widget
    # ToDo: utilize common functions
    # Output data selector
    def browse_dir_path_model(self, elem):
        results = self._open_file_dialog(self.model_directory, "files") # returns list
        if len(results) == 0 or results == '':
            return
        
        self.model_directory = str(Path(results[0]).parent.absolute())
        self.directory = self.model_directory
        self.current_dir_path = self.model_directory

        self.saveLastPaths()

        pydantic_models = list()
        for result in results:
            self.yaml_model_file = result
            elem.value = self.yaml_model_file

            with open(result, 'r') as yaml_in:
                yaml_object = utils.yaml.safe_load(yaml_in) # yaml_object will be a list or a dict
            jsonString = json.dumps(self.convert(yaml_object))
            json_out = json.loads(jsonString)
            json_dict = dict(json_out)

            selected_modes = list(OPTION_TO_MODEL_DICT.copy().keys())
            exclude_modes = list(OPTION_TO_MODEL_DICT.copy().keys())

            for k in range(len(selected_modes)-1, -1, -1):
                if selected_modes[k] in json_dict.keys():
                    exclude_modes.pop(k)
                else:
                    selected_modes.pop(k)

            pruned_pydantic_class, ret_msg = self.buildModel(selected_modes)
            if pruned_pydantic_class is None:
                self.messageBox(ret_msg)
                return        

            pydantic_model, ret_msg = self.get_model_from_file(self.yaml_model_file)
            if pydantic_model is None:
                if isinstance(ret_msg, List) and len(ret_msg)==2 and len(ret_msg[0]["loc"])==3 and ret_msg[0]["loc"][2] == "background_path":
                    pydantic_model = pruned_pydantic_class # if only background_path fails validation
                    json_dict["birefringence"]["apply_inverse"]["background_path"] = ""
                    self.messageBox("background_path:\nPath was invalid and will be reset")
                else:
                    self.messageBox(ret_msg)
                    return
            else:
                # make sure "background_path" is valid
                bg_loc = json_dict["birefringence"]["apply_inverse"]["background_path"]
                if bg_loc != "":
                    extension = os.path.splitext(bg_loc)[1]
                    if len(extension) > 0:
                        bg_loc = Path(os.path.join(str(Path(bg_loc).parent.absolute()),"background.zarr"))
                    else:
                        bg_loc = Path(os.path.join(bg_loc, "background.zarr"))
                    if not bg_loc.exists() or not self.validateInputData(str(bg_loc)):
                        self.messageBox("background_path:\nPwas invalid and will be reset")
                        json_dict["birefringence"]["apply_inverse"]["background_path"] = ""
                    else:
                        json_dict["birefringence"]["apply_inverse"]["background_path"] = str(bg_loc.parent.absolute())
            
            pydantic_model = self._create_acq_contols2(selected_modes, exclude_modes, pydantic_model, json_dict)
            if pydantic_model is None:
                self.messageBox("Error - pydantic model returned None")
                return
            
            pydantic_models.append(pydantic_model)
        
        return pydantic_models
    
    # useful when using close widget and not napari close and we might need them again
    def saveLastPaths(self):
        HAS_INSTANCE["current_dir_path"] = self.current_dir_path
        HAS_INSTANCE["current_save_path"] = self.current_save_path
        HAS_INSTANCE["input_directory"] = self.input_directory
        HAS_INSTANCE["save_directory"] = self.save_directory
        HAS_INSTANCE["model_directory"] = self.model_directory
        HAS_INSTANCE["yaml_model_file"] = self.yaml_model_file
    
    # clears the results table
    def clear_results_table(self):
        if self.confirmDialog():
            for i in range(self.proc_table_QFormLayout.rowCount()):
                self.proc_table_QFormLayout.removeRow(0)

    def removeRow(self, row, expID):
        try:
            if row < self.proc_table_QFormLayout.rowCount():
                widgetItem = self.proc_table_QFormLayout.itemAt(row)
                if widgetItem is not None:
                    name_widget = widgetItem.widget()
                    toolTip_string = str(name_widget.toolTip)
                    if expID in toolTip_string:
                        self.proc_table_QFormLayout.removeRow(row) # removeRow vs takeRow for threads ?
        except Exception as exc:
            print(exc.args)
    
    # marks fields on the Model that cause a validation error
    def modelHighlighter(self, errs):
        try:
            for uid in errs.keys():
                self.modelHighlighterVals[uid] = {}
                container = errs[uid]["cls"]
                self.modelHighlighterVals[uid]["errs"] = errs[uid]["errs"]
                self.modelHighlighterVals[uid]["items"] = []
                self.modelHighlighterVals[uid]["tooltip"] = []
                if len(errs[uid]["errs"]) > 0:
                    self.modelHighlighterSetter(errs[uid]["errs"], container, uid)
        except Exception as exc:
            print(exc.args)
            # more of a test feature - no need to show up

    # format all model errors into a display format for napari error message box
    def formatStringForErrorDisplay(self, errs):
        try:
            ret_str = ""
            for uid in errs.keys():
                if len(errs[uid]["errs"]) > 0:
                    ret_str += errs[uid]["collapsibleBox"] + "\n"
                    for idx in range(len(errs[uid]["errs"])):
                        ret_str += f"{'>'.join(errs[uid]['errs'][idx]['loc'])}:\n{errs[uid]['errs'][idx]['msg']} \n"
                    ret_str += "\n"
            return ret_str
        except Exception as exc:
            return ret_str

    # recursively fix the container for highlighting
    def modelHighlighterSetter(self, errs, container:Container, containerID, lev=0):
        try:
            layout = container.native.layout()
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item.widget():
                    widget = layout.itemAt(i).widget()
                    if (not isinstance(widget._magic_widget, CheckBox) and not isinstance(widget._magic_widget, PushButton)) and not isinstance(widget._magic_widget, LineEdit) and isinstance(widget._magic_widget._inner_widget, Container) and not (widget._magic_widget._inner_widget is None):
                        self.modelHighlighterSetter(errs, widget._magic_widget._inner_widget, containerID, lev+1)
                    else:
                        for idx in range(len(errs)):
                            if len(errs[idx]["loc"])-1 < lev:
                                pass
                            elif isinstance(widget._magic_widget, CheckBox) or isinstance(widget._magic_widget, LineEdit)  or isinstance(widget._magic_widget, PushButton):
                                if widget._magic_widget.label == errs[idx]["loc"][lev].replace("_", " "):
                                    if widget._magic_widget.tooltip is None:
                                        widget._magic_widget.tooltip = "-\n"
                                        self.modelHighlighterVals[containerID]["items"].append(widget._magic_widget)
                                        self.modelHighlighterVals[containerID]["tooltip"].append(widget._magic_widget.tooltip)
                                    widget._magic_widget.tooltip += errs[idx]["msg"] + "\n"
                                    widget._magic_widget.native.setStyleSheet("border:1px solid rgb(255, 255, 0); border-width: 1px;")                                    
                            elif widget._magic_widget._label_widget.value == errs[idx]["loc"][lev].replace("_", " "):
                                if widget._magic_widget._label_widget.tooltip is None:
                                    widget._magic_widget._label_widget.tooltip = "-\n"
                                    self.modelHighlighterVals[containerID]["items"].append(widget._magic_widget._label_widget)
                                    self.modelHighlighterVals[containerID]["tooltip"].append(widget._magic_widget._label_widget.tooltip)
                                widget._magic_widget._label_widget.tooltip += errs[idx]["msg"] + "\n"
                                widget._magic_widget._label_widget.native.setStyleSheet("border:1px solid rgb(255, 255, 0); border-width: 1px;")                                
                                if widget._magic_widget._inner_widget.tooltip is None:
                                    widget._magic_widget._inner_widget.tooltip = "-\n"      
                                    self.modelHighlighterVals[containerID]["items"].append(widget._magic_widget._inner_widget)
                                    self.modelHighlighterVals[containerID]["tooltip"].append(widget._magic_widget._inner_widget.tooltip)                    
                                widget._magic_widget._inner_widget.tooltip += errs[idx]["msg"] + "\n"
                                widget._magic_widget._inner_widget.native.setStyleSheet("border:1px solid rgb(255, 255, 0); border-width: 1px;")                                
        except Exception as exc:
            print(exc.args)
            # more of a test feature - no need to show up

    # recursively fix the container for highlighting
    def modelResetHighlighterSetter(self):
        try:
            for containerID in self.modelHighlighterVals.keys():
                items = self.modelHighlighterVals[containerID]["items"]
                tooltip = self.modelHighlighterVals[containerID]["tooltip"]
                i=0
                for widItem in items:
                    # widItem.tooltip = None # let them tool tip remain
                    widItem.native.setStyleSheet("border:1px solid rgb(0, 0, 0); border-width: 0px;")
                    widItem.tooltip = tooltip[i]
                    i += 1
                                
        except Exception as exc:
            print(exc.args)
            # more of a test feature - no need to show up
                                
        except Exception as exc:
            print(exc.args)
            # more of a test feature - no need to show up

    # passes msg to napari notifications
    def messageBox(self, msg, type="exc"):
        if len(msg) > 0:            
            try:
                json_object = msg
                json_txt = ""
                for err in json_object:
                    json_txt = json_txt + "Loc: {loc}\nMsg:{msg}\nType:{type}\n\n".format(loc=err["loc"], msg=err["msg"], type=err["type"])
                json_txt = str(json_txt)
                # ToDo: format it better
                # formatted txt does not show up properly in msg-box ??
            except:
                json_txt = str(msg)

            # show is a message box
            if type == "exc":
                notifications.show_error(json_txt)
            else:
                notifications.show_info(json_txt)

    # adds processing entry to _qwidgetTabEntry_layout as row item
    # row item will be purged from table as processing finishes
    # there could be 3 tabs for this processing table status
    # Running, Finished, Errored 
    def addTableEntry(self, tableEntryID, tableEntryShortDesc, tableEntryVals, proc_params):
        
        _txtForInfoBox = "Updating {id}: Please wait...".format(id=tableEntryID)
        _scrollAreaCollapsibleBoxDisplayWidget = widgets.Label(value=_txtForInfoBox) # ToDo: Replace with tablular data and Stop button
        
        _scrollAreaCollapsibleBoxWidgetLayout = QVBoxLayout()
        _scrollAreaCollapsibleBoxWidgetLayout.addWidget(_scrollAreaCollapsibleBoxDisplayWidget.native)
        _scrollAreaCollapsibleBoxWidgetLayout.setAlignment(Qt.AlignTop)

        _scrollAreaCollapsibleBoxWidget = QWidget()
        _scrollAreaCollapsibleBoxWidget.setLayout(_scrollAreaCollapsibleBoxWidgetLayout)

        _scrollAreaCollapsibleBox = QScrollArea()
        _scrollAreaCollapsibleBox.setWidgetResizable(True)
        _scrollAreaCollapsibleBox.setMinimumHeight(200)
        _scrollAreaCollapsibleBox.setWidget(_scrollAreaCollapsibleBoxWidget)

        _collapsibleBoxWidgetLayout = QVBoxLayout()
        _collapsibleBoxWidgetLayout.setContentsMargins(0,0,0,0)
        _collapsibleBoxWidgetLayout.setSpacing(0)
        _collapsibleBoxWidgetLayout.addWidget(_scrollAreaCollapsibleBox)

        _collapsibleBoxWidget = CollapsibleBox(tableEntryID) # tableEntryID, tableEntryShortDesc - should update with processing status 
        _collapsibleBoxWidget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        _collapsibleBoxWidget.setContentLayout(_collapsibleBoxWidgetLayout)
        
        _expandingTabEntryWidgetLayout = QVBoxLayout()
        _expandingTabEntryWidgetLayout.addWidget(_collapsibleBoxWidget)

        _expandingTabEntryWidget = QWidget()
        _expandingTabEntryWidget.toolTip = tableEntryShortDesc
        _expandingTabEntryWidget.setLayout(_expandingTabEntryWidgetLayout)
        _expandingTabEntryWidget.layout().setContentsMargins(0,0,0,0)
        _expandingTabEntryWidget.layout().setSpacing(0)
        _expandingTabEntryWidget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        _scrollAreaCollapsibleBoxDisplayWidget.changed.connect(lambda: self.removeTableRow(_expandingTabEntryWidget, _scrollAreaCollapsibleBoxDisplayWidget))
        
        # instead of adding, insert at 0 to keep latest entry on top
        # self.proc_table_QFormLayout.addRow(_expandingTabEntryWidget)
        self.proc_table_QFormLayout.insertRow(0, _expandingTabEntryWidget)

        proc_params["table_layout"] = self.proc_table_QFormLayout
        proc_params["table_entry"] = _expandingTabEntryWidget
        proc_params["table_entry_infoBox"] = _scrollAreaCollapsibleBoxDisplayWidget

        self.worker.runInPool(proc_params)
        # result = self.worker.getResult(proc_params["exp_id"])
        # print(result)

    
    # Builds the model as required
    def buildModel(self, selected_modes):
        try:
            b = None
            p = None
            f = None
            chNames = ['State0']
            exclude_modes = ["birefringence", "phase", "fluorescence"]
            if "birefringence" in selected_modes and "phase" in selected_modes:
                b = settings.BirefringenceSettings()
                p = settings.PhaseSettings()
                chNames = ['State0','State1','State2','State3']
                exclude_modes = ["fluorescence"]
            elif "birefringence" in selected_modes:
                b = settings.BirefringenceSettings()
                chNames = ['State0','State1','State2','State3']
                exclude_modes = ["fluorescence", "phase"]
            elif "phase" in selected_modes:
                p = settings.PhaseSettings()
                exclude_modes = ["birefringence", "fluorescence"]
            elif "fluorescence" in selected_modes:
                f = settings.FluorescenceSettings()
                exclude_modes = ["birefringence", "phase"]
            
            model = None
            try:
                model = settings.ReconstructionSettings(input_channel_names=chNames, birefringence=b, phase=p, fluorescence=f)
            except ValidationError as exc:
                # use v1 and v2 differ for ValidationError - newer one is not caught properly
                return None, exc.errors()
            
            model = self._fix_model(model, exclude_modes, 'input_channel_names', chNames)            
            return model, "+".join(selected_modes) + ": MSG_SUCCESS"
        
        except Exception as exc:
            return None, exc.args
        
    # ToDo: Temporary fix to over ride the 'input_channel_names' default value
    # Needs revisitation
    def _fix_model(self, model, exclude_modes, attr_key, attr_val):
        try:
            for mode in exclude_modes:
                model = settings.ReconstructionSettings.copy(model, exclude={mode}, deep=True, update={attr_key:attr_val})
            settings.ReconstructionSettings.__setattr__(model, attr_key, attr_val)
            if hasattr(model, attr_key):
                model.__fields__[attr_key].default = attr_val
                model.__fields__[attr_key].field_info.default = attr_val
        except Exception as exc:
            return print(exc.args)
        return model

    # Creates UI controls from model based on selections
    def _create_acq_contols(self):                                
        
        # Make a copy of selections and unsed for deletion
        selected_modes = []
        exclude_modes = []

        for mode in self.modes_selected.keys():
            enabled = self.modes_selected[mode]["Checkbox"].value
            if not enabled:
                exclude_modes.append(mode)
            else:
                selected_modes.append(mode)

        self._create_acq_contols2(selected_modes, exclude_modes)

    def _create_acq_contols2(self, selected_modes, exclude_modes, myLoadedModel=None, json_dict=None):
        
        # initialize the top container and specify what pydantic class to map from
        if myLoadedModel is not None:
            pydantic_class = myLoadedModel
        else:
            pydantic_class, ret_msg = self.buildModel(selected_modes)
            if pydantic_class is None:
                self.messageBox(ret_msg)
                return

        # Final constant UI val and identifier
        _idx: Final[int] = self.index
        _str: Final[str] = str(uuid.uuid4())

        # Container holding the pydantic UI components
        # Multiple instances/copies since more than 1 might be created
        recon_pydantic_container = widgets.Container(name=_str, scrollable=False)     

        self.add_pydantic_to_container(pydantic_class, recon_pydantic_container, exclude_modes, json_dict)

        # Run a validation check to see if the selected options are permitted
        # before we create the GUI
        # get the kwargs from the container/class
        pydantic_kwargs = {}
        pydantic_kwargs, ret_msg = self.get_and_validate_pydantic_args(recon_pydantic_container, pydantic_class, pydantic_kwargs, exclude_modes)
        if pydantic_kwargs is None:
            self.messageBox(ret_msg)
            return

        # For list element, this needs to be cleaned and parsed back as an array
        input_channel_names, ret_msg = self.clean_string_for_list("input_channel_names", pydantic_kwargs["input_channel_names"])
        if input_channel_names is None:
            self.messageBox(ret_msg)
            return
        pydantic_kwargs["input_channel_names"] = input_channel_names

        time_indices, ret_msg = self.clean_string_int_for_list("time_indices", pydantic_kwargs["time_indices"])
        if time_indices is None:
            self.messageBox(ret_msg)
            return
        pydantic_kwargs["time_indices"] = time_indices

        if "birefringence" in pydantic_kwargs.keys():
            background_path, ret_msg = self.clean_path_string_when_empty("background_path", pydantic_kwargs["birefringence"]["apply_inverse"]["background_path"])
            if background_path is None:
                self.messageBox(ret_msg)
                return
            pydantic_kwargs["birefringence"]["apply_inverse"]["background_path"] = background_path
    
        # validate and return errors if None
        pydantic_model, ret_msg = self.validate_pydantic_model(pydantic_class, pydantic_kwargs)
        if pydantic_model is None:
            self.messageBox(ret_msg)
            return

        # generate a json from the instantiated model, update the json_display
        # most of this will end up in a table as processing proceeds
        json_txt, ret_msg = self.validate_and_return_json(pydantic_model)
        if json_txt is None:
            self.messageBox(ret_msg)
            return
        
        # Line seperator between pydantic UI components
        _line = QFrame()
        _line.setMinimumWidth(1)
        _line.setFixedHeight(2)
        _line.setFrameShape(QFrame.HLine)
        _line.setFrameShadow(QFrame.Sunken)
        _line.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        _line.setStyleSheet("margin:1px; padding:2px; border:1px solid rgb(128,128,128); border-width: 1px;")   

        # PushButton to delete a UI container
        # Use case when a wrong selection of input modes get selected eg Bire+Fl
        # Preferably this root level validation should occur before values arevalidated
        # in order to display and avoid this to occur
        _del_button = widgets.PushButton(name="Delete this Model")        
        
        # Output Data location
        # These could be multiple based on user selection for each model
        # Inherits from Input by default at creation time
        _output_data_loc = widgets.LineEdit(
                name="",
                value=self.input_directory
        )
        _output_data_btn = widgets.PushButton(
                name="OutputData",
                label="Output Data"
        )
        
        # Passing location label to output location selector
        _output_data_btn.clicked.connect(lambda: self.browse_dir_path_output(_output_data_loc))
        _output_data_loc.changed.connect(lambda: self.readAndSetOutputPathOnValidation(_output_data_loc))

        # Passing all UI components that would be deleted
        _expandingTabEntryWidget = QWidget()
        _del_button.clicked.connect(lambda: self._delete_model(_expandingTabEntryWidget, recon_pydantic_container.native, _output_data_loc.native, _output_data_btn.native, _del_button.native, _line, _idx, _str))        
        
        c_mode = "-and-".join(selected_modes)
        if c_mode in CONTAINERS_INFO.keys():
            CONTAINERS_INFO[c_mode] += 1
        else:
            CONTAINERS_INFO[c_mode] = 1
        num_str =  "{:02d}".format(CONTAINERS_INFO[c_mode])
        c_mode_str = f"{c_mode} - {num_str}"

        # HBox for Output Data
        _hBox_widget = QWidget()
        _hBox_layout = QHBoxLayout()
        _hBox_layout.setAlignment(Qt.AlignTop)
        _hBox_widget.setLayout(_hBox_layout)
        _hBox_layout.addWidget(_output_data_loc.native)
        _hBox_layout.addWidget(_output_data_btn.native)

        # Add this container to the main scrollable widget
        _scrollAreaCollapsibleBoxWidgetLayout = QVBoxLayout()        
        _scrollAreaCollapsibleBoxWidgetLayout.setAlignment(Qt.AlignTop)

        _scrollAreaCollapsibleBoxWidget = QWidget()
        _scrollAreaCollapsibleBoxWidget.setLayout(_scrollAreaCollapsibleBoxWidgetLayout)

        _scrollAreaCollapsibleBox = QScrollArea()
        _scrollAreaCollapsibleBox.setWidgetResizable(True)
        _scrollAreaCollapsibleBox.setWidget(_scrollAreaCollapsibleBoxWidget)
        _scrollAreaCollapsibleBox.setMinimumHeight(500)

        _collapsibleBoxWidgetLayout = QVBoxLayout()
        _collapsibleBoxWidgetLayout.setContentsMargins(0,0,0,0)
        _collapsibleBoxWidgetLayout.setSpacing(0)
        _collapsibleBoxWidgetLayout.addWidget(_scrollAreaCollapsibleBox)

        _collapsibleBoxWidget = CollapsibleBox(c_mode_str) # tableEntryID, tableEntryShortDesc - should update with processing status 
        _collapsibleBoxWidget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        _collapsibleBoxWidget.setContentLayout(_collapsibleBoxWidgetLayout)
        
        _expandingTabEntryWidgetLayout = QVBoxLayout()
        _expandingTabEntryWidgetLayout.addWidget(_collapsibleBoxWidget)
        
        _expandingTabEntryWidget.toolTip = c_mode_str
        _expandingTabEntryWidget.setLayout(_expandingTabEntryWidgetLayout)
        _expandingTabEntryWidget.layout().setContentsMargins(0,0,0,0)
        _expandingTabEntryWidget.layout().setSpacing(0)
        _expandingTabEntryWidget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)        
        _expandingTabEntryWidget.layout().setAlignment(Qt.AlignTop)

        _scrollAreaCollapsibleBoxWidgetLayout.addWidget(recon_pydantic_container.native)
        _scrollAreaCollapsibleBoxWidgetLayout.addWidget(_hBox_widget)
        _scrollAreaCollapsibleBoxWidgetLayout.addWidget(_del_button.native)
        _scrollAreaCollapsibleBoxWidgetLayout.addWidget(_line)

        self.recon_tab_qwidget_settings_layout.addWidget(_expandingTabEntryWidget)

        # Store a copy of the pydantic container along with all its associated components and properties
        # We dont needs a copy of the class but storing for now
        # This will be used for making deletion edits and looping to create our final run output
        # uuid - used for identiying in editable list
        self.pydantic_classes.append({'uuid':_str, 'c_mode_str':c_mode_str, 'collapsibleBoxWidget':_collapsibleBoxWidget, 'class':pydantic_class, 'input':self.reconstruction_input_data_loc, 'output':_output_data_loc, 'container':recon_pydantic_container, 'selected_modes':selected_modes.copy(), 'exclude_modes':exclude_modes.copy()})
        self.index += 1

        if self.index > 1:
            self.build_button.text = "Build && Run {n} Models".format(n=self.index)
        else:
            self.build_button.text = "Build && Run Model"

        return pydantic_model

    # UI components deletion - maybe just needs the parent container instead of individual components
    def _delete_model(self, wid0, wid1, wid2, wid3, wid4, wid5, index, _str):

        if not self.confirmDialog():
            return False
        
        if wid5 is not None:
            wid5.setParent(None)
        if wid4 is not None:
            wid4.setParent(None)
        if wid3 is not None:
            wid3.setParent(None)
        if wid2 is not None:
            wid2.setParent(None)
        if wid1 is not None:
            wid1.setParent(None)
        if wid0 is not None:
            wid0.setParent(None)
        
        # Find and remove the class from our pydantic model list using uuid
        i=0
        for item in self.pydantic_classes:
            if item["uuid"] == _str:
                self.pydantic_classes.pop(i)
                break
        self.index = len(self.pydantic_classes)
        if self.index > 1:
            self.build_button.text = "Build && Run {n} Models".format(n=self.index)
        else:
            self.build_button.text = "Build && Run Model"

    # Clear all the generated pydantic models and clears the pydantic model list
    def _clear_all_models(self):
        if self.confirmDialog():
            index = self.recon_tab_qwidget_settings_layout.count()-1
            while(index >= 0):
                myWidget = self.recon_tab_qwidget_settings_layout.itemAt(index).widget()
                if myWidget is not None:
                    myWidget.setParent(None)
                index -=1
            self.pydantic_classes.clear()
            CONTAINERS_INFO.clear()
            self.index = 0
            self.build_button.text = "Build && Run Model"
    
    # Displays the json output from the pydantic model UI selections by user
    # Loops through all our stored pydantic classes
    def build_model_and_run(self):
        # we dont want to have a partial run if there are N models
        # so we will validate them all first and then run in a second loop
        # first pass for validating
        # second pass for creating yaml and processing

        self.modelResetHighlighterSetter() # reset the container elements that might be highlighted for errors
        _collectAllErrors = {}
        _collectAllErrorsBool = True
        for item in self.pydantic_classes:
            cls = item['class']
            cls_container = item['container']
            selected_modes = item['selected_modes']
            exclude_modes = item['exclude_modes']  
            uuid_str = item['uuid']  
            _collapsibleBoxWidget = item['collapsibleBoxWidget']
            c_mode_str = item['c_mode_str']

            _collectAllErrors[uuid_str] = {}
            _collectAllErrors[uuid_str]["cls"] = cls_container
            _collectAllErrors[uuid_str]["errs"] = []
            _collectAllErrors[uuid_str]["collapsibleBox"] = c_mode_str
            
            # build up the arguments for the pydantic model given the current container
            if cls is None:
                self.messageBox(ret_msg)
                return

            # get the kwargs from the container/class
            pydantic_kwargs = {}
            pydantic_kwargs, ret_msg = self.get_and_validate_pydantic_args(cls_container, cls, pydantic_kwargs, exclude_modes)            
            if pydantic_kwargs is None and not _collectAllErrorsBool:
                self.messageBox(ret_msg)
                return

            # For list element, this needs to be cleaned and parsed back as an array
            input_channel_names, ret_msg = self.clean_string_for_list("input_channel_names", pydantic_kwargs["input_channel_names"])
            if input_channel_names is None and not _collectAllErrorsBool:
                self.messageBox(ret_msg)
                return            
            pydantic_kwargs["input_channel_names"] = input_channel_names

            time_indices, ret_msg = self.clean_string_int_for_list("time_indices", pydantic_kwargs["time_indices"])
            if time_indices is None and not _collectAllErrorsBool:
                self.messageBox(ret_msg)
                return
            pydantic_kwargs["time_indices"] = time_indices

            if "birefringence" in pydantic_kwargs.keys():
                background_path, ret_msg = self.clean_path_string_when_empty("background_path", pydantic_kwargs["birefringence"]["apply_inverse"]["background_path"])
                if background_path is None and not _collectAllErrorsBool:
                    self.messageBox(ret_msg)
                    return
                pydantic_kwargs["birefringence"]["apply_inverse"]["background_path"] = background_path

            # validate and return errors if None
            pydantic_model, ret_msg = self.validate_pydantic_model(cls, pydantic_kwargs)
            if ret_msg == MSG_SUCCESS:
                _collapsibleBoxWidget.setNewName(f"{c_mode_str} {_validate_ok}")
            else:
                _collapsibleBoxWidget.setNewName(f"{c_mode_str} {_validate_alert}")
                _collectAllErrors[uuid_str]["errs"] = ret_msg
            if pydantic_model is None and not _collectAllErrorsBool:
                self.messageBox(ret_msg)
                return

            # generate a json from the instantiated model, update the json_display
            # most of this will end up in a table as processing proceeds
            json_txt, ret_msg = self.validate_and_return_json(pydantic_model)
            if json_txt is None and not _collectAllErrorsBool:
                self.messageBox(ret_msg)
                return
            
        # check if we collected any validation errors before continuing
        for uu_key in _collectAllErrors.keys():
            if len(_collectAllErrors[uu_key]["errs"]) > 0:
                self.modelHighlighter(_collectAllErrors)
                fmt_str = self.formatStringForErrorDisplay(_collectAllErrors)
                self.messageBox(fmt_str)
                return
        
        # generate a time-stamp for our yaml files to avoid overwriting
        # files generated at the same time will have an index suffix
        now = datetime.datetime.now()
        ms = now.strftime("%f")[:3]
        unique_id = now.strftime("%Y_%m_%d_%H_%M_%S_")+ms

        i = 0
        for item in self.pydantic_classes:
            i += 1
            cls = item['class']
            cls_container = item['container']
            selected_modes = item['selected_modes']
            exclude_modes = item['exclude_modes']
            c_mode_str = item['c_mode_str']

            # gather input/out locations
            input_dir = f"{item['input'].value}"
            output_dir = f"{item['output'].value}"

            # build up the arguments for the pydantic model given the current container
            if cls is None:
                self.messageBox(ret_msg)
                return

            pydantic_kwargs = {}
            pydantic_kwargs, ret_msg = self.get_and_validate_pydantic_args(cls_container, cls, pydantic_kwargs, exclude_modes)
            if pydantic_kwargs is None:
                self.messageBox(ret_msg)
                return

            input_channel_names, ret_msg = self.clean_string_for_list("input_channel_names", pydantic_kwargs["input_channel_names"])
            if input_channel_names is None:
                self.messageBox(ret_msg)
                return
            pydantic_kwargs["input_channel_names"] = input_channel_names

            time_indices, ret_msg = self.clean_string_int_for_list("time_indices", pydantic_kwargs["time_indices"])
            if time_indices is None:
                self.messageBox(ret_msg)
                return
            pydantic_kwargs["time_indices"] = time_indices

            time_indices, ret_msg = self.clean_string_int_for_list("time_indices", pydantic_kwargs["time_indices"])
            if time_indices is None:
                self.messageBox(ret_msg)
                return
            pydantic_kwargs["time_indices"] = time_indices

            if "birefringence" in pydantic_kwargs.keys():
                background_path, ret_msg = self.clean_path_string_when_empty("background_path", pydantic_kwargs["birefringence"]["apply_inverse"]["background_path"])
                if background_path is None:
                    self.messageBox(ret_msg)
                    return
                pydantic_kwargs["birefringence"]["apply_inverse"]["background_path"] = background_path

            # validate and return errors if None
            pydantic_model, ret_msg = self.validate_pydantic_model(cls, pydantic_kwargs)
            if pydantic_model is None:
                self.messageBox(ret_msg)
                return

            # generate a json from the instantiated model, update the json_display
            # most of this will end up in a table as processing proceeds
            json_txt, ret_msg = self.validate_and_return_json(pydantic_model)
            if json_txt is None:
                self.messageBox(ret_msg)
                return

            # save the yaml files
            # path is next to saved data location
            save_config_path = str(Path(output_dir).parent.absolute())
            yml_file_name = "-and-".join(selected_modes)
            yml_file = yml_file_name+"-"+unique_id+"-"+str(i)+".yml"
            config_path = os.path.join(save_config_path, yml_file)
            utils.model_to_yaml(pydantic_model, config_path)

            # Input params for table entry
            # Once ALL entries are entered we can deleted ALL model containers
            # Table will need a low priority update thread to refresh status queried from CLI
            # Table entries will be purged on completion when Result is returned OK
            # Table entries will show an error msg when processing finishes but Result not OK
            # Table fields ID / DateTime, Reconstruction type, Input Location, Output Location, Progress indicator, Stop button

            # addl_txt = "ID:" + unique_id + "-"+ str(i) + "\nInput:" + input_dir + "\nOutput:" + output_dir
            # self.json_display.value = self.json_display.value + addl_txt + "\n" + json_txt+ "\n\n"
            expID = "{tID}-{idx}".format(tID = unique_id, idx = i)
            tableID = "{tName}: ({tID}-{idx})".format(tName = c_mode_str, tID = unique_id, idx = i)
            tableDescToolTip = "{tName}: ({tID}-{idx})".format(tName = yml_file_name, tID = unique_id, idx = i)

            proc_params = {}
            proc_params["exp_id"] = expID
            proc_params["desc"] = tableDescToolTip
            proc_params["config_path"] = str(Path(config_path).absolute())
            proc_params["input_path"] = str(Path(input_dir).absolute())
            proc_params["output_path"] = str(Path(output_dir).absolute())
            proc_params["output_path_parent"] = str(Path(output_dir).parent.absolute())

            self.addTableEntry(tableID, tableDescToolTip, json_txt, proc_params)
                    
    # ======= These function do not implement validation
    # They simply make the data from GUI translate to input types
    # that the model expects: for eg. GUI txt field will output only str
    # when the model needs integers

    # util function to parse list elements displayed as string
    def remove_chars(self, string, chars_to_remove):
        for char in chars_to_remove:
            string = string.replace(char, '')
        return string

    # util function to parse list elements displayed as string
    def clean_string_for_list(self, field, string):
        chars_to_remove = ['[',']', '\'', '"', ' ']
        if isinstance(string, str):
            string = self.remove_chars(string, chars_to_remove)
        if len(string) == 0:
            return None, {'msg':field + ' is invalid'}        
        if ',' in string:
            string = string.split(',')
            return string, MSG_SUCCESS
        if isinstance(string, str):
            string = [string]
            return string, MSG_SUCCESS
        return string, MSG_SUCCESS
    
    # util function to parse list elements displayed as string, int, int as list of strings, int range
    # [1,2,3], 4,5,6 , 5-95
    def clean_string_int_for_list(self, field, string):
        chars_to_remove = ['[',']', '\'', '"', ' ']
        if Literal[string] == Literal["all"]:
            return string, MSG_SUCCESS
        if Literal[string] == Literal[""]:
                return string, MSG_SUCCESS        
        if isinstance(string, str):
            string = self.remove_chars(string, chars_to_remove)
        if len(string) == 0:
            return None, {'msg':field + ' is invalid'}        
        if '-' in string:
            string = string.split('-')
            if len(string) == 2:
                try:
                    x = int(string[0])
                    if not isinstance(x, int):
                        raise
                except Exception as exc:
                    return None, {'msg':field + ' first range element is not an integer'}
                try:
                    y = int(string[1])
                    if not isinstance(y, int):
                        raise
                except Exception as exc:
                    return None, {'msg':field + ' second range element is not an integer'}
                if y > x:
                    return list(range(x, y+1)), MSG_SUCCESS
                else:
                    return None, {'msg':field + ' second integer cannot be smaller than first'}
            else:
                return None, {'msg':field + ' is invalid'}
        if ',' in string:
            string = string.split(',')
            return string, MSG_SUCCESS
        return string, MSG_SUCCESS
    
    # util function to set path to empty - by default empty path has a "."
    def clean_path_string_when_empty(self, field, string):        
        if isinstance(string, Path) and string == Path(""):
            string = ""
            return string, MSG_SUCCESS
        return string, MSG_SUCCESS
        
    # get the pydantic_kwargs and catches any errors in doing so
    def get_and_validate_pydantic_args(self, cls_container, cls, pydantic_kwargs, exclude_modes):
        try:
            try:
                self.get_pydantic_kwargs(cls_container, cls, pydantic_kwargs, exclude_modes)
                return pydantic_kwargs, MSG_SUCCESS
            except ValidationError as exc:
                return None, exc.errors()
        except Exception as exc:
            return None, exc.args

    # validate the model and return errors for user actioning
    def validate_pydantic_model(self, cls, pydantic_kwargs):
    # instantiate the pydantic model form the kwargs we just pulled
        try:
            try :
                pydantic_model = settings.ReconstructionSettings.parse_obj(pydantic_kwargs)
                return pydantic_model, MSG_SUCCESS
            except ValidationError as exc:
                return None, exc.errors()
        except Exception as exc:
            return None, exc.args
        
    # test to make sure model coverts to json which should ensure compatibility with yaml export
    def validate_and_return_json(self, pydantic_model):
        try :
            json_format = pydantic_model.json(indent=4)
            return json_format, MSG_SUCCESS
        except Exception as exc:
            return None, exc.args
        
    # gets a copy of the model from a yaml file
    # will get all fields (even those that are optional and not in yaml) and default values
    # model needs further parsing against yaml file for fields
    def get_model_from_file(self, model_file_path):
        pydantic_model = None
        try :
            try:
                pydantic_model = utils.yaml_to_model(model_file_path, settings.ReconstructionSettings)
            except ValidationError as exc:
                return pydantic_model, exc.errors()
            if pydantic_model is None:
                raise Exception("utils.yaml_to_model - returned a None model")
            return pydantic_model, MSG_SUCCESS
        except Exception as exc:
            return None, exc.args
        
    # handles json with boolean properly and converts to lowercase string
    # as required
    def convert(self, obj):
        if isinstance(obj, bool):
            return str(obj).lower()
        if isinstance(obj, (list, tuple)):
            return [self.convert(item) for item in obj]
        if isinstance(obj, dict):
            return {self.convert(key):self.convert(value) for key, value in obj.items()}
        return obj

    # Main function to add pydantic model to container
    # https://github.com/chrishavlin/miscellaneous_python/blob/main/src/pydantic_magicgui_roundtrip.py
    # Has limitation and can cause breakages for unhandled or incorrectly handled types
    # Cannot handle Union types/typing - for now being handled explicitly
    # Ignoring NoneType since those should be Optional but maybe needs displaying ??
    # ToDo: Needs revisitation, Union check
    # Displaying Union field "time_indices" as LineEdit component
    # excludes handles fields that are not supposed to show up from __fields__
    # json_dict adds ability to provide new set of default values at time of container creation
 
    def add_pydantic_to_container(self, py_model:Union[BaseModel, ModelMetaclass], container: widgets.Container, excludes=[], json_dict=None):
        # recursively traverse a pydantic model adding widgets to a container. When a nested
        # pydantic model is encountered, add a new nested container

        for field, field_def in py_model.__fields__.items():            
            if field_def is not None and field not in excludes:
                def_val = field_def.default
                ftype = field_def.type_          
                toolTip = ""         
                try:
                    for f_val in field_def.class_validators.keys():
                        toolTip = f"{toolTip}{f_val} "
                except Exception as e:
                    pass
                if isinstance(ftype, BaseModel) or isinstance(ftype, ModelMetaclass):
                    json_val = None
                    if json_dict is not None:
                        json_val = json_dict[field]
                    # the field is a pydantic class, add a container for it and fill it
                    new_widget_cls = widgets.Container
                    new_widget = new_widget_cls(name=field_def.name)
                    new_widget.tooltip = toolTip
                    self.add_pydantic_to_container(ftype, new_widget, excludes, json_val)
                #ToDo: Implement Union check, tried:
                # pydantic.typing.is_union(ftype)
                # isinstance(ftype, types.UnionType)
                # https://stackoverflow.com/questions/45957615/how-to-check-a-variable-against-union-type-during-runtime
                elif isinstance(ftype, type(Union[NonNegativeInt, List, str])): 
                    if (field == "background_path"): #field == "background_path": 
                        new_widget_cls, ops = get_widget_class(def_val, Annotated[Path, {"mode": "d"}], dict(name=field, value=def_val))
                        new_widget = new_widget_cls(**ops)
                        toolTip = "Select the folder containing background.zarr"
                    elif (field == "time_indices"): #field == "time_indices": 
                        new_widget_cls, ops = get_widget_class(def_val, str, dict(name=field, value=def_val))
                        new_widget = new_widget_cls(**ops)
                    else: # other Union cases
                        new_widget_cls, ops = get_widget_class(def_val, str, dict(name=field, value=def_val))
                        new_widget = new_widget_cls(**ops)
                    new_widget.tooltip = toolTip
                    if isinstance(new_widget, widgets.EmptyWidget):
                        warnings.warn(message=f"magicgui could not identify a widget for {py_model}.{field}, which has type {ftype}")  
                elif isinstance(def_val, float):
                    # parse the field, add appropriate widget
                    def_step_size = 0.001
                    if field_def.name == "regularization_strength":
                        def_step_size = 0.00001
                    if def_val > -1 and def_val < 1:
                        new_widget_cls, ops = get_widget_class(None, ftype, dict(name=field_def.name, value=def_val, step=float(def_step_size)))
                        new_widget = new_widget_cls(**ops)
                        new_widget.tooltip = toolTip
                    else:
                        new_widget_cls, ops = get_widget_class(None, ftype, dict(name=field_def.name, value=def_val))
                        new_widget = new_widget_cls(**ops)
                        new_widget.tooltip = toolTip
                    if isinstance(new_widget, widgets.EmptyWidget):
                        warnings.warn(message=f"magicgui could not identify a widget for {py_model}.{field}, which has type {ftype}")
                else:
                    # parse the field, add appropriate widget
                    new_widget_cls, ops = get_widget_class(None, ftype, dict(name=field_def.name, value=def_val))
                    new_widget = new_widget_cls(**ops)                    
                    if isinstance(new_widget, widgets.EmptyWidget):
                        warnings.warn(message=f"magicgui could not identify a widget for {py_model}.{field}, which has type {ftype}")
                    else:
                        new_widget.tooltip = toolTip                    
                if json_dict is not None and (not isinstance(new_widget, widgets.Container) or (isinstance(new_widget, widgets.FileEdit))):
                    if field in json_dict.keys():
                        if isinstance(new_widget, widgets.CheckBox):
                            new_widget.value = True if json_dict[field]=="true" else False 
                        elif isinstance(new_widget, widgets.FileEdit):
                            if len(json_dict[field]) > 0:
                                extension = os.path.splitext(json_dict[field])[1]
                                if len(extension) > 0:
                                    new_widget.value = Path(json_dict[field]).parent.absolute() # CLI accepts BG folder not .zarr
                                else:
                                    new_widget.value = Path(json_dict[field])
                        else:
                            new_widget.value = json_dict[field]
                container.append(new_widget)
            
    # refer - add_pydantic_to_container() for comments
    def get_pydantic_kwargs(self, container: widgets.Container, pydantic_model, pydantic_kwargs: dict, excludes=[], json_dict=None):
    # given a container that was instantiated from a pydantic model, get the arguments
    # needed to instantiate that pydantic model from the container.

        # traverse model fields, pull out values from container
        for field, field_def in pydantic_model.__fields__.items():
             if field_def is not None and field not in excludes:
                ftype = field_def.type_
                if isinstance(ftype, BaseModel) or isinstance(ftype, ModelMetaclass):
                    # go deeper
                    pydantic_kwargs[field] = {} # new dictionary for the new nest level
                    # any pydantic class will be a container, so pull that out to pass
                    # to the recursive call
                    sub_container = getattr(container, field_def.name)
                    self.get_pydantic_kwargs(sub_container, ftype, pydantic_kwargs[field], excludes, json_dict)
                else:
                    # not a pydantic class, just pull the field value from the container
                    if hasattr(container, field_def.name):
                        value = getattr(container, field_def.name).value
                        pydantic_kwargs[field] = value

    # copied from main_widget
    # file open/select dialog
    def _open_file_dialog(self, default_path, type):
        if type == "dir":
            return self._open_dialog("select a directory", str(default_path), type)
        elif type == "file":
            return self._open_dialog("select a file", str(default_path), type)
        elif type == "files":
            return self._open_dialog("select file(s)", str(default_path), type)
        elif type == "save":
            return self._open_dialog("save a file", str(default_path), type)
        else:
            return self._open_dialog("select a directory", str(default_path), type)

    def _open_dialog(self, title, ref, type):
        """
        opens pop-up dialogue for the user to choose a specific file or directory.

        Parameters
        ----------
        title:          (str) message to display at the top of the pop up
        ref:            (str) reference path to start the search at
        type:           (str) type of file the user is choosing (dir, file, or save)

        Returns
        -------

        """

        options = QFileDialog.DontUseNativeDialog
        if type == "dir":
            path = QFileDialog.getExistingDirectory(
                None, title, ref, options=options
            )
        elif type == "file":
            path = QFileDialog.getOpenFileName(
                None, title, ref, options=options
            )[0]
        elif type == "files":
            path = QFileDialog.getOpenFileNames(
                None, title, ref, options=options
            )[0]
        elif type == "save":
            path = QFileDialog.getSaveFileName(
                None, "Choose a save name", ref, options=options
            )[0]
        else:
            raise ValueError("Did not understand file dialogue type")

        return path
    
class CollapsibleBox(QWidget):
    def __init__(self, title="", parent=None):
        super(CollapsibleBox, self).__init__(parent)

        self.toggle_button = QToolButton(
            text=title, checkable=True, checked=False
        )
        self.toggle_button.setStyleSheet("QToolButton { border: none; }")
        self.toggle_button.setToolButtonStyle(
            QtCore.Qt.ToolButtonTextBesideIcon
        )
        self.toggle_button.setArrowType(QtCore.Qt.RightArrow)
        self.toggle_button.pressed.connect(self.on_pressed)

        self.toggle_animation = QtCore.QParallelAnimationGroup(self)

        self.content_area = QScrollArea(maximumHeight=0, minimumHeight=0)
        self.content_area.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )
        self.content_area.setFrameShape(QFrame.NoFrame)

        lay = QVBoxLayout(self)
        lay.setSpacing(0)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.toggle_button)
        lay.addWidget(self.content_area)

        self.toggle_animation.addAnimation(
            QtCore.QPropertyAnimation(self, b"minimumHeight")
        )
        self.toggle_animation.addAnimation(
            QtCore.QPropertyAnimation(self, b"maximumHeight")
        )
        self.toggle_animation.addAnimation(
            QtCore.QPropertyAnimation(self.content_area, b"maximumHeight")
        )

    def setNewName(self, name):
        self.toggle_button.setText(name)

	# @QtCore.pyqtSlot()
    def on_pressed(self):
        checked = self.toggle_button.isChecked()
        self.toggle_button.setArrowType(
            QtCore.Qt.DownArrow if not checked else QtCore.Qt.RightArrow
        )
        self.toggle_animation.setDirection(
            QtCore.QAbstractAnimation.Forward
            if not checked
            else QtCore.QAbstractAnimation.Backward
        )
        self.toggle_animation.start()

    def setContentLayout(self, layout):
        lay = self.content_area.layout()
        del lay
        self.content_area.setLayout(layout)
        collapsed_height = (
            self.sizeHint().height() - self.content_area.maximumHeight()
        )
        content_height = layout.sizeHint().height()
        for i in range(self.toggle_animation.animationCount()):
            animation = self.toggle_animation.animationAt(i)
            animation.setDuration(500)
            animation.setStartValue(collapsed_height)
            animation.setEndValue(collapsed_height + content_height)

        content_animation = self.toggle_animation.animationAt(
            self.toggle_animation.animationCount() - 1
        )
        content_animation.setDuration(500)
        content_animation.setStartValue(0)
        content_animation.setEndValue(content_height)

import socket, threading
class MyWorker():
    
    def __init__(self, formLayout, tab_recon:Ui_ReconTab_Form, parentForm):
        super().__init__()    
        self.formLayout:QFormLayout = formLayout
        self.tab_recon:Ui_ReconTab_Form = tab_recon
        self.ui:QWidget = parentForm
        self.max_cores = os.cpu_count()
        # In the case of CLI, we just need to submit requests in a non-blocking way
        self.threadPool = int(self.max_cores/2)
        self.results = {}
        self.pool = None        
        # https://click.palletsprojects.com/en/stable/testing/
        # self.runner = CliRunner()
        self.startPool()
        # jobs_mgmt.shared_var_jobs = self.JobsManager.shared_var_jobs
        self.JobsMgmt = jobs_mgmt.JobsManagement()
        self.useServer = True
        self.serverRunning = True
        self.serverSocket = None
        thread = threading.Thread(target=self.startServer)
        thread.start()
        self.workerThreadRowDeletion = RowDeletionWorkerThread(self.formLayout)
        self.workerThreadRowDeletion.removeRowSignal.connect(self.tab_recon.removeRow)
        self.workerThreadRowDeletion.start()

    def setNewInstances(self, formLayout, tab_recon, parentForm):
        self.formLayout:QFormLayout = formLayout
        self.tab_recon:Ui_ReconTab_Form = tab_recon
        self.ui:QWidget = parentForm
        self.workerThreadRowDeletion.setNewInstances(formLayout)

    def findWidgetRowInLayout(self, strID):
        layout: QFormLayout = self.formLayout
        for idx in range(0, layout.rowCount()):
            widgetItem = layout.itemAt(idx)
            name_widget = widgetItem.widget()
            toolTip_string = str(name_widget.toolTip)
            if strID in toolTip_string:
                name_widget.setParent(None)
                return idx
        return -1

    def startServer(self):
        try:
            if not self.useServer:
                return

            self.serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.serverSocket.bind(('localhost', jobs_mgmt.SERVER_PORT))
            self.serverSocket.listen(50) # become a server socket, maximum 50 connections

            while self.serverRunning:
                connection, address = self.serverSocket.accept()
                if self.ui is not None and not self.ui.isVisible():
                    break
                try:
                    buf = connection.recv(64)
                    if len(buf) > 0:
                        decoded_string = buf.decode("utf-8")
                        json_str = str(decoded_string)
                        json_obj = json.loads(json_str)
                        uID = ""
                        jobID = ""
                        for k in json_obj:
                            self.JobsMgmt.shared_var_jobs[k] = json_obj[k]
                            uID = k
                            jobID = json_obj[k]

                        # dont block the server thread
                        thread = threading.Thread(target=self.tableUpdateAndCleaupThread, args=(uID, jobID))
                        thread.start()
                except Exception as exc:
                    print(exc.args)
                    time.sleep(1)
            
            self.serverSocket.close()
        except Exception as exc:
            if not self.serverRunning:
                self.serverRunning = True
                return # ignore - will cause an exception on napari close but that is fine and does the job
            print(exc.args)

    def stopServer(self):
        try:
            if self.serverSocket is not None:
                self.serverRunning = False
                self.serverSocket.close()
        except Exception as exc:
            print(exc.args)

    def getMaxCPU_cores(self):
        return self.max_cores

    def setPoolThreads(self, t):
        if t > 0 and t < self.max_cores:
            self.threadPool = t

    def startPool(self):
        if self.pool is None:
            self.pool = ThreadPoolExecutor(max_workers=self.threadPool)

    def shutDownPool(self):
        self.pool.shutdown(wait=False)

    # the table update thread can be called from multiple points/threads
    # on errors - table row item is updated but there is no row deletion
    # on successful processing - the row item is expected to be deleted
    # row is being deleted from a seperate thread for which we need to connect using signal
    def tableUpdateAndCleaupThread(self, expIdx="", jobIdx=""):
        # finished will be updated by the job - submitit status

        # ToDo: Another approach to this could be to implement a status thread on the client side
        # Since the client is already running till the job is completed, the client could ping status
        # at regular intervals and also provide results and exceptions we currently read from the file
        # Currently we only send JobID/UniqueID pair from Client to Server. This would reduce multiple threads
        # server side.
        # For row removal use a Queued list approach for better stability

        if expIdx != "" and jobIdx != "":
            # this request came from server so we can wait for the Job to finish and update progress
            # some wait logic needs to be added otherwise for unknown errors this thread will persist
            # perhaps set a time out limit and then update the status window and then exit
            params = self.results[expIdx]
            _infoBox:Label = params["table_entry_infoBox"]
            _txtForInfoBox = "Updating {id}: Please wait... \nJobID assigned: {jID} ".format(id=params["desc"], jID=jobIdx)
            try:
                _infoBox.value = _txtForInfoBox
            except:
                # deleted by user - no longer needs updating
                self.results[expIdx]["status"] = STATUS_user_cleared_job
                return
            _tUpdateCount = 0
            _tUpdateCountTimeout = 120 # 2 mins
            _lastUpdate_jobTXT = ""
            while True:
                time.sleep(1) # update every sec and exit on break                
                try:
                    if _infoBox == None:
                        self.results[expIdx]["status"] = STATUS_user_cleared_job
                        break # deleted by user - no longer needs updating
                    if _infoBox.value:
                        pass
                except:
                    self.results[expIdx]["status"] = STATUS_user_cleared_job
                    break # deleted by user - no longer needs updating
                if self.JobsMgmt.hasSubmittedJob(expIdx):                    
                    if params["status"] in [STATUS_finished_job]:
                        break
                    elif params["status"] in [STATUS_errored_job]:
                        jobERR = self.JobsMgmt.checkForJobIDFile(jobIdx, extension="err")
                        _infoBox.value = jobIdx + "\n" + params["desc"] +"\n\n"+ jobERR
                        break
                    else:
                        jobTXT = self.JobsMgmt.checkForJobIDFile(jobIdx, extension="out")
                        try:
                            if jobTXT == "": # job file not created yet
                                time.sleep(2)
                            elif self.results[expIdx]["status"] == STATUS_finished_job:
                                rowIdx = self.findWidgetRowInLayout(expIdx)
                                # check to ensure row deletion due to shrinking table
                                # if not deleted try to delete again
                                if rowIdx < 0:
                                    break
                                else:
                                    ROW_POP_QUEUE.append(expIdx)
                            elif JOB_COMPLETION_STR in jobTXT:
                                self.results[expIdx]["status"] = STATUS_finished_job
                                _infoBox.value = jobTXT
                                # this is the only case where row deleting occurs    
                                # we cant delete the row directly from this thread
                                # we will use the exp_id to identify and delete the row
                                # using pyqtSignal
                                ROW_POP_QUEUE.append(expIdx)                                
                                # break - based on status
                            elif JOB_TRIGGERED_EXC in jobTXT:
                                self.results[expIdx]["status"] = STATUS_errored_job
                                jobERR = self.JobsMgmt.checkForJobIDFile(jobIdx, extension="err")
                                _infoBox.value = jobIdx + "\n" + params["desc"] +"\n\n"+ jobTXT +"\n\n"+ jobERR
                                break
                            elif JOB_RUNNING_STR in jobTXT:
                                self.results[expIdx]["status"] = STATUS_running_job                                
                                _infoBox.value = jobTXT
                                _tUpdateCount += 1
                                if _tUpdateCount > 60:                                    
                                    if _lastUpdate_jobTXT != jobTXT:
                                        # if there is an update reset counter
                                        _tUpdateCount=0
                                        _lastUpdate_jobTXT = jobTXT
                                    else:
                                        _infoBox.value = "Please check terminal output for Job status..\n\n" + jobTXT
                                if _tUpdateCount > _tUpdateCountTimeout:
                                    break                            
                            else:
                                jobERR = self.JobsMgmt.checkForJobIDFile(jobIdx, extension="err")
                                _infoBox.value = jobIdx + "\n" + params["desc"] +"\n\n"+ jobERR
                                break
                        except Exception as exc:
                            print(exc.args)
        else:
            # this would occur when an exception happens on the pool side before or during job submission
            # we dont have a job ID and will update based on exp_ID/uIU
            for param_ID in self.results.keys():
                params = self.results[param_ID]
                if params["status"] in [STATUS_errored_pool]:
                    _infoBox = params["table_entry_infoBox"]
                    poolERR = self.results[params["exp_id"]]["error"]
                    _infoBox.value = poolERR

    def runInPool(self, params):
        self.results[params["exp_id"]] = params
        self.results[params["exp_id"]]["status"] = STATUS_running_pool
        self.results[params["exp_id"]]["error"] = ""
        try:          
            self.pool.submit(self.run, params)
        except Exception as exc:
            self.results[params["exp_id"]]["status"] = STATUS_errored_pool
            self.results[params["exp_id"]]["error"] = str("\n".join(exc.args))
            self.tableUpdateAndCleaupThread()

    def runMultiInPool(self, multi_params_as_list):
        for params in multi_params_as_list:
            self.results[params["exp_id"]] = params
            self.results[params["exp_id"]]["status"] = STATUS_submitted_pool
            self.results[params["exp_id"]]["error"] = ""
        try:         
            self.pool.map(self.run, multi_params_as_list)
        except Exception as exc:
            for params in multi_params_as_list:
                self.results[params["exp_id"]]["status"] = STATUS_errored_pool
                self.results[params["exp_id"]]["error"] = str("\n".join(exc.args))
            self.tableUpdateAndCleaupThread()

    def getResults(self):
        return self.results
    
    def getResult(self, exp_id):
        return self.results[exp_id]
    
    def run(self, params): 
        # thread where work is passed to CLI which will handle the 
        # multi-processing aspects based on resources
        if params["exp_id"] not in self.results.keys():
            self.results[params["exp_id"]] = params
            self.results[params["exp_id"]]["error"] = ""

        try:
            # does need further threading ? probably not !
            thread = threading.Thread(target=self.runInSubProcess, args=(params,))
            thread.start()
            
            # self.runInSubProcess(params)

            # check for this job to show up in submitit jobs list
            # wait for 2 sec before raising an error

        except Exception as exc:
            self.results[params["exp_id"]]["status"] = STATUS_errored_pool
            self.results[params["exp_id"]]["error"] = str("\n".join(exc.args))
            self.tableUpdateAndCleaupThread()

    def runInSubProcess(self, params):
        try:      
            input_path = str(params["input_path"])
            config_path = str(params["config_path"])
            output_path = str(params["output_path"])
            uid = str(params["exp_id"])    
            mainfp = str(main.FILE_PATH)

            self.results[params["exp_id"]]["status"] = STATUS_submitted_job

            proc = subprocess.run(['python', mainfp, 'reconstruct', '-i', input_path, '-c', config_path, '-o', output_path, '-uid', uid])
            self.results[params["exp_id"]]["proc"] = proc
            if proc.returncode != 0:
                raise Exception("An error occurred in processing ! Check terminal output.")

        except Exception as exc:            
            self.results[params["exp_id"]]["status"] = STATUS_errored_pool
            self.results[params["exp_id"]]["error"] = str("\n".join(exc.args))
            self.tableUpdateAndCleaupThread()   

ROW_POP_QUEUE = []
# Emits a signal to QFormLayout on the main thread
class RowDeletionWorkerThread(QThread):
    removeRowSignal = pyqtSignal(int, str)

    def __init__(self, formLayout):
        super().__init__()
        self.formLayout = formLayout

    def setNewInstances(self, formLayout):
        self.formLayout:QFormLayout = formLayout

    # we might deal with race conditions with a shrinking table
    # find out widget and return its index
    def findWidgetRowInLayout(self, strID):
        layout: QFormLayout = self.formLayout
        for idx in range(0, layout.rowCount()):
            widgetItem = layout.itemAt(idx)
            if widgetItem is not None:
                name_widget = widgetItem.widget()
                toolTip_string = str(name_widget.toolTip)
                if strID in toolTip_string:
                    name_widget.setParent(None)
                    return idx
        return -1

    def run(self):
        while True:
            if len(ROW_POP_QUEUE) > 0:
                stringID = ROW_POP_QUEUE.pop(0)
                # Emit the signal to remove the row
                deleteRow = self.findWidgetRowInLayout(stringID)
                if deleteRow > -1:
                    self.removeRowSignal.emit(int(deleteRow), str(stringID))
                time.sleep(1)
            else:
                time.sleep(5)

# VScode debugging
if __name__ == "__main__":
    import napari
    napari.Viewer()
    napari.run()