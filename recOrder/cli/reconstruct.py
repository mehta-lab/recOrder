import click
from recOrder.cli.compute_transfer_function import (
    compute_transfer_function_cli,
)
from recOrder.cli.apply_inverse_transfer_function import (
    apply_inverse_transfer_function_cli,
)
from recOrder.cli.parsing import (
    input_data_path_argument,
    config_path_option,
    output_dataset_options,
)


@click.command()
@click.help_option("-h", "--help")
@input_data_path_argument()
@config_path_option()
@output_dataset_options(default="./reconstruction.zarr")
def reconstruct(input_data_path, config_path, output_path):
    transfer_function_path = "transfer_function.zarr"
    compute_transfer_function_cli(input_data_path, config_path, transfer_function_path)
    apply_inverse_transfer_function_cli(input_data_path, transfer_function_path, config_path, output_path=)
    """Reconstruct a dataset using configuration file."""
