import pytest
import numpy as np
from recOrder.cli import settings
from iohub.ngff import open_ome_zarr


@pytest.fixture(scope="function")
def input_zarr(tmp_path):
    path = tmp_path / "input.zarr"

    dataset = open_ome_zarr(
        path,
        layout="fov",
        mode="w",
        channel_names=["None"],
    )
    dataset.create_zeros("0", (2, 1, 4, 5, 6), dtype=np.float32)
    yield path, dataset


@pytest.fixture(scope="function")
def birefringence_phase_recon_settings_function(tmp_path):
    recon_settings = settings.ReconstructionSettings(
        birefringence=settings.BirefringenceSettings(),
        phase=settings.PhaseSettings(),
    )
    dataset = open_ome_zarr(
        tmp_path, layout="fov", mode="w", channel_names=["None"]
    )
    yield recon_settings, dataset
