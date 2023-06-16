from recOrder.cli.main import cli
from click.testing import CliRunner
from unittest.mock import patch
from recOrder.cli.compute_transfer_function import (
    generate_and_save_phase_transfer_function, 
    generate_and_save_birefringence_transfer_function,
)

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
            joined_path = tmp_path.joinpath(path)
            cmd = temp_cmd + str(joined_path)
            result = runner.invoke(cli, cmd)
            assert result.exit_code == 0
            assert path in result.output
            assert joined_path.exists()

def test_compute_transfer_config_none(tmp_path):
    runner = CliRunner()
    for option in ("-c ", "--config-path "):
        cmd = "compute-transfer-function " + option + "None " + "-o " + str(tmp_path)
        result = runner.invoke(cli, cmd)
        assert result.exit_code == 0
        assert "Generating" in result.output

def test_stokes_matrix_write(default_settings_and_transfer_function):
    settings, dataset = default_settings_and_transfer_function
    generate_and_save_birefringence_transfer_function(settings, dataset)
    assert dataset["intensity_to_stokes_matrix"]

def test_absorption_and_phase_write(default_settings_and_transfer_function):
    settings, dataset = default_settings_and_transfer_function
    generate_and_save_phase_transfer_function(settings, dataset)
    assert dataset["absorption_transfer_function"]
    assert dataset["phase_transfer_function"]
    assert "real_potential_transfer_function" not in dataset
    assert "imaginary_potential_transfer_function" not in dataset

def test_phase_3dim_write(settings_3d_and_default_transfer_function):
    settings, dataset = settings_3d_and_default_transfer_function
    generate_and_save_phase_transfer_function(settings, dataset)
    assert dataset["real_potential_transfer_function"]
    assert dataset["imaginary_potential_transfer_function"]
    assert "absorption_transfer_function" not in dataset
    assert "phase_transfer_function" not in dataset

def test_birefringence_default_call(tmp_path, default_settings_and_transfer_function):
    runner = CliRunner()
    cmd = "compute-transfer-function -o " + str(tmp_path)
    settings, dataset = default_settings_and_transfer_function
    with patch("recOrder.cli.compute_transfer_function.open_ome_zarr") as mock_zarr_function:
        mock_zarr_function.return_value = dataset
        with patch("recOrder.cli.compute_transfer_function.generate_and_save_birefringence_transfer_function") as mock:
            result = runner.invoke(cli, cmd)
            mock.assert_called_once_with(settings, dataset)
            assert result.exit_code == 0
            assert "reconstruct_birefringence: true" in result.output

def test_phase_default_call(tmp_path, default_settings_and_transfer_function):
    runner = CliRunner()
    cmd = "compute-transfer-function -o " + str(tmp_path)
    settings, dataset = default_settings_and_transfer_function
    with patch("recOrder.cli.compute_transfer_function.open_ome_zarr") as mock_zarr_function:
        mock_zarr_function.return_value = dataset
        with patch("recOrder.cli.compute_transfer_function.generate_and_save_phase_transfer_function") as mock:
            result = runner.invoke(cli, cmd)
            mock.assert_called_once_with(settings, dataset)
            assert result.exit_code == 0
            assert "reconstruct_phase: true" in result.output

def test_birefringence_false_call(tmp_path, birefringence_settings_false_and_default_transfer_function):
    runner = CliRunner()
    cmd = "compute-transfer-function -o " + str(tmp_path)
    settings, _ = birefringence_settings_false_and_default_transfer_function
    with patch("recOrder.cli.compute_transfer_function.TransferFunctionSettings") as mock_settings:
        mock_settings.return_value = settings
        with patch("recOrder.cli.compute_transfer_function.generate_and_save_birefringence_transfer_function") as mock:
            result = runner.invoke(cli, cmd)
            mock.assert_not_called()
            assert result.exit_code == 0
            assert "reconstruct_birefringence: false" in result.output

def test_phase_false_call(tmp_path, phase_settings_false_and_default_transfer_function):
    runner = CliRunner()
    cmd = "compute-transfer-function -o " + str(tmp_path)
    settings, _ = phase_settings_false_and_default_transfer_function
    with patch("recOrder.cli.compute_transfer_function.TransferFunctionSettings") as mock_settings:
        mock_settings.return_value = settings
        with patch("recOrder.cli.compute_transfer_function.generate_and_save_phase_transfer_function") as mock:
            result = runner.invoke(cli, cmd)
            mock.assert_not_called()
            assert result.exit_code == 0
            assert "reconstruct_phase: false" in result.output

def test_b_and_p_false_call(tmp_path, birefringence_and_phase_settings_false_and_default_transfer_function):
    runner = CliRunner()
    cmd = "compute-transfer-function -o " + str(tmp_path)
    settings, _ = birefringence_and_phase_settings_false_and_default_transfer_function
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