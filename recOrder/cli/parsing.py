# lifted from dexp

import click
import warnings
import glob
from typing import Callable, Sequence


def input_path_argument() -> Callable:
    def decorator(f: Callable) -> Callable:
        return click.argument(
            "input-path",
            nargs=1,
        )(f)

    return decorator


def config_path_option() -> Callable:
    def decorator(f: Callable) -> Callable:
        return click.option(
            "--config-path", "-c", default=None, help="Path to config.yml"
        )(f)

    return decorator


def output_dataset_options() -> Callable:
    click_options = [
        click.option(
            "--output-path",
            "-o",
            default="./output.zarr",
            help="Path to output.zarr",
        )
    ]
    # good place to add chunking, overwrite flag, etc

    def decorator(f: Callable) -> Callable:
        for opt in click_options:
            f = opt(f)
        return f

    return decorator
