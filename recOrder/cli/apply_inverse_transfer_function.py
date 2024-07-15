import itertools
import warnings
from functools import partial
from pathlib import Path

import click
import numpy as np
import time
import torch
import torch.multiprocessing as mp
import submitit
import sys
from iohub import open_ome_zarr

from recOrder.cli import apply_inverse_models
from recOrder.cli.parsing import (
    config_filepath,
    input_position_dirpaths,
    output_dirpath,
    processes_option,
    transfer_function_dirpath,
)
from recOrder.cli.printing import echo_headline, echo_settings
from recOrder.cli.settings import ReconstructionSettings
from recOrder.cli.utils import (
    apply_inverse_to_zyx_and_save,
    create_empty_hcs_zarr,
)
from recOrder.io import utils


def _check_background_consistency(
    background_shape, data_shape, input_channel_names
):
    data_cyx_shape = (len(input_channel_names),) + data_shape[3:]
    if background_shape != data_cyx_shape:
        raise ValueError(
            f"Background shape {background_shape} does not match data shape {data_cyx_shape}"
        )


def get_reconstruction_output_metadata(position_path: Path, config_path: Path):
    # Get non-OME-Zarr plate-level metadata if it's available
    plate_metadata = {}
    try:
        input_plate = open_ome_zarr(
            position_path.parent.parent.parent, mode="r"
        )
        plate_metadata = dict(input_plate.zattrs)
        plate_metadata.pop("plate")
    except RuntimeError:
        warnings.warn(
            "Position is not part of a plate...no plate metadata will be copied."
        )

    # Load the first position to infer dataset information
    input_dataset = open_ome_zarr(str(position_path), mode="r")
    T, _, Z, Y, X = input_dataset.data.shape

    settings = utils.yaml_to_model(config_path, ReconstructionSettings)

    # Simplify important settings names
    recon_biref = settings.birefringence is not None
    recon_phase = settings.phase is not None
    recon_fluo = settings.fluorescence is not None
    recon_dim = settings.reconstruction_dimension

    # Prepare output dataset
    channel_names = []
    if recon_biref:
        channel_names.append("Retardance")
        channel_names.append("Orientation")
        channel_names.append("BF")
        channel_names.append("Pol")
    if recon_phase:
        if recon_dim == 2:
            channel_names.append("Phase2D")
        elif recon_dim == 3:
            channel_names.append("Phase3D")
    if recon_fluo:
        fluor_name = settings.input_channel_names[0]
        if recon_dim == 2:
            channel_names.append(fluor_name + "_Density2D")
        elif recon_dim == 3:
            channel_names.append(fluor_name + "_Density3D")

    if recon_dim == 2:
        output_z_shape = 1
    elif recon_dim == 3:
        output_z_shape = input_dataset.data.shape[2]

    return {
        "shape": (T, len(channel_names), output_z_shape, Y, X),
        "chunks": (1, 1, 1, Y, X),
        "scale": input_dataset.scale,
        "channel_names": channel_names,
        "dtype": np.float32,
        "plate_metadata": plate_metadata,
    }


def apply_inverse_transfer_function_single_position(
    input_position_dirpath: Path,
    transfer_function_dirpath: Path,
    config_filepath: Path,
    output_position_dirpath: Path,
    num_processes,
    output_channel_names: list[str],
) -> None:
    echo_headline("\nStarting reconstruction...")

    # Load datasets
    transfer_function_dataset = open_ome_zarr(transfer_function_dirpath)
    input_dataset = open_ome_zarr(input_position_dirpath)
    output_dataset = open_ome_zarr(output_position_dirpath, mode="r+")

    # Load config file
    settings = utils.yaml_to_model(config_filepath, ReconstructionSettings)

    # Check input channel names
    if not set(settings.input_channel_names).issubset(
        input_dataset.channel_names
    ):
        raise ValueError(
            f"Each of the input_channel_names = {settings.input_channel_names} in {config_filepath} must appear in the dataset {input_position_dirpath} which currently contains channel_names = {input_dataset.channel_names}."
        )

    # Find input channel indices
    input_channel_indices = []
    for input_channel_name in settings.input_channel_names:
        input_channel_indices.append(
            input_dataset.channel_names.index(input_channel_name)
        )

    # Find output channel indices
    output_channel_indices = []
    for output_channel_name in output_channel_names:
        output_channel_indices.append(
            output_dataset.channel_names.index(output_channel_name)
        )

    # Find time indices
    if settings.time_indices == "all":
        time_indices = range(input_dataset.data.shape[0])
    elif isinstance(settings.time_indices, list):
        time_indices = settings.time_indices
    elif isinstance(settings.time_indices, int):
        time_indices = [settings.time_indices]

    # Check for invalid times
    time_ubound = input_dataset.data.shape[0] - 1
    if np.max(time_indices) > time_ubound:
        raise ValueError(
            f"time_indices = {time_indices} includes a time index beyond the maximum index of the dataset = {time_ubound}"
        )

    # Simplify important settings names
    recon_biref = settings.birefringence is not None
    recon_phase = settings.phase is not None
    recon_fluo = settings.fluorescence is not None
    recon_dim = settings.reconstruction_dimension

    # Prepare birefringence parameters
    if settings.birefringence is not None:
        # settings.birefringence has more parameters than waveorder needs,
        # so this section converts the settings to a dict and separates the
        # waveorder parameters (biref_inverse_dict) from the recorder
        # parameters (cyx_no_sample_data, and wavelength_illumination)
        biref_inverse_dict = settings.birefringence.apply_inverse.dict()

        # Resolve background path into array
        background_path = biref_inverse_dict.pop("background_path")
        if background_path != "":
            cyx_no_sample_data = utils.load_background(background_path)
            _check_background_consistency(
                cyx_no_sample_data.shape,
                input_dataset.data.shape,
                settings.input_channel_names,
            )
        else:
            cyx_no_sample_data = None

        # Get illumination wavelength for retardance radians -> nanometers conversion
        biref_wavelength_illumination = biref_inverse_dict.pop(
            "wavelength_illumination"
        )

    # Prepare the apply_inverse_model_function and its arguments

    # [biref only]
    if recon_biref and (not recon_phase):
        echo_headline("Reconstructing birefringence with settings:")
        echo_settings(settings.birefringence)

        # Setup parameters for apply_inverse_to_zyx_and_save
        apply_inverse_model_function = apply_inverse_models.birefringence
        apply_inverse_args = {
            "cyx_no_sample_data": cyx_no_sample_data,
            "wavelength_illumination": biref_wavelength_illumination,
            "recon_dim": recon_dim,
            "biref_inverse_dict": biref_inverse_dict,
            "transfer_function_dataset": transfer_function_dataset,
        }

    # [phase only]
    if recon_phase and (not recon_biref):
        echo_headline("Reconstructing phase with settings:")
        echo_settings(settings.phase.apply_inverse)

        # Setup parameters for apply_inverse_to_zyx_and_save
        apply_inverse_model_function = apply_inverse_models.phase
        apply_inverse_args = {
            "recon_dim": recon_dim,
            "settings_phase": settings.phase,
            "transfer_function_dataset": transfer_function_dataset,
        }

    # [biref and phase]
    if recon_biref and recon_phase:
        echo_headline("Reconstructing birefringence and phase with settings:")
        echo_settings(settings.birefringence.apply_inverse)
        echo_settings(settings.phase.apply_inverse)

        # Setup parameters for apply_inverse_to_zyx_and_save
        apply_inverse_model_function = (
            apply_inverse_models.birefringence_and_phase
        )
        apply_inverse_args = {
            "cyx_no_sample_data": cyx_no_sample_data,
            "wavelength_illumination": biref_wavelength_illumination,
            "recon_dim": recon_dim,
            "biref_inverse_dict": biref_inverse_dict,
            "settings_phase": settings.phase,
            "transfer_function_dataset": transfer_function_dataset,
        }

    # [fluo]
    if recon_fluo:
        echo_headline("Reconstructing fluorescence with settings:")
        echo_settings(settings.fluorescence.apply_inverse)

        # Setup parameters for apply_inverse_to_zyx_and_save
        apply_inverse_model_function = apply_inverse_models.fluorescence
        apply_inverse_args = {
            "recon_dim": recon_dim,
            "settings_fluorescence": settings.fluorescence,
            "transfer_function_dataset": transfer_function_dataset,
        }

    # Make the partial function for apply inverse
    partial_apply_inverse_to_zyx_and_save = partial(
        apply_inverse_to_zyx_and_save,
        apply_inverse_model_function,
        input_dataset,
        output_position_dirpath,
        input_channel_indices,
        output_channel_indices,
        **apply_inverse_args,
    )

    # Multiprocessing logic
    if num_processes > 1:
        # Loop through T, processing and writing as we go
        click.echo(
            f"\nStarting multiprocess pool with {num_processes} processes"
        )
        with mp.Pool(num_processes) as p:
            p.starmap(
                partial_apply_inverse_to_zyx_and_save,
                itertools.product(time_indices),
            )
    else:
        for t_idx in time_indices:
            partial_apply_inverse_to_zyx_and_save(t_idx)

    # Save metadata at position level
    output_dataset.zattrs["settings"] = settings.dict()

    echo_headline(f"Closing {output_position_dirpath}\n")
    output_dataset.close()
    transfer_function_dataset.close()
    input_dataset.close()

    echo_headline(
        f"Recreate this reconstruction with:\n$ recorder apply-inv-tf {input_position_dirpath} {transfer_function_dirpath} -c {config_filepath} -o {output_position_dirpath}"
    )


def apply_inverse_transfer_function_cli(
    input_position_dirpaths: list[Path],
    transfer_function_dirpath: Path,
    config_filepath: Path,
    output_dirpath: Path,
    num_processes: int = 1,
) -> None:
    output_metadata = get_reconstruction_output_metadata(
        input_position_dirpaths[0], config_filepath
    )
    create_empty_hcs_zarr(
        store_path=output_dirpath,
        position_keys=[p.parts[-3:] for p in input_position_dirpaths],
        **output_metadata,
    )
    # Initialize torch num of threads and interoeration operations
    if num_processes > 1:
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)

    # Estimate resources
    num_jobs = len(input_position_dirpaths)
    gb_ram_request = int(32)
    cpu_request = 1

    echo_headline(
        f"Preparing {num_jobs} jobs, each with {gb_ram_request} GB of memory and {cpu_request} CPU."
    )

    # Prepare and submit jobs
    executor = submitit.AutoExecutor(folder="logs")
    executor.update_parameters(
        slurm_array_parallelism=num_jobs,
        slurm_mem_per_cpu=f"{gb_ram_request}G",
        slurm_cpus_per_task=cpu_request,
        # more slurm_*** resource parameters here
    )
    jobs = []

    with executor.batch():  # submits batch on exit
        for input_position_dirpath in input_position_dirpaths:
            job = executor.submit(
                apply_inverse_transfer_function_single_position,
                input_position_dirpath,
                transfer_function_dirpath,
                config_filepath,
                output_dirpath / Path(*input_position_dirpath.parts[-3:]),
                num_processes,
                output_metadata["channel_names"],
            )
            jobs.append(job)  # use for managing dependencies

    # Monitor jobs (will move elsewhere)
    def clear_status(jobs):
        for job in jobs:
            sys.stdout.write("\033[F")  # Move cursor up
            sys.stdout.write("\033[K")  # Clear line

    def print_status(jobs, input_position_dirpaths):
        for job, input_position_dirpath in zip(jobs, input_position_dirpaths):
            if job.state == "COMPLETED":
                color = "\033[32m"  # green
            elif job.state == "RUNNING":
                color = "\033[93m"  # yellow
            else:
                color = "\033[91m"  # red

            try:
                node_name = job.get_info()["NodeList"]
            except:
                node_name = "SUBMITTED"

            sys.stdout.write(
                f"{color}{job.job_id}"
                f"\033[15G {'/'.join(input_position_dirpath.parts[-3:])}"
                f"\033[30G {job.state}"
                f"\033[40G {node_name}"
                f"\033[50G {time.time() - job.watcher._start_time:.0f} s\n"
            )
            sys.stdout.flush()

    def print_header():
        sys.stdout.write(
            "ID\033[15G WELL \033[30G STATUS \033[40G NODE \033[50G ELAPSED\n"
        )
        sys.stdout.flush()

    echo_headline(f"{num_jobs} jobs submitted.")
    try:
        print_header()
        print_status(jobs, input_position_dirpaths)
        while not all(job.done() for job in jobs):
            time.sleep(1)
            clear_status(jobs)
            print_status(jobs, input_position_dirpaths)

        # Print final status
        time.sleep(3)
        clear_status(jobs)
        print_status(jobs, input_position_dirpaths)

    except KeyboardInterrupt:
        for job in jobs:
            job.cancel()
        print("All jobs cancelled.")


@click.command()
@input_position_dirpaths()
@transfer_function_dirpath()
@config_filepath()
@output_dirpath()
@processes_option(default=1)
def apply_inv_tf(
    input_position_dirpaths: list[Path],
    transfer_function_dirpath: Path,
    config_filepath: Path,
    output_dirpath: Path,
    num_processes,
) -> None:
    """
    Apply an inverse transfer function to a dataset using a configuration file.

    Applies a transfer function to all positions in the list `input-position-dirpaths`,
    so all positions must have the same TCZYX shape.

    Appends channels to ./output.zarr, so multiple reconstructions can fill a single store.

    See /examples for example configuration files.

    >> recorder apply-inv-tf -i ./input.zarr/*/*/* -t ./transfer-function.zarr -c /examples/birefringence.yml -o ./output.zarr
    """
    apply_inverse_transfer_function_cli(
        input_position_dirpaths,
        transfer_function_dirpath,
        config_filepath,
        output_dirpath,
        num_processes,
    )
