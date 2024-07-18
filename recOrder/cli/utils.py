from pathlib import Path
from typing import Tuple

import click
import datetime
import numpy as np
import re
import torch
import time
import submitit
import sys
from iohub.ngff import Position, open_ome_zarr
from iohub.ngff_meta import TransformationMeta
from numpy.typing import DTypeLike


def create_empty_hcs_zarr(
    store_path: Path,
    position_keys: list[Tuple[str]],
    shape: Tuple[int],
    chunks: Tuple[int],
    scale: Tuple[float],
    channel_names: list[str],
    dtype: DTypeLike,
    plate_metadata: dict = {},
) -> None:
    """If the plate does not exist, create an empty zarr plate.

    If the plate exists, append positions and channels if they are not
    already in the plate.

    Parameters
    ----------
    store_path : Path
        hcs plate path
    position_keys : list[Tuple[str]]
        Position keys, will append if not present in the plate.
        e.g. [("A", "1", "0"), ("A", "1", "1")]
    shape : Tuple[int]
    chunks : Tuple[int]
    scale : Tuple[float]
    channel_names : list[str]
        Channel names, will append if not present in metadata.
    dtype : DTypeLike
    plate_metadata : dict
    """

    # Create plate
    output_plate = open_ome_zarr(
        str(store_path), layout="hcs", mode="a", channel_names=channel_names
    )

    # Pass metadata
    output_plate.zattrs.update(plate_metadata)

    # Create positions
    for position_key in position_keys:
        position_key_string = "/".join(position_key)
        # Check if position is already in the store, if not create it
        if position_key_string not in output_plate.zgroup:
            position = output_plate.create_position(*position_key)

            _ = position.create_zeros(
                name="0",
                shape=shape,
                chunks=chunks,
                dtype=dtype,
                transform=[TransformationMeta(type="scale", scale=scale)],
            )
        else:
            position = output_plate[position_key_string]

        # Check if channel_names are already in the store, if not append them
        for channel_name in channel_names:
            # Read channel names directly from metadata to avoid race conditions
            metadata_channel_names = [
                channel.label for channel in position.metadata.omero.channels
            ]
            if channel_name not in metadata_channel_names:
                position.append_channel(channel_name, resize_arrays=True)


def apply_inverse_to_zyx_and_save(
    func,
    position: Position,
    output_path: Path,
    input_channel_indices: list[int],
    output_channel_indices: list[int],
    t_idx: int = 0,
    **kwargs,
) -> None:
    """Load a zyx array from a Position object, apply a transformation and save the result to file"""
    click.echo(f"Reconstructing t={t_idx}")

    # Load data
    czyx_uint16_numpy = position.data.oindex[t_idx, input_channel_indices]

    # convert to np.int32 (torch doesn't accept np.uint16), then convert to tensor float32
    czyx_data = torch.tensor(np.int32(czyx_uint16_numpy), dtype=torch.float32)

    # Apply transformation
    reconstruction_czyx = func(czyx_data, **kwargs)

    # Write to file
    # for c, recon_zyx in enumerate(reconstruction_zyx):
    with open_ome_zarr(output_path, mode="r+") as output_dataset:
        output_dataset[0].oindex[
            t_idx, output_channel_indices
        ] = reconstruction_czyx
    click.echo(f"Finished Writing.. t={t_idx}")


def _clear_status(jobs):
    for job in jobs:
        sys.stdout.write("\033[F")  # Move cursor up
        sys.stdout.write("\033[K")  # Clear line


def _print_status(jobs, position_dirpaths, elapsed_list):
    for i, (job, position_dirpath) in enumerate(zip(
        jobs, position_dirpaths
    )):
        if job.state == "COMPLETED":
            color = "\033[32m"  # green
        elif job.state == "RUNNING":
            color = "\033[93m"  # yellow
            elapsed_list[i] += 1  # inexact timing
        else:
            color = "\033[91m"  # red

        try:
            node_name = job.get_info()["NodeList"]
        except:
            node_name = "SUBMITTED"

        sys.stdout.write(
            f"{color}{job.job_id}"
            f"\033[15G {'/'.join(position_dirpath.parts[-3:])}"
            f"\033[30G {job.state}"
            f"\033[40G {node_name}"
            f"\033[50G {elapsed_list[i]} s\n"
        )
        sys.stdout.flush()
    return elapsed_list


def _print_header():
    sys.stdout.write(
        "\033[96mID\033[15G WELL \033[30G STATUS \033[40G NODE \033[50G ELAPSED\n"
    )
    sys.stdout.flush()


def monitor_jobs(jobs: list[submitit.Job], position_dirpaths: list[Path]):
    """Displays the status of a list of submitit jobs with corresponding paths.

    Parameters
    ----------
    jobs : list[submitit.Job]
        List of submitit jobs
    position_dirpaths : list[Path]
        List of corresponding position paths
    """
    if not len(jobs) == len(position_dirpaths):
        raise ValueError(
            "The number of jobs and position_dirpaths should be the same."
        )

    elapsed_list = [0] * len(jobs)  # timer for each job
    try:
        _print_header()
        _print_status(jobs, position_dirpaths, elapsed_list)
        while not all(job.done() for job in jobs):
            time.sleep(1)
            _clear_status(jobs)
            elapsed_list = _print_status(jobs, position_dirpaths, elapsed_list)

        # Print final status
        time.sleep(1)
        _clear_status(jobs)
        _print_status(jobs, position_dirpaths, elapsed_list)

    except KeyboardInterrupt:
        for job in jobs:
            job.cancel()
        print("All jobs cancelled.")

