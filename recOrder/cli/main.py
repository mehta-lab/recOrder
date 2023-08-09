import click

from recOrder.cli.apply_inverse_transfer_function import apply_inv_tf
from recOrder.cli.compute_transfer_function import compute_tf
from recOrder.cli.reconstruct import reconstruct


@click.group()
def cli():
    """\033[92mrecOrder: Computational Toolkit for Label-Free Imaging\033[0m\n"""


cli.add_command(reconstruct)
cli.add_command(compute_tf)
cli.add_command(apply_inv_tf)
