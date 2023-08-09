from pathlib import Path
from typing import Callable

import click
from iohub.ngff import Plate, open_ome_zarr
from natsort import natsorted

from recOrder.cli.option_eat_all import OptionEatAll


def _validate_and_process_paths(
    ctx: click.Context, opt: click.Option, value: str
) -> None:
    # Sort and validate the input paths
    input_paths = [Path(path) for path in natsorted(value)]
    for path in input_paths:
        with open_ome_zarr(path, mode="r") as dataset:
            if isinstance(dataset, Plate):
                raise ValueError(
                    "Please supply a single position instead of an HCS plate. Likely fix: replace 'input.zarr' with 'input.zarr/0/0/0'"
                )
    return input_paths


def input_position_dirpaths() -> Callable:
    def decorator(f: Callable) -> Callable:
        return click.option(
            "--input-position-dirpaths",
            "-i",
            cls=OptionEatAll,
            type=tuple,
            callback=_validate_and_process_paths,
            help="Paths to input positions",
        )(f)

    return decorator


def config_filepath() -> Callable:
    def decorator(f: Callable) -> Callable:
        return click.option(
            "--config-filepath",
            "-c",
            required=True,
            type=click.Path(exists=True, file_okay=True, dir_okay=False),
            help="Path to YAML configuration file",
        )(f)

    return decorator


def transfer_function_dirpath() -> Callable:
    def decorator(f: Callable) -> Callable:
        return click.option(
            "--transfer-function",
            "-t",
            required=True,
            type=click.Path(exists=False, file_okay=False, dir_okay=True),
            help="Path to transfer function .zarr",
        )(f)

    return decorator


def output_dirpath() -> Callable:
    def decorator(f: Callable) -> Callable:
        return click.option(
            "--output-dirpath",
            "-o",
            required=True,
            type=click.Path(exists=False, file_okay=False, dir_okay=True),
            help="Path to output directory",
        )(f)

    return decorator
