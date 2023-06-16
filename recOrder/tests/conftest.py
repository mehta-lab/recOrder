import pytest
from recOrder.cli.settings import TransferFunctionSettings
from iohub.ngff import open_ome_zarr

@pytest.fixture(scope="function")
def default_settings_and_transfer_function(tmp_path):
    settings = TransferFunctionSettings()
    dataset = open_ome_zarr(tmp_path, layout="fov", mode="w", channel_names=["None"])
    yield settings, dataset

@pytest.fixture(scope="function")
def birefringence_settings_false_and_default_transfer_function(default_settings_and_transfer_function):
    settings, dataset = default_settings_and_transfer_function
    settings.universal_settings.reconstruct_birefringence = False
    yield settings, dataset

@pytest.fixture(scope="function")
def phase_settings_false_and_default_transfer_function(default_settings_and_transfer_function):
    settings, dataset = default_settings_and_transfer_function
    settings.universal_settings.reconstruct_phase = False
    yield settings, dataset

@pytest.fixture(scope="function")
def birefringence_and_phase_settings_false_and_default_transfer_function(default_settings_and_transfer_function):
    settings, dataset = default_settings_and_transfer_function
    settings.universal_settings.reconstruct_birefringence = False
    settings.universal_settings.reconstruct_phase = False
    yield settings, dataset

@pytest.fixture(scope="function")
def settings_3d_and_default_transfer_function(default_settings_and_transfer_function):
    settings, dataset = default_settings_and_transfer_function
    settings.universal_settings.reconstruction_dimension = 3
    yield settings, dataset