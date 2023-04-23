import click
from recOrder.cli.parsing import config_path_option, output_dataset_options


@click.command()
@config_path_option()
@output_dataset_options()
def apply_inverse_transfer_function(
    transfer_function_path, config_path, input_path, output_path
):
    "Invert and apply a transfer function"
    return NotImplementedError
