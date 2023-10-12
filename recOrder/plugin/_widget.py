from __future__ import annotations

import os
from inspect import isclass
from pathlib import Path
from typing import TYPE_CHECKING, Union, Literal, get_args

import pydantic
from magicgui import magicgui, widgets
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from superqt import QCollapsible, QLabeledSlider

from recOrder.cli import settings
from recOrder.io.utils import model_to_yaml, yaml_to_model

if TYPE_CHECKING:
    from napari import Viewer

OPTION_TO_MODEL_DICT = {
    "Birefringence": settings.BirefringenceSettings,
    "Phase": settings.PhaseSettings,
    "Birefringence and Phase": settings.BirefringenceAndPhaseSettings,
    "Fluorescence": settings.FluorescenceSettings,
}

RECONSTRUCTION_TYPES = Literal[tuple(OPTION_TO_MODEL_DICT.keys())]


class QHLine(QFrame):
    def __init__(self):
        super().__init__()
        self.setFrameShape(QFrame.HLine)


class QNamedSlider(QWidget):
    def __init__(self, name: str):
        super().__init__()
        self._slider = QLabeledSlider(Qt.Orientation.Horizontal)
        layout = QFormLayout()
        layout.addRow(name, self._slider)
        self.setLayout(layout)


class ReconstructionSettingsWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.cwd = os.getcwd()
        self.parent_layout = QVBoxLayout()
        self.container = widgets.Container(scrollable=True)

        for field in settings.ReconstructionSettings.__fields__.values():
            if field.name == "reconstruction_type":
                self.reconstruction_type_combo_box = widgets.create_widget(
                    annotation=RECONSTRUCTION_TYPES,
                    name=field.name,
                )
                self.reconstruction_type_combo_box.changed.connect(
                    self._update_config_window
                )
                self.container.append(self.reconstruction_type_combo_box)
            elif field.name == "input_channel_names":
                self.container.append(widgets.ListEdit(field.default, name=field.name))
            else:
                self.container.append(_get_config_field(field))

        self.parent_layout.addWidget(self.container.native)
        self._add_button_row()

        self.setLayout(self.parent_layout)
        self._update_config_window()
    
    def _update_config_window(self) -> None:
        if isinstance(self.container[-1], widgets.Container):
            self.container.pop(-1)
        # Get model from combo box
        option = self.reconstruction_type_combo_box.value
        model = OPTION_TO_MODEL_DICT[option]
        channel_settings = widgets.Container()
        _add_widget_to_container(channel_settings, model)
        self.container.append(channel_settings)
        pass

    def _add_button_row(self) -> None:
        grid_layout = QGridLayout()
        load_btn = QPushButton("Load")
        load_btn.clicked.connect(self._load_dataset)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save_dataset)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)

        grid_layout.addWidget(load_btn, 0, 0)
        grid_layout.addWidget(save_btn, 0, 1)
        grid_layout.addWidget(close_btn, 0, 2)
        self.parent_layout.addLayout(grid_layout)
        pass

    
    def _save_dataset(self) -> None:
        if hasattr(self, 'reconstruction_type'):
            delattr(self, 'reconstruction_type')
        path, _ = QFileDialog.getSaveFileName(
            parent=self,
            caption="Open a directory containing a dataset",
            directory=self.cwd,
        )
        
        settings_kwargs = {}
        reconstruction_type_kwargs = {}
        def switch(recontruction_type: str, prop: str, key: str):
            if recontruction_type == 'Birefringence':
                key_set = settings.BirefringenceSettings().__fields__.get(prop).default.__dict__.keys()
                return key in key_set
            elif recontruction_type == 'Phase':
                key_set = settings.PhaseSettings().__fields__.get(prop).default.__dict__.keys()
                return key in key_set
            elif recontruction_type == 'FluorescenceSettings':
                key_set = settings.FluorescenceSettings().__fields__.get(prop).default.__dict__.keys()
                return key in key_set
            else:
                return False
        
        def add_fields(container: widgets.Container, settings_kwarg: dict):
            for widget in container:
                widget: widgets.Widget
                name: str = widget.name
                if isinstance(widget, widgets.Container):
                    if widget.widget_type == 'ListEdit':
                        settings_kwarg[name] = widget.value
                    else:
                        if name == '':
                            add_fields(widget, reconstruction_type_kwargs)
                        else:
                            settings_kwarg[name] = {}
                            add_fields(widget, settings_kwarg[name])
                else:
                    if name == 'reconstruction_type':
                        settings_kwarg['reconstruction_type'] = {}
                        self.recontruction_type = widget.value
                    elif name == '' and widget.widget_type == 'Label':
                        prop = str(widget.value).replace(' ', '_')
                        if prop == 'birefringence_settings':
                                self.curr_settings = 'birefringence_settings'
                        elif prop == 'phase_settings':
                                self.curr_settings = 'phase_settings'
                        elif hasattr(self, 'curr_settings'):
                            if prop == 'transfer_function' or prop == 'apply_inverse':
                                continue
                        settings_kwarg[prop] = {}
                    else:
                        if hasattr(self, 'recontruction_type'):
                            if self.recontruction_type != 'Birefringence and Phase':
                                if switch(self.recontruction_type, 'transfer_function', name):
                                    settings_kwarg['transfer_function'][name] = widget.value
                                elif switch(self.recontruction_type, 'apply_inverse', name):
                                    settings_kwarg['apply_inverse'][name] = widget.value
                            else:
                                if hasattr(self, 'curr_settings'):
                                    trimmed_curr_settings = self.curr_settings.split("_")[0].capitalize()
                                    if switch(trimmed_curr_settings, 'transfer_function', name):
                                        if not 'transfer_function' in settings_kwarg[self.curr_settings]:
                                            settings_kwarg[self.curr_settings]['transfer_function'] = {}
                                        settings_kwarg[self.curr_settings]['transfer_function'][name] = widget.value
                                    elif switch(trimmed_curr_settings, 'apply_inverse', name):
                                        if not 'apply_inverse' in settings_kwarg[self.curr_settings]:
                                            settings_kwarg[self.curr_settings]['apply_inverse'] = {}
                                        settings_kwarg[self.curr_settings]['apply_inverse'][name] = widget.value
                        else:
                            settings_kwarg[name] = widget.value
        
        add_fields(self.container, settings_kwargs)
        
        def reconstruction_type(recontruction_type: str, reconstruction_type_kwargs: dict):
            if recontruction_type == 'Birefringence':
                self.recontruction_type_model = settings.BirefringenceSettings(**reconstruction_type_kwargs)
                return
            elif recontruction_type == 'Phase':
                self.recontruction_type_model = settings.PhaseSettings(**reconstruction_type_kwargs)
                return
            elif recontruction_type == 'Fluorescence':
                self.recontruction_type_model = settings.FluorescenceSettings(**reconstruction_type_kwargs)
                return
            else:
                self.recontruction_type_model = settings.BirefringenceAndPhaseSettings(**reconstruction_type_kwargs)
                return
        
        reconstruction_type(self.recontruction_type, reconstruction_type_kwargs)
        for key in reconstruction_type_kwargs.keys():
            settings_kwargs.get('reconstruction_type')[key] = reconstruction_type_kwargs.get(key)

        self.model = settings.ReconstructionSettings(**settings_kwargs)
        model_to_yaml(self.model, path)

    def _load_dataset(self) -> None:
        # panel should be clear first then re-added the widgets
        path, _ = QFileDialog.getOpenFileName(
            parent=self,
            caption="Open a directory containing a dataset",
            directory=self.cwd,
        )
        self.model = yaml_to_model(path, settings.ReconstructionSettings)
        self.container = widgets.Container(scrollable=True)

        def get_type(field_name):
            for field in settings.ReconstructionSettings.__fields__.values():
                if field.name == field_name:
                    return field.type_
        
        def get_reconstruction_type_model(value: any):
            keys = value.__dict__.keys()
            if 'birefringence_settings' in keys and 'phase_settings' in keys:
                return settings.BirefringenceAndPhaseSettings(**value.dict())
            else:
                transfer_func_keys = value.__dict__.get('transfer_function').__annotations__.keys()
                if 'swing' in transfer_func_keys:
                    return settings.BirefringenceSettings(**value.dict())
                elif 'numerical_aperture_illumination' in transfer_func_keys:
                    return settings.PhaseSettings(**value.dict())
                else:
                    return settings.FluorescenceSettings(**value.dict())

        for field_name in self.model.__dict__:
            value = self.model.__dict__.get(field_name)
            if field_name == "input_channel_names":
                self.container.append(widgets.ListEdit(value, name=field_name))
            elif field_name == "reconstruction_type":
                # TODO: correctly show the reconstruction type from load
                self.container.append(self.reconstruction_type_combo_box)
                reconstruction_type_model = get_reconstruction_type_model(value)
                channel_settings = widgets.Container()
                _add_widget_to_container(channel_settings, reconstruction_type_model)
                self.container.append(channel_settings)
            else:
                self.container.append(_create_config_field(value, get_type(field_name), field_name))

        self.parent_layout.addWidget(self.container.native)



def calibrate_lc(
    calibration_metadata: str, states: Literal["4-states", "5-states"]
):
    pass


def _filter_annoation(field_type: type):
    annotation = str
    if (
        getattr(field_type, "__name__", str(field_type))
        in pydantic.types.__all__
    ):
        if "Float" in str(field_type):
            annotation = float
        elif "Int" in str(field_type):
            annotation = int
    return annotation

def _create_config_field(value: any, type: any, name: str):
    try:
        widget = widgets.create_widget(value, annotation=type, name=name)
    except Exception:
        widget = widgets.create_widget(
            value,
            annotation=_filter_annoation(type),
            name=name,
        )
    return widget

def _get_config_field(field: pydantic.fields.ModelField):
    try:
        widget = widgets.create_widget(
            value=field.default, annotation=field.type_, name=field.name
        )
    except Exception:
        widget = widgets.create_widget(
            value=field.default,
            annotation=_filter_annoation(field.type_),
            name=field.name,
        )

    return widget


def _is_pydantic_model_type(type_: type):
    if isclass(type_):
        if issubclass(type_, pydantic.BaseModel):
            return True
    return False

def _is_pydantic_model_instance(type_: type):
    return isinstance(type_, pydantic.BaseModel)

def _add_widget_to_container(
    container,
    model: Union[pydantic.BaseModel, pydantic.fields.ModelField],
    label: str = None,
):
    """Recursively add nested magic GUI widgets to a container."""
    if _is_pydantic_model_instance(model):
        for field in model.__dict__.keys():
            if field == 'birefringence_settings' or field == 'phase_settings' or field == 'transfer_function' or field == 'apply_inverse':
                label = widgets.Label(value=field)
                container.append(label)
            value = model.__dict__.get(field)
            if _is_pydantic_model_instance(value):
                container = _add_widget_to_container(container, value)
            else:
                container.append(_create_config_field(value, None, field))
    elif _is_pydantic_model_type(model) or _is_pydantic_model_instance(model):  # top-level classes
        if label is not None:
            label = widgets.Label(value=label)
            container.append(label)
        for field in model.__fields__.values():
            container = _add_widget_to_container(container, field)
    elif hasattr(model, 'type_') and _is_pydantic_model_type(model.type_):  # intermediate classes
        container = _add_widget_to_container(
            container, model.type_, label=model.name.replace("_", " ")
        )
    else:  # bottom level fields
        container.append(_get_config_field(model))
    return container


class MainWidget(QWidget):
    def __init__(self, napari_viewer: Viewer):
        super().__init__()
        self.viewer = napari_viewer
        self.cwd = os.getcwd()
        self._input_path = None
        self._reconstruct_config_path = None
        self._main_layout = QVBoxLayout()
        self._add_calibration_layout()
        self._add_input_layout()
        self._add_reconstruct_layout()
        self._add_visualization_layout()
        self.setLayout(self._main_layout)

    def _add_labelled_row(
        self, label: str, left: QWidget, right: QWidget
    ) -> None:
        grid_layout = QGridLayout()
        grid_layout.addWidget(QLabel(label), 0, 0)
        grid_layout.addWidget(left, 0, 1)
        grid_layout.addWidget(right, 0, 2)
        self._main_layout.addLayout(grid_layout)

    def _add_calibration_layout(self) -> None:
        calibrate_btn = QPushButton("Calibrate")
        calibrate_btn.clicked.connect(self._launch_calibration_window)
        calibrate_status_le = QLineEdit()
        calibrate_status_le.setReadOnly(True)
        calibrate_status_le.setText("<Not calibrated>")
        self._add_labelled_row(
            "LC Calibration", calibrate_status_le, calibrate_btn
        )

    def _launch_calibration_window(self) -> None:
        magicgui(calibrate_lc).show()

    def _add_input_layout(self) -> None:
        self._input_path_le = QLineEdit()
        self._input_path_le.setReadOnly(True)
        self._input_path_le.setText("<Not set>")
        input_btn = QPushButton("Open")
        input_btn.clicked.connect(self._select_dataset)
        self._add_labelled_row("Input dataset", self._input_path_le, input_btn)

    def _select_dataset(self) -> None:
        path = QFileDialog.getExistingDirectory(
            parent=self,
            caption="Open a directory containing a dataset",
            directory=self.cwd,
        )
        self._input_path_le.setText(path)
        self._input_path = Path(path)

    def _add_reconstruct_layout(self) -> None:
        self._reconstruct_config_path_le = QLineEdit()
        self._reconstruct_config_path_le.setReadOnly(True)
        self._reconstruct_config_path_le.setText("<Not set>")
        reconstruct_config_btn = QPushButton("Edit")
        reconstruct_config_btn.clicked.connect(self._launch_config_window)
        self._add_labelled_row(
            "Reconstruction parameters",
            self._reconstruct_config_path_le,
            reconstruct_config_btn,
        )
        reconstruct_btn = QPushButton("Reconstruct")
        reconstruct_btn.clicked.connect(self._reconstruct)
        self._main_layout.addWidget(reconstruct_btn)

    def _launch_config_window(self) -> None:
        self.popup = ReconstructionSettingsWidget()
        self.popup.show()

    def _reconstruct(self) -> None:
        pass

    def _add_visualization_layout(self) -> None:
        self._main_layout.addWidget(QHLine())
        collapsible = QCollapsible("Visualization tools")
        collapsible.addWidget(QNamedSlider("Max retardance"))
        self._main_layout.addWidget(collapsible)
