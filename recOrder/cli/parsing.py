import click
from typing import Callable
from iohub.ngff import open_ome_zarr, Plate
from torch.multiprocessing import mp
from natsort import natsorted
from pathlib import Path


def _validate_fov_path(
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


def _convert_to_Path(ctx, param, value):
    if value:
        value = Path(value)
    else:
        value = None
    return value


def input_data_path_argument() -> Callable:
    def decorator(f: Callable) -> Callable:
        return click.argument(
            "input-data-path",
            type=click.Path(exists=True),
            callback=_validate_fov_path,
            nargs=-1,
        )(f)

    return decorator


def config_path_option() -> Callable:
    def decorator(f: Callable) -> Callable:
        return click.option(
            "--config-path",
            "-c",
            required=True,
            help="Path to config.yml",
            callback=_convert_to_Path,
        )(f)

    return decorator


def output_dataset_option(default) -> Callable:
    click_options = [
        click.option(
            "--output-path",
            "-o",
            default=default,
            help="Path to output.zarr",
            callback=_convert_to_Path,
        )
    ]
    # good place to add chunking, overwrite flag, etc

    def decorator(f: Callable) -> Callable:
        for opt in click_options:
            f = opt(f)
        return f

    return decorator


# TODO: this setting will have to be collected from SLURM?
def processes_option(default: int = None) -> Callable:
    def check_processes_option(ctx, param, value):
        max_processes = mp.cpu_count()
        if value > max_processes:
            raise click.BadParameter(
                f"Maximum number of processes is {max_processes}"
            )
        return value

    def decorator(f: Callable) -> Callable:
        return click.option(
            "--num_processes",
            "-j",
            default=default or mp.cpu_count(),
            type=int,
            help="Number of processes to run in parallel.",
            callback=check_processes_option,
        )(f)

    return decorator
