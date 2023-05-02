# lifted from dexp

import click
import warnings
import glob
from typing import Callable, Sequence
import multiprocessing as mp


def input_data_path_argument() -> Callable:
    def decorator(f: Callable) -> Callable:
        return click.argument(
            "input-data-path",
            type=click.Path(exists=True),
            nargs=-1,
        )(f)

    return decorator


def config_path_option() -> Callable:
    def decorator(f: Callable) -> Callable:
        return click.option(
            "--config-path", "-c", default=None, help="Path to config.yml"
        )(f)

    return decorator


def output_dataset_options(default) -> Callable:
    click_options = [
        click.option(
            "--output-path",
            "-o",
            default=default,
            help="Path to output.zarr",
        )
    ]
    # good place to add chunking, overwrite flag, etc

    def decorator(f: Callable) -> Callable:
        for opt in click_options:
            f = opt(f)
        return f

    return decorator


def cores_option(default: int = None) -> Callable:
    def check_cores_option(ctx, param, value):
        max_cores = mp.cpu_count()
        if value > max_cores:
            raise click.BadParameter(f"Maximum number of cores is {max_cores}")
        return value

    def decorator(f: Callable) -> Callable:
        return click.option(
            "--num_cores",
            "-j",
            default=default or mp.cpu_count(),
            type=int,
            help="Number of cores to use for processing.",
            callback=check_cores_option,
        )(f)

    return decorator
