from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QFrame,
    QLabel,
    QGridLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QSlider,
)

from superqt import QLabeledSlider, QCollapsible

if TYPE_CHECKING:
    from napari import Viewer


class QHLine(QFrame):
    def __init__(self):
        super().__init__()
        self.setFrameShape(QFrame.HLine)


class QNamedSlider(QWidget):
    def __init__(self, name: str):
        super().__init__()
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._max_retardance_slider = QLabeledSlider(Qt.Orientation.Horizontal)
        layout = QFormLayout()
        layout.addRow(name, self._max_retardance_slider)
        self.setLayout(layout)


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
        pass

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
        pass

    def _reconstruct(self) -> None:
        pass

    def _add_visualization_layout(self) -> None:
        self._main_layout.addWidget(QHLine())
        collapsible = QCollapsible("Visualization tools")
        collapsible.addWidget(QNamedSlider("Max retardance"))
        self._main_layout.addWidget(collapsible)
