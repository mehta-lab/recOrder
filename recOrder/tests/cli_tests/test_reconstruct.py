import numpy as np
from recOrder.cli.main import cli
from recOrder.cli import settings
from recOrder.io import utils
from click.testing import CliRunner
from iohub.ngff import open_ome_zarr


def test_reconstruct(tmp_path):
    input_path = tmp_path / "input.zarr"

    # Generate input "dataset"
    channel_names = [f"State{x}" for x in range(4)]
    dataset = open_ome_zarr(
        input_path,
        layout="fov",
        mode="w",
        channel_names=channel_names,
    )
    dataset.create_zeros("0", (2, 4, 4, 5, 6), dtype=np.uint16)

    # Setup options
    birefringence_settings = settings.BirefringenceSettings(
        transfer_function=settings.BirefringenceTransferFunctionSettings()
    )
    all_options = [
        (birefringence_settings, [0], None, 2),
        (birefringence_settings, 0, settings.PhaseSettings(), 2),
        (birefringence_settings, [0, 1], None, 3),
        (birefringence_settings, "all", settings.PhaseSettings(), 3),
    ]

    for (
        birefringence_option,
        time_indices,
        phase_option,
        dimension_option,
    ) in all_options:
        if (birefringence_option is None) and (phase_option is None):
            continue

        # Generate recon settings
        recon_settings = settings.ReconstructionSettings(
            input_channel_names=channel_names,
            time_indices=time_indices,
            reconstruction_dimension=dimension_option,
            birefringence=birefringence_option,
            phase=phase_option,
        )
        config_path = tmp_path / "test.yml"
        utils.model_to_yaml(recon_settings, config_path)

        # Run CLI
        runner = CliRunner()
        tf_path = input_path.with_name("tf.zarr")
        runner.invoke(
            cli,
            [
                "compute-tf",
                str(input_path),
                "-c",
                str(config_path),
                "-o",
                str(tf_path),
            ],
            catch_exceptions=False,
        )
        assert tf_path.exists()

        # Apply the tf
        result_path = input_path.with_name("result.zarr")

        result_inv = runner.invoke(
            cli,
            [
                "apply-inv-tf",
                str(input_path),
                str(tf_path),
                "-c",
                str(config_path),
                "-o",
                str(result_path),
            ],
            catch_exceptions=False,
        )
        assert result_path.exists()
        assert result_inv.exit_code == 0
        assert "Reconstructing" in result_inv.output

        # Check output
        result_dataset = open_ome_zarr(result_path)
        assert result_dataset["0"].shape[0] in {1, 2}
        assert result_dataset["0"].shape[3:] == (5, 6)

        # Test direct recon
        result_inv = runner.invoke(
            cli,
            [
                "reconstruct",
                str(input_path),
                "-c",
                str(config_path),
                "-o",
                str(result_path),
            ],
        )
        assert result_path.exists()
        assert result_inv.exit_code == 0
        assert "Reconstructing" in result_inv.output
