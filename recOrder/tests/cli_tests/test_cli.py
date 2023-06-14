from recOrder.cli.main import cli
import unittest
from click.testing import CliRunner
from unittest.mock import patch, Mock
from iohub.ngff import open_ome_zarr, Position
from hypothesis import given
from hypothesis import strategies as st
from recOrder.cli.compute_transfer_function import (
    generate_save_phase_transfer_function, 
    generate_and_save_birefringence_transfer_function,
    compute_transfer_function_cli,
)
from recOrder.cli.settings import (
    TransferFunctionSettings,
    _PhaseTransferFunctionSettings,
    _BirefringenceTransferFunctionSettings
)
from typing import Literal

def test_main():
    runner = CliRunner()
    result = runner.invoke(cli)

    assert result.exit_code == 0
    assert "Toolkit" in result.output

def test_compute_transfer():
    runner = CliRunner()
    result = runner.invoke(cli, "compute-transfer-function")

    assert result.exit_code == 0
    assert "Generating" in result.output

def test_compute_transfer_blank_config():
    runner = CliRunner()
    for option in ("-c ", "--config-path "):
        cmd = "compute-transfer-function" + option
        result = runner.invoke(cli, cmd)
        assert result.exit_code == 2
        assert "Error" in result.output

def test_compute_transfer_output_file():
    runner = CliRunner()
    paths = ["test1", "test2/test", "test3/"]
    for option in ("-o ", "--output-path "):
        temp_cmd = "compute-transfer-function " + option
        for path in paths:
            cmd = temp_cmd
            cmd += path
            result = runner.invoke(cli, cmd)
            assert result.exit_code == 0
            assert path in result.output

def test_compute_transfer_config_none():
    runner = CliRunner()
    for option in ("-c ", "--config-path "):
        cmd = "compute-transfer-function " + option + "None"
        result = runner.invoke(cli, cmd)
        assert result.exit_code == 0
        assert "Generating"

@patch("recOrder.cli.compute_transfer_function.TransferFunctionSettings")
def test_compute_transfer_config_settings(mock_function):
    mock_settings = Mock()
    mock_settings.universal_settings.dict.return_value = [{
        'reconstruct_birefringence': False,
        'reconstruct_phase': True,
        'reconstruct_dimensions': 2,
        'wavelength_illumination': 0.532
    }
    ]
    mock_settings.universal_settings.reconstruct_birefringence = False
    mock_settings.universal_settings.reconstruct_phase = True
    mock_settings.universal_settings.reconstruct_dimension = 2
    mock_settings.universal_settings.wavelength_illumination = 0.532

    mock_settings.phase_transfer_function_settings = _PhaseTransferFunctionSettings()
    mock_settings.birefringence_transfer_function_settings = _BirefringenceTransferFunctionSettings()

    mock_settings.dict.return_value = {
    'universal_settings': {'reconstruct_birefringence': False, 
                           'reconstruct_phase': True, 
                           'reconstruction_dimension': 2, 
                           'wavelength_illumination': 0.532}, 
    'birefringence_transfer_function_settings': {'swing': 0.1, 
                                                 'scheme': '4-State'}, 
    'phase_transfer_function_settings': {'zyx_shape': [16, 128, 256], 
                                         'yx_pixel_size': 0.325, 
                                         'z_pixel_size': 2.0, 
                                         'z_padding': 0, 
                                         'index_of_refraction_media': 1.3, 
                                         'numerical_aperture_illumination': 0.5, 
                                         'numerical_aperture_detection': 1.2}}

    mock_function.return_value = mock_settings

    compute_transfer_function_cli(None, 'test')


# @given(birefringence=st.booleans(), phase=st.booleans(), dim=st.integers(2, 3))
# def test_compute_transfer_config_diff_settings(birefringence, phase, dim):
    # runner = CliRunner()
    # cmd = "compute-transfer-function -c"
    # # test_output_path = "config_settings_test"
    # settings = TransferFunctionSettings()
    # settings.universal_settings.reconstruct_birefringence = False #birefringence
    # settings.universal_settings.reconstruct_phase = #phase
    # settings.universal_settings.reconstruction_dimension = #dim
    # print('hello')

