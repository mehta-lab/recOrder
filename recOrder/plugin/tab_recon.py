import os, sys, glob, ntpath, subprocess, traceback, json, time
from pathlib import Path, PurePath
from qtpy import QtCore, QtGui
from qtpy.QtGui import QPixmap, QPainter, QCursor
from qtpy.QtCore import Qt, QTimer, QSize
from qtpy.QtWidgets import *
from magicgui.widgets import *
from napari.qt.threading import thread_worker

import pydantic, datetime, uuid
from enum import Enum
from typing import Optional, Union
from typing import Final
from magicgui import widgets
from magicgui.type_map import get_widget_class
import warnings

from recOrder.io import utils
from recOrder.cli import settings
    
# Main class for the Reconstruction tab
# Not efficient since instantiated from GUI
# Does not have access to common functions in main_widget
# ToDo : From main_widget and pass self reference
class Ui_Form(object):
    def __init__(self):
        super().__init__()       
        self.current_dir_path = str(Path.cwd())
        self.current_save_path = str(Path.cwd())
        self.input_directory = str(Path.cwd())
        self.save_directory = str(Path.cwd())

        # Top level parent
        self.recon_tab_widget = QWidget()
        self.recon_tab_layout = QVBoxLayout()
        self.recon_tab_layout.setAlignment(Qt.AlignTop)
        self.recon_tab_layout.setContentsMargins(0,0,0,0)
        self.recon_tab_layout.setSpacing(0) 
        self.recon_tab_widget.setLayout(self.recon_tab_layout)        
        
        self.recon_tab_container = widgets.Container(name='Main', scrollable=True)        
        self.recon_tab_layout.addWidget(self.recon_tab_container.native)    
                
        # Top level - Selection modes, model creation and running
        self.modes_widget = QWidget()
        self.modes_layout = QHBoxLayout()
        self.modes_layout.setAlignment(Qt.AlignTop)
        self.modes_widget.setLayout(self.modes_layout)
        self.modes_widget.setMaximumHeight(60)
                
        # For now replicate CLI processing modes - these could reside in the CLI settings file as well
        # for consistency
        OPTION_TO_MODEL_DICT = {
            "birefringence": {"enabled":False, "setting":None},
            "phase": {"enabled":False, "setting":None},
            "fluorescence": {"enabled":False, "setting":None},
        }
        self.modes_selected = OPTION_TO_MODEL_DICT

        # Make a copy of the Reconstruction settings mode, these will be used as template
        for mode in self.modes_selected.keys():
            self.modes_selected[mode]["setting"] = settings.ReconstructionSettings.__fields__[mode]

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
        self.recon_tab_container.native.layout().addWidget(self.modes_widget)

        # Top level - Data Input
        self.modes_widget2 = QWidget()
        self.modes_layout2 = QHBoxLayout()
        self.modes_layout2.setAlignment(Qt.AlignTop)
        self.modes_widget2.setLayout(self.modes_layout2)

        self.reconstruction_input_data_loc = widgets.LineEdit(
                name="",
                value=self.input_directory
        )
        self.reconstruction_input_data = widgets.PushButton(
                name="InputData",
                label="Input Data"
        )
        self.reconstruction_input_data.clicked.connect(self.browse_dir_path_input)
        self.modes_layout2.addWidget(self.reconstruction_input_data_loc.native)
        self.modes_layout2.addWidget(self.reconstruction_input_data.native)
        self.recon_tab_container.native.layout().addWidget(self.modes_widget2)
        
        # Top level - Central scrollable component which will hold Editable/(vertical) Expanding UI
        self.recon_tab_scrollArea_settings = QScrollArea()
        self.recon_tab_scrollArea_settings.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.recon_tab_scrollArea_settings.setWidgetResizable(True)
        self.recon_tab_qwidget_settings = QWidget()
        self.recon_tab_qwidget_settings_layout = QVBoxLayout()
        self.recon_tab_qwidget_settings_layout.setSpacing(10)
        self.recon_tab_qwidget_settings_layout.setAlignment(Qt.AlignTop)
        self.recon_tab_qwidget_settings.setLayout(self.recon_tab_qwidget_settings_layout)
        self.recon_tab_scrollArea_settings.setWidget(self.recon_tab_qwidget_settings)
        self.recon_tab_layout.addWidget(self.recon_tab_scrollArea_settings)
               
        # Temp placeholder component to display, json pydantic output, validation msg, etc
        # ToDo: Move to plugin message/error handling
        self.json_display = widgets.Label(value="")
        _scrollArea = QScrollArea()
        _scrollArea.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        _scrollArea.setWidgetResizable(True)   
        _scrollArea.setMaximumHeight(200)     
        _qwidget_settings = QWidget()
        _qwidget_settings_layout = QVBoxLayout()
        _qwidget_settings_layout.setAlignment(Qt.AlignTop)
        _qwidget_settings.setLayout(_qwidget_settings_layout)
        _scrollArea.setWidget(_qwidget_settings)
        self.recon_tab_layout.addWidget(_scrollArea)
        self.build_button.clicked.connect(self.display_json_callback)
        _qwidget_settings_layout.addWidget(self.json_display.native)

    # Copied from main_widget
    # ToDo: utilize common functions
    # Input data selector
    def browse_dir_path_input(self):
        result = self._open_file_dialog(self.current_dir_path, "dir")
        self.directory = result
        self.current_dir_path = result
        self.input_directory = result
        self.reconstruction_input_data_loc.value = self.input_directory

    # Copied from main_widget
    # ToDo: utilize common functions
    # Output data selector
    def browse_dir_path_output(self, elem):
        result = self._open_file_dialog(self.current_dir_path, "dir")
        self.directory = result
        self.current_dir_path = result
        self.save_directory = result
        elem.value = self.save_directory

    # Creates UI controls from model based on selections
    def _create_acq_contols(self):                                
        # initialize the top container and specify what pydantic class to map from        
        pydantic_class = settings.ReconstructionSettings
        
        # Make a copy of selections and unsed for deletion
        self.selected_modes = []
        self.selected_modes_del = []
        self.selected_modes_vals = {}
        for mode in self.modes_selected.keys():
            enabled = self.modes_selected[mode]["Checkbox"].value
            self.selected_modes_vals[mode] = enabled
            if not enabled:
                self.selected_modes_del.append(mode)
                pydantic_class.__fields__[mode] = None
            else:
                self.selected_modes.append(mode)
                pydantic_class.__fields__[mode] = self.modes_selected[mode]["setting"]

        # Container holding the pydantic UI components
        # Multiple instances/copies since more than 1 might be created
        recon_pydantic_container = widgets.Container(name='-and-'.join(self.selected_modes), scrollable=False)        
        self.add_pydantic_to_container(pydantic_class, recon_pydantic_container)

        # Add this container to the main scrollable widget
        self.recon_tab_qwidget_settings_layout.addWidget(recon_pydantic_container.native)

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

        # Final constant UI val and identifier
        _idx: Final[int] = self.index
        _str: Final[str] = uuid.uuid4()        
        
        # Output Data location
        # These could be multiple based on user selection for each model
        # Inherits from Input by default at creation time
        _output_data_loc = widgets.LineEdit(
                name="",
                value=self.input_directory
        )
        _output_data = widgets.PushButton(
                name="OutputData",
                label="Output Data"
        )

        # Passing all UI components that would be deleted
        _del_button.clicked.connect(lambda: self._delete_model(recon_pydantic_container.native, _output_data_loc.native, _output_data.native, _del_button.native, _line, _idx, _str))
        
        # Passing location label to output location selector
        _output_data.clicked.connect(lambda: self.browse_dir_path_output(_output_data_loc))

        # HBox for Output Data
        _hBox_widget = QWidget()
        _hBox_layout = QHBoxLayout()
        _hBox_layout.setAlignment(Qt.AlignTop)
        _hBox_widget.setLayout(_hBox_layout)
        _hBox_layout.addWidget(_output_data_loc.native)
        _hBox_layout.addWidget(_output_data.native)

        self.recon_tab_qwidget_settings_layout.addWidget(_hBox_widget)
        self.recon_tab_qwidget_settings_layout.addWidget(_del_button.native)
        self.recon_tab_qwidget_settings_layout.addWidget(_line)

        # Dynamic/modifying UI probably needs this
        self.recon_tab_qwidget_settings_layout.addStretch()

        # Store a copy of the pydantic container along with all its associated components and properties
        # We dont needs a copy of the class but storing for now
        # This will be used for making deletion edits and looping to create our final run output
        # uuid - used for identiying in editable list
        self.pydantic_classes.append({'uuid':_str, 'class':pydantic_class, 'input':self.reconstruction_input_data_loc, 'output':_output_data_loc, 'container':recon_pydantic_container, 'selected_modes':self.selected_modes.copy(), 'selected_modes_del':self.selected_modes_del.copy(), 'selected_modes_vals':self.selected_modes_vals.copy()})
        self.index += 1

    # UI components deletion - maybe just needs the parent container instead of individual components
    def _delete_model(self, wid1, wid2, wid3, wid4, wid5, index, _str):
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
        
        # Find and remove the class from our pydantic model list using uuid
        i=0
        for item in self.pydantic_classes:
            if item["uuid"] == _str:
                self.pydantic_classes.pop(i)
                self.json_display.value = ""
                return
            i += 1

    # Clear all the generated pydantic models and clears the pydantic model list
    def _clear_all_models(self):
        index = self.recon_tab_qwidget_settings_layout.count()-1
        while(index >= 0):
            myWidget = self.recon_tab_qwidget_settings_layout.itemAt(index).widget()
            if myWidget is not None:
                myWidget.setParent(None)
            index -=1
        self.pydantic_classes.clear()
        self.json_display.value = ""
        self.index = 0
    
    # Displays the json output from the pydantic model UI selections by user
    # Loops through all our stored pydantic classes
    def display_json_callback(self):
        # we dont want to have a partial run if there are N models
        # so we will validate them all first and then run in a second loop
        # first pass for validating
        # second pass for creating yaml and processing
        for item in self.pydantic_classes:
            cls = item['class'] # not used
            cls_container = item['container']
            selected_modes = item['selected_modes']
            selected_modes_del = item['selected_modes_del']
            selected_modes_vals = item['selected_modes_vals']
            
            # build up the arguments for the pydantic model given the current container
            cls = settings.ReconstructionSettings

            for mode in self.modes_selected.keys():
                enabled = selected_modes_vals[mode]
                if not enabled:
                    cls.__fields__[mode] = None
                else:
                    cls.__fields__[mode] = self.modes_selected[mode]["setting"]

            # get the kwargs from the container/class
            pydantic_kwargs = {}
            self.get_pydantic_kwargs(cls_container, cls, pydantic_kwargs)

            # For list element, this needs to be cleaned and parsed back as an array
            pydantic_kwargs["input_channel_names"] = self.remove_chars(pydantic_kwargs["input_channel_names"], ['[',']', '\'', ' '])  
            pydantic_kwargs["input_channel_names"] = pydantic_kwargs["input_channel_names"].split(',')

            # Modes that are not used needs to be purged from the class to reflect 
            # the same on the container side
            for mode in selected_modes_del:
                del cls.__fields__[mode]

            # instantiate the pydantic model form the kwargs we just pulled
            # validate and return any meaning info for user
            try :
                pydantic_model = cls.parse_obj(pydantic_kwargs)
            except pydantic.ValidationError as exc:
                self.json_display.value = exc.errors()[0]
                return

            # generate a json from the instantiated model, update the json_display
            self.json_format = pydantic_model.json(indent=4)
            self.json_display.value = self.json_format

        self.json_display.value = ""
        
        # generate a time-stamp for our yaml files to avoid overwriting
        # files generated at the same time will have an index suffix
        now = datetime.datetime.now()
        unique_id = now.strftime("%Y_%m_%d_%H_%M_%S")

        i = 0
        for item in self.pydantic_classes:
            i += 1
            cls = item['class'] # not used
            cls_container = item['container']
            selected_modes = item['selected_modes']
            selected_modes_del = item['selected_modes_del']
            selected_modes_vals = item['selected_modes_vals']

            # gather input/out locations
            input_dir = f"{item['input'].value}"
            output_dir = f"{item['output'].value}"

            # build up the arguments for the pydantic model given the current container
            cls = settings.ReconstructionSettings

            for mode in self.modes_selected.keys():
                enabled = selected_modes_vals[mode]
                if not enabled:
                    cls.__fields__[mode] = None
                else:
                    cls.__fields__[mode] = self.modes_selected[mode]["setting"]

            pydantic_kwargs = {}
            self.get_pydantic_kwargs(cls_container, cls, pydantic_kwargs)

            pydantic_kwargs["input_channel_names"] = self.remove_chars(pydantic_kwargs["input_channel_names"], ['[',']', '\'', ' '])            
            pydantic_kwargs["input_channel_names"] = pydantic_kwargs["input_channel_names"].split(',')

            for mode in selected_modes_del:
                del cls.__fields__[mode]

            # instantiate the pydantic model form the kwargs we just pulled
            try :
                pydantic_model = cls.parse_obj(pydantic_kwargs)
            except pydantic.ValidationError as exc:
                self.json_display.value = exc.errors()[0]
                return

            # generate a json from the instantiated model, update the json_display
            # most of this will end up in a table as processing proceeds
            self.json_format = pydantic_model.json(indent=4)
            addl_txt = "ID:" + unique_id + "-"+ str(i) + "\nInput:" + input_dir + "\nOutput:" + output_dir
            self.json_display.value = self.json_display.value + addl_txt + "\n" + self.json_format+ "\n\n"
            
            # save the yaml files
            save_config_path = str(Path.cwd())
            dir_ = save_config_path
            yml_file = "-and-".join(selected_modes)
            yml_file = yml_file+"-"+unique_id+"-"+str(i)+".yml"
            config_path = os.path.join(dir_ ,"examples", yml_file)
            utils.model_to_yaml(pydantic_model, config_path)
        
    # util function to parse list elements displayed as string
    def remove_chars(self, string, chars_to_remove):
        for char in chars_to_remove:
            string = string.replace(char, '')
        return string    

    # Main function to add pydantic model to container
    # https://github.com/chrishavlin/miscellaneous_python/blob/main/src/pydantic_magicgui_roundtrip.py
    # Has limitation and can cause breakages for unhandled or incorrectly handled types
    # Cannot handle Union types/typing - for now being handled explicitly
    # Ignoring NoneType since those should be Optional but maybe needs displaying ??
    # ToDo: Needs revisitation, Union check
    # Displaying Union field "time_indices" as LineEdit component
    def add_pydantic_to_container(self, py_model: Union[pydantic.BaseModel, pydantic.main.ModelMetaclass], container: widgets.Container):
        # recursively traverse a pydantic model adding widgets to a container. When a nested
        # pydantic model is encountered, add a new nested container
        for field, field_def in py_model.__fields__.items():
            if field_def is not None:
                ftype = field_def.type_
                if isinstance(ftype, pydantic.BaseModel) or isinstance(ftype, pydantic.main.ModelMetaclass):
                    # the field is a pydantic class, add a container for it and fill it
                    new_widget_cls = widgets.Container
                    new_widget = new_widget_cls(name=field_def.name)
                    self.add_pydantic_to_container(ftype, new_widget)
                elif field == "time_indices": #ToDo: Implement Union check
                    new_widget_cls, ops = get_widget_class(None, str, dict(name=field, value=field_def.default))
                    new_widget = new_widget_cls(**ops)
                    if isinstance(new_widget, widgets.EmptyWidget):
                        warnings.warn(message=f"magicgui could not identify a widget for {py_model}.{field}, which has type {ftype}")                
                else:
                    # parse the field, add appropriate widget
                    new_widget_cls, ops = get_widget_class(None, ftype, dict(name=field_def.name, value=field_def.default))
                    new_widget = new_widget_cls(**ops)
                    if isinstance(new_widget, widgets.EmptyWidget):
                        warnings.warn(message=f"magicgui could not identify a widget for {py_model}.{field}, which has type {ftype}")
                container.append(new_widget)
            
    # refer - add_pydantic_to_container() for comments
    def get_pydantic_kwargs(self, container: widgets.Container, pydantic_model, pydantic_kwargs: dict):
    # given a container that was instantiated from a pydantic model, get the arguments
    # needed to instantiate that pydantic model from the container.

        # traverse model fields, pull out values from container
        for field, field_def in pydantic_model.__fields__.items():
             if field_def is not None:
                ftype = field_def.type_
                if isinstance(ftype, pydantic.BaseModel) or isinstance(ftype, pydantic.main.ModelMetaclass):
                    # go deeper
                    pydantic_kwargs[field] = {} # new dictionary for the new nest level
                    # any pydantic class will be a container, so pull that out to pass
                    # to the recursive call
                    sub_container = getattr(container, field_def.name)
                    self.get_pydantic_kwargs(sub_container, ftype, pydantic_kwargs[field])
                else:
                    # not a pydantic class, just pull the field value from the container
                    if hasattr(container, field_def.name):
                        value = getattr(container, field_def.name).value
                        pydantic_kwargs[field] = value

    # copied from main_widget
    # file open/select dialog
    def _open_file_dialog(self, default_path, type):
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
        elif type == "save":
            path = QFileDialog.getSaveFileName(
                None, "Choose a save name", ref, options=options
            )[0]
        else:
            raise ValueError("Did not understand file dialogue type")

        return path

# VScode debugging
if __name__ == "__main__":
    import napari
    napari.Viewer()
    napari.run()