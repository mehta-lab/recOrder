from recOrder.cli.main import cli
from click.testing import CliRunner
from recOrder.cli.compute_transfer_function import (
    generate_and_save_phase_transfer_function,
    generate_and_save_birefringence_transfer_function,
    generate_and_save_fluorescence_transfer_function,
)


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
    assert dataset["imaginary_potential_transfer_function"].shape == (
        1,
        1,
        3,
        4,
        5,
    )
    assert "absorption_transfer_function" not in dataset
    assert "phase_transfer_function" not in dataset


def test_phase_3dim_write(birefringence_phase_recon_settings_function):
    settings, dataset = birefringence_phase_recon_settings_function
    settings.reconstruction_dimension = 2
    generate_and_save_phase_transfer_function(settings, dataset, (3, 4, 5))
    assert dataset["absorption_transfer_function"]
    assert dataset["phase_transfer_function"]
    assert dataset["phase_transfer_function"].shape == (1, 1, 3, 4, 5)
    assert "real_potential_transfer_function" not in dataset
    assert "imaginary_potential_transfer_function" not in dataset


def test_fluorescence_write(fluorescence_recon_settings_function):
    settings, dataset = fluorescence_recon_settings_function
    generate_and_save_fluorescence_transfer_function(
        settings, dataset, (3, 4, 5)
    )
    assert dataset["optical_transfer_function"]
    assert dataset["optical_transfer_function"].shape == (1, 1, 3, 4, 5)
    assert "real_potential_transfer_function" not in dataset
    assert "imaginary_potential_transfer_function" not in dataset