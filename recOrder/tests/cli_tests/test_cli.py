from recOrder.cli.main import cli
from click.testing import CliRunner
from unittest.mock import patch, Mock
from iohub.ngff import open_ome_zarr, Position
from hypothesis import given
from hypothesis import strategies as st
from recOrder.cli.compute_transfer_function import generate_save_phase_transfer_function, generate_and_save_birefringence_transfer_function

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
    for option in ("-c", "--config-path"):
        cmd = "compute-transfer-function" + option
        result = runner.invoke(cli, cmd)
        assert result.exit_code == 2
        assert "Error" in result.output

def test_compute_transfer_output_file():
    runner = CliRunner()
    paths = ["test1", "test2/test", "test3/"]
    for option in ("-o ", "--output-path "):
        cmd = "compute-transfer-function " + option
        for path in paths:
            run_cmd = cmd
            run_cmd += path
            result = runner.invoke(cli, run_cmd)
            assert result.exit_code == 0
            assert path in result.output