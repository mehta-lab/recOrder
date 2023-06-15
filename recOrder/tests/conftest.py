import pytest
from recOrder.cli.settings import TransferFunctionSettings
from iohub.ngff import open_ome_zarr

@pytest.fixture(scope="function")
def setup_default_ctf_settings(tmp_path):
    settings = TransferFunctionSettings()
    dataset = open_ome_zarr(tmp_path, layout="fov", mode="w", channel_names=["None"])
    yield settings, dataset

@pytest.fixture(scope="function")
def setup_b_false_ctf_settings(tmp_path):
    settings = TransferFunctionSettings()
    settings.universal_settings.reconstruct_birefringence = False
    dataset = open_ome_zarr(tmp_path, layout="fov", mode="w", channel_names=["None"])
    yield settings, dataset

@pytest.fixture(scope="function")
def setup_p_false_ctf_settings(tmp_path):
    settings = TransferFunctionSettings()
    settings.universal_settings.reconstruct_phase = False
    dataset = open_ome_zarr(tmp_path, layout="fov", mode="w", channel_names=["None"])
    yield settings, dataset

@pytest.fixture(scope="function")
def setup_b_and_p_false_ctf_settings(tmp_path):
    settings = TransferFunctionSettings()
    settings.universal_settings.reconstruct_birefringence = False
    settings.universal_settings.reconstruct_phase = False
    dataset = open_ome_zarr(tmp_path, layout="fov", mode="w", channel_names=["None"])
    yield settings, dataset