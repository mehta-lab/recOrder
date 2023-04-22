import click
from recOrder.cli.view import view
from recOrder.cli.reconstruct import reconstruct
from recOrder.cli.compute_transfer_function import compute_transfer_function
from recOrder.cli.apply_inverse_transfer_function import (
    apply_inverse_transfer_function,
)


@click.group()
def cli():
    print(
        "\033[92mrecOrder: Computational Toolkit for Label-Free Imaging\033[0m\n"
    )


cli.add_command(view)
cli.add_command(reconstruct)
cli.add_command(compute_transfer_function)
cli.add_command(apply_inverse_transfer_function)
