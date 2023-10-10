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

from recOrder.cli.settings import ReconstructionSettings

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


def _get_config_container(
    model: Union[pydantic.BaseModel, pydantic.fields.ModelField],
    scrollable: bool,
    label: str = None,
):
    """Recursively create nested magic GUI widgets for a pydantic model."""
    if _is_pydantic_model_type(model):  # top-level to create
        widget = widgets.Container(scrollable=scrollable)
        if label is not None:
            label = widgets.Label(value=label)
            widget.append(label)
        for field in model.__fields__.values():
            widget.append(_get_config_container(field, scrollable=False))
    elif _is_pydantic_model_type(model.type_):  # sublevels
        widget = _get_config_container(
            model.type_, scrollable=False, label=model.name.replace("_", " ")
        )
    else:  # individual fields
        if model.name == "reconstruction_type":
            type_names = [
                x.__name__.split("Settings")[0] for x in get_args(model.type_)
            ]
            widget = widgets.create_widget(
                annotation=Literal[tuple(type_names)],
                name=model.name,
            )
            # connect to _on_click_function
        else:
            widget = _get_config_field(model)
    return widget


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
        container = _get_config_container(
            ReconstructionSettings, scrollable=True
        )
        container.show()

    def _reconstruct(self) -> None:
        pass

    def _add_visualization_layout(self) -> None:
        self._main_layout.addWidget(QHLine())
        collapsible = QCollapsible("Visualization tools")
        collapsible.addWidget(QNamedSlider("Max retardance"))
        self._main_layout.addWidget(collapsible)
