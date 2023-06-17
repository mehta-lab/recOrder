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


def test_compute_transfer(input_zarr):
    path, _ = input_zarr
    runner = CliRunner()
    result = runner.invoke(cli, "compute-tf " + str(path))
    assert result.exit_code == 0
    assert "Generating" in result.output


def test_compute_transfer_blank_config():
    runner = CliRunner()
    for option in ("-c ", "--config-path "):
        cmd = "compute-tf " + option
        result = runner.invoke(cli, cmd)
        assert result.exit_code == 2
        assert "Error" in result.output


def test_compute_transfer_blank_output():
    runner = CliRunner()
    for option in ("-o ", "--output-path "):
        cmd = "compute-tf " + option
        result = runner.invoke(cli, cmd)
        assert result.exit_code == 2
        assert "Error" in result.output


def test_compute_transfer_output_file(tmp_path, input_zarr):
    input_path, _ = input_zarr
    runner = CliRunner()
    paths = ["test1", "test2/test"]
    for option in (" -o ", " --output-path "):
        temp_cmd = "compute-tf " + str(input_path) + option
        for path in paths:
            joined_path = tmp_path.joinpath(path)
            cmd = temp_cmd + str(joined_path)
            result = runner.invoke(cli, cmd)
            assert result.exit_code == 0
            assert path in result.output
            assert joined_path.exists()


def test_stokes_matrix_write(birefringence_phase_recon_settings_function):
    settings, dataset = birefringence_phase_recon_settings_function
    generate_and_save_birefringence_transfer_function(settings, dataset)
    assert dataset["intensity_to_stokes_matrix"]


def test_absorption_and_phase_write(
    birefringence_phase_recon_settings_function,
):
    settings, dataset = birefringence_phase_recon_settings_function
    generate_and_save_phase_transfer_function(settings, dataset, (3, 4, 5))
    assert dataset["real_potential_transfer_function"]
    assert dataset["imaginary_potential_transfer_function"]
    assert "absorption_transfer_function" not in dataset
    assert "phase_transfer_function" not in dataset


def test_phase_3dim_write(birefringence_phase_recon_settings_function):
    settings, dataset = birefringence_phase_recon_settings_function
    settings.reconstruction_dimension = 2
    generate_and_save_phase_transfer_function(settings, dataset, (3, 4, 5))
    assert dataset["absorption_transfer_function"]
    assert dataset["phase_transfer_function"]
    assert "real_potential_transfer_function" not in dataset
    assert "imaginary_potential_transfer_function" not in dataset


# TODO: FIX THESE
def test_birefringence_call(
    tmp_path, birefringence_phase_recon_settings_function, input_zarr
):
    input_path, _ = input_zarr
    runner = CliRunner()
    cmd = "compute-tf " + str(input_path) + " -o " + str(tmp_path)
    settings, dataset = birefringence_phase_recon_settings_function
    with patch(
        "recOrder.cli.compute_transfer_function.open_ome_zarr"
    ) as mock_zarr_function:
        mock_zarr_function.return_value = dataset
        with patch(
            "recOrder.cli.compute_transfer_function.generate_and_save_birefringence_transfer_function"
        ) as mock:
            result = runner.invoke(cli, cmd)
            # mock.assert_called_once_with(settings, dataset, (4, 5, 6))
            assert result.exit_code == 0
            assert "birefringence:" in result.output


def test_phase_default_call(
    tmp_path, birefringence_phase_recon_settings_function, input_zarr
):
    input_path, _ = input_zarr
    runner = CliRunner()
    cmd = "compute-tf " + str(input_path) + " -o " + str(tmp_path)
    settings, dataset = birefringence_phase_recon_settings_function
    with patch(
        "recOrder.cli.compute_transfer_function.open_ome_zarr"
    ) as mock_zarr_function:
        mock_zarr_function.return_value = dataset
        with patch(
            "recOrder.cli.compute_transfer_function.generate_and_save_phase_transfer_function"
        ) as mock:
            result = runner.invoke(cli, cmd)
            mock.assert_called_once_with(settings, dataset)
            assert result.exit_code == 0
            assert "phase:" in result.output
