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
from recOrder.cli.settings import OPTION_TO_MODEL_DICT, RECONSTRUCTION_TYPES

if TYPE_CHECKING:
    from napari import Viewer


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


def _add_widget_to_container(
    container,
    model: Union[pydantic.BaseModel, pydantic.fields.ModelField],
    label: str = None,
):
    """Recursively add nested magic GUI widgets to a container."""
    if _is_pydantic_model_type(model):  # top-level classes
        if label is not None:
            label = widgets.Label(value=label)
            container.append(label)
        for field in model.__fields__.values():
            container = _add_widget_to_container(container, field)
    elif _is_pydantic_model_type(model.type_):  # intermediate classes
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

    def _update_config_window(self) -> None:
        if isinstance(self.container[-1], widgets.Container):
            self.container.pop(-1)
        # Get model from combo box
        option = self.reconstruction_type_combo_box.value
        model = OPTION_TO_MODEL_DICT[option]
        channel_settings = widgets.Container()
        _add_widget_to_container(channel_settings, model)
        self.container.append(channel_settings)

    def _launch_config_window(self) -> None:
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
            else:
                self.container.append(_get_config_field(field))

        self._update_config_window()
        self.container.show()

    def _reconstruct(self) -> None:
        pass

    def _add_visualization_layout(self) -> None:
        self._main_layout.addWidget(QHLine())
        collapsible = QCollapsible("Visualization tools")
        collapsible.addWidget(QNamedSlider("Max retardance"))
        self._main_layout.addWidget(collapsible)
