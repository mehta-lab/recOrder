from recOrder.cli.main import cli
import unittest
from click.testing import CliRunner
from unittest.mock import patch, Mock
from iohub.ngff import open_ome_zarr, Position
from hypothesis import given, HealthCheck, settings
from hypothesis import strategies as st
from recOrder.cli.compute_transfer_function import (
    generate_and_save_phase_transfer_function, 
    generate_and_save_birefringence_transfer_function,
    compute_transfer_function_cli
)
from recOrder.cli.settings import (
    TransferFunctionSettings,
    _PhaseTransferFunctionSettings,
    _BirefringenceTransferFunctionSettings,
    _UniversalSettings
)
import pytest

def test_main():
    runner = CliRunner()
    result = runner.invoke(cli)

    assert result.exit_code == 0
    assert "Toolkit" in result.output

def test_compute_transfer(tmp_path):
    runner = CliRunner()
    result = runner.invoke(cli, "compute-transfer-function -o " + str(tmp_path))
    assert result.exit_code == 0
    assert "Generating" in result.output

def test_compute_transfer_blank_config():
    runner = CliRunner()
    for option in ("-c ", "--config-path "):
        cmd = "compute-transfer-function " + option
        result = runner.invoke(cli, cmd)
        assert result.exit_code == 2
        assert "Error" in result.output

def test_compute_transfer_blank_output():
    runner = CliRunner()
    for option in ("-o ", "--output-path "):
        cmd = "compute-transfer-function " + option
        result = runner.invoke(cli, cmd)
        assert result.exit_code == 2
        assert "Error" in result.output

def test_compute_transfer_output_file(tmp_path):
    runner = CliRunner()
    paths = ["test1", "test2/test"]
    for option in ("-o ", "--output-path "):
        temp_cmd = "compute-transfer-function " + option
        for path in paths:
            cmd = temp_cmd + str(tmp_path.joinpath(path))
            result = runner.invoke(cli, cmd)
            assert result.exit_code == 0
            assert path in result.output
            assert tmp_path.exists()

def test_compute_transfer_config_none(tmp_path):
    runner = CliRunner()
    for option in ("-c ", "--config-path "):
        cmd = "compute-transfer-function " + option + "None " + "-o " + str(tmp_path)
        result = runner.invoke(cli, cmd)
        assert result.exit_code == 0
        assert "Generating" in result.output

def test_stokes_matrix_write(setup_default_ctf_settings):
    settings, dataset = setup_default_ctf_settings
    generate_and_save_birefringence_transfer_function(settings, dataset)
    assert dataset["intensity_to_stokes_matrix"]

def test_absorption_and_phase_write(setup_default_ctf_settings):
    settings, dataset = setup_default_ctf_settings
    generate_and_save_phase_transfer_function(settings, dataset)
    assert dataset["absorption_transfer_function"]
    assert dataset["phase_transfer_function"]
    with pytest.raises(KeyError):
        assert dataset["real_potential_transfer_function"]
        assert dataset["imaginary_potential_transfer_function"]

def test_phase_3dim_write(setup_3d_ctf_settings):
    settings, dataset = setup_3d_ctf_settings
    generate_and_save_phase_transfer_function(settings, dataset)
    assert dataset["real_potential_transfer_function"]
    assert dataset["imaginary_potential_transfer_function"]
    with pytest.raises(KeyError):
        assert dataset["absorption_transfer_function"]
        assert dataset["phase_transfer_function"]

def test_birefringence_default_call(tmp_path, setup_default_ctf_settings):
    runner = CliRunner()
    cmd = "compute-transfer-function -o " + str(tmp_path)
    settings, dataset = setup_default_ctf_settings
    with patch("recOrder.cli.compute_transfer_function.open_ome_zarr") as mock_zarr_function:
        mock_zarr_function.return_value = dataset
        with patch("recOrder.cli.compute_transfer_function.generate_and_save_birefringence_transfer_function") as mock:
            result = runner.invoke(cli, cmd)
            mock.assert_called_once_with(settings, dataset)
            assert result.exit_code == 0
            assert "reconstruct_birefringence: true" in result.output

def test_phase_default_call(tmp_path, setup_default_ctf_settings):
    runner = CliRunner()
    cmd = "compute-transfer-function -o " + str(tmp_path)
    settings, dataset = setup_default_ctf_settings
    with patch("recOrder.cli.compute_transfer_function.open_ome_zarr") as mock_zarr_function:
        mock_zarr_function.return_value = dataset
        with patch("recOrder.cli.compute_transfer_function.generate_and_save_phase_transfer_function") as mock:
            result = runner.invoke(cli, cmd)
            mock.assert_called_once_with(settings, dataset)
            assert result.exit_code == 0
            assert "reconstruct_phase: true" in result.output

def test_birefringence_false_call(tmp_path, setup_b_false_ctf_settings):
    runner = CliRunner()
    cmd = "compute-transfer-function -o " + str(tmp_path)
    settings, _ = setup_b_false_ctf_settings
    with patch("recOrder.cli.compute_transfer_function.TransferFunctionSettings") as mock_settings:
        mock_settings.return_value = settings
        with patch("recOrder.cli.compute_transfer_function.generate_and_save_birefringence_transfer_function") as mock:
            result = runner.invoke(cli, cmd)
            mock.assert_not_called()
            assert result.exit_code == 0
            assert "reconstruct_birefringence: false" in result.output

def test_phase_false_call(tmp_path, setup_p_false_ctf_settings):
    runner = CliRunner()
    cmd = "compute-transfer-function -o " + str(tmp_path)
    settings, _ = setup_p_false_ctf_settings
    with patch("recOrder.cli.compute_transfer_function.TransferFunctionSettings") as mock_settings:
        mock_settings.return_value = settings
        with patch("recOrder.cli.compute_transfer_function.generate_and_save_phase_transfer_function") as mock:
            result = runner.invoke(cli, cmd)
            mock.assert_not_called()
            assert result.exit_code == 0
            assert "reconstruct_phase: false" in result.output

def test_b_and_p_false_call(tmp_path, setup_b_and_p_false_ctf_settings):
    runner = CliRunner()
    cmd = "compute-transfer-function -o " + str(tmp_path)
    settings, _ = setup_b_and_p_false_ctf_settings
    with patch("recOrder.cli.compute_transfer_function.TransferFunctionSettings") as mock_settings:
        mock_settings.return_value = settings
        with patch("recOrder.cli.compute_transfer_function.generate_and_save_birefringence_transfer_function") as mock_1:
            with patch("recOrder.cli.compute_transfer_function.generate_and_save_phase_transfer_function") as mock_2:
                result = runner.invoke(cli, cmd)
                mock_1.assert_not_called()
                mock_2.assert_not_called()
                assert result.exit_code == 0
                assert "reconstruct_birefringence: false" in result.output
                assert "reconstruct_phase: false" in result.output