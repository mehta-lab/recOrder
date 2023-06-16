import pytest
from recOrder.cli.settings import TransferFunctionSettings
from iohub.ngff import open_ome_zarr

@pytest.fixture(scope="function")
def default_settings_and_transfer_function(tmp_path):
    settings = TransferFunctionSettings()
    dataset = open_ome_zarr(tmp_path, layout="fov", mode="w", channel_names=["None"])
    yield settings, dataset