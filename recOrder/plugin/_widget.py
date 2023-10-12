from __future__ import annotations

import os
from time import sleep
from inspect import isclass
from pathlib import Path
from typing import TYPE_CHECKING, Union, Literal
import numpy as np
import pydantic
from magicgui import magicgui, widgets
from qtpy.QtCore import Qt, QFileSystemWatcher
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
    QCheckBox,
)
from superqt import QCollapsible, QLabeledSlider

from recOrder.cli import settings, reconstruct
from recOrder.cli.apply_inverse_transfer_function import (
    get_reconstruction_output_metadata,
)
from recOrder.cli.settings import (
    OPTION_TO_MODEL_DICT,
    RECONSTRUCTION_TYPES,
    ReconstructionSettings,
)
from recOrder.io import utils
from iohub.ngff import open_ome_zarr
from iohub.ngff_meta import TransformationMeta

INTERVAL_SECONDS = 2

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
        self._main_layout = QVBoxLayout()
        self._add_calibration_layout()
        self._add_input_layout()
        self._add_config_layout()
        self._add_output_layout()
        self._add_reconstruct_layout()
        self._add_visualization_layout()
        self.setLayout(self._main_layout)

        # Temporary
        self._input_path_le.setText(
            "/Users/talon.chandler/Desktop/0.4.0-release/zenodo-v1.4.0/sample_contribution/raw_data.zarr/0/0/0"
        )
        self._input_config_path_le.setText(
            "/Users/talon.chandler/recOrder/examples/birefringence.yml"
        )
        self._output_path_le.setText(
            "/Users/talon.chandler/Downloads/test.zarr"
        )
        self.last_reconstructed_time_point = 0

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
        self._input_path_le.setReadOnly(False)
        self._input_path_le.setText("")
        input_btn = QPushButton("Browse")
        input_btn.clicked.connect(self._select_dataset)
        self._add_labelled_row("Input dataset", self._input_path_le, input_btn)

    def _select_dataset(self) -> None:
        path = QFileDialog.getExistingDirectory(
            parent=self,
            caption="Open a directory containing a dataset",
            directory=self.cwd,
        )
        self._input_path_le.setText(path)

    def _add_config_layout(self) -> None:
        self._input_config_path_le = QLineEdit()
        self._input_config_path_le.setReadOnly(False)
        self._input_config_path_le.setText("")
        config_open_btn = QPushButton("Browse")
        config_open_btn.clicked.connect(self._select_config)

        reconstruct_config_btn = QPushButton("Edit")
        reconstruct_config_btn.clicked.connect(self._launch_config_window)

        # Add config editing row
        grid_layout = QGridLayout()
        grid_layout.addWidget(QLabel("Reconstruction parameters"), 0, 0)
        grid_layout.addWidget(self._input_config_path_le, 0, 1)
        grid_layout.addWidget(config_open_btn, 0, 2)
        grid_layout.addWidget(reconstruct_config_btn, 0, 3)
        self._main_layout.addLayout(grid_layout)

    def _select_config(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            parent=self,
            caption="Open a configuration yaml file",
            directory=self.cwd,
        )
        self._input_config_path_le.setText(path)

    def _add_output_layout(self) -> None:
        self._output_path_le = QLineEdit()
        self._output_path_le.setReadOnly(False)
        self._output_path_le.setText("")
        output_btn = QPushButton("Browse")
        output_btn.clicked.connect(self._select_output)
        self._add_labelled_row(
            "Output dataset", self._output_path_le, output_btn
        )

    def _select_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            parent=self,
            caption="Choose an output .zarr",
            directory=self.cwd,
        )
        self._output_path_le.setText(path)

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
            elif field.name != "reconstruction_settings":
                self.container.append(_get_config_field(field))

        self._update_config_window()
        self.container.show()

    def _reconstruct(self) -> None:
        input_zarr_path = Path(self._input_path_le.text())
        input_config_path = Path(self._input_config_path_le.text())

        if not self.in_progress_cb.isChecked():
            # Set off reconstruction
            reconstruct.reconstruct_cli(
                input_position_dirpaths=[input_zarr_path],
                config_filepath=input_config_path,
                output_dirpath=Path(self._output_path_le.text()),
                num_processes=1,
            )

            # Add reconstruction to viewer
            self.viewer.open(
                self._output_path_le.text(), plugin="napari-ome-zarr"
            )
        else:
            while not input_zarr_path.exists():
                sleep(INTERVAL_SECONDS)

            # Start watching
            self.watcher = QFileSystemWatcher([str(input_zarr_path / "0")])
            self.watcher.directoryChanged.connect(self._data_changed)

    def _data_changed(self):
        input_zarr_path = Path(self._input_path_le.text())
        input_config_path = Path(self._input_config_path_le.text())

        if not Path(self._output_path_le.text()).exists():
            # Prepare the output zarr
            output_dict = get_reconstruction_output_metadata(
                input_zarr_path, input_config_path
            )
            self.output_dataset = open_ome_zarr(
                self._output_path_le.text(),
                mode="a",
                layout="fov",
                channel_names=output_dict["channel_names"],
            )
            self.output_dataset.create_zeros(
                name="0",
                shape=output_dict["shape"],
                chunks=output_dict["chunks"],
                dtype=output_dict["dtype"],
                transform=[
                    TransformationMeta(
                        type="scale", scale=output_dict["scale"]
                    )
                ],
            )
        else:
            self.output_dataset = open_ome_zarr(
                self._output_path_le.text(), mode="a"
            )

            dataset = open_ome_zarr(input_zarr_path)
            while self.last_reconstructed_time_point < dataset["0"].shape[0]:
                # Create time-specific ReconstructionSettings object
                settings = utils.yaml_to_model(
                    self._input_config_path_le.text(), ReconstructionSettings
                )
                settings.time_indices = self.last_reconstructed_time_point

                utils.model_to_yaml(settings, "./tmp.yaml")

                # Set off reconstruction
                reconstruct.reconstruct_cli(
                    input_position_dirpaths=[input_zarr_path],
                    config_filepath=Path("./tmp.yaml"),
                    output_dirpath=Path("./tmp.zarr"),
                    num_processes=1,
                )

                # Append result into output zarr
                with open_ome_zarr("./tmp.zarr") as temp_dataset:
                    # @Ziwen is there a better way?
                    if self.output_dataset["0"].shape[0] == 1:
                        self.output_dataset["0"][:] = np.array(
                            temp_dataset["0/0/0"]["0"]
                        )
                    else:
                        self.output_dataset["0"].append(
                            temp_dataset["0/0/0"]["0"], axis=0
                        )

                self.viewer.open(
                    self._output_path_le.text(), plugin="napari-ome-zarr"
                )

                # Add reconstruction to viewer after first reconstruction
                self.last_reconstructed_time_point += 1
            dataset.close()

    def _add_reconstruct_layout(self) -> None:
        grid_layout = QGridLayout()

        reconstruct_btn = QPushButton("Reconstruct")
        reconstruct_btn.clicked.connect(self._reconstruct)
        grid_layout.addWidget(reconstruct_btn, 0, 0)

        self.in_progress_cb = QCheckBox("In progress")
        grid_layout.addWidget(self.in_progress_cb, 0, 2)

        self._main_layout.addLayout(grid_layout)

    def _add_visualization_layout(self) -> None:
        self._main_layout.addWidget(QHLine())
        collapsible = QCollapsible("Visualization tools")
        collapsible.addWidget(QNamedSlider("Max retardance"))
        self._main_layout.addWidget(collapsible)
