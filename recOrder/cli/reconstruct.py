import os

import click

from recOrder.cli.apply_inverse_transfer_function import (
    apply_inverse_transfer_function_cli,
)
from recOrder.cli.compute_transfer_function import (
    compute_transfer_function_cli,
)
from recOrder.cli.parsing import (
    config_filepath,
    input_position_dirpaths,
    output_dirpath,
)


@click.command()
@input_position_dirpaths()
@config_filepath()
@output_dirpath()
def reconstruct(input_data_path, config_path, output_path):
    """
    Reconstruct a dataset using a configuration file. This is a
    convenience function for a `compute-tf` call followed by a `apply-inv-tf`
    call.

    See /examples for example configuration files.

    >> recorder reconstruct -i ./input.zarr/*/*/* -c ./examples/birefringence.yml -o ./output.zarr
    """

    # Handle transfer function path
    output_directory = os.path.dirname(output_path)
    transfer_function_path = os.path.join(
        output_directory, "transfer_function.zarr"
    )

    # Compute transfer function and apply inverse
    compute_transfer_function_cli(
        input_data_path, config_path, transfer_function_path
    )
    apply_inverse_transfer_function_cli(
        input_data_path, transfer_function_path, config_path, output_path
    )
