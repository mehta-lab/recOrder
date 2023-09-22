import datetime
import os
import glob
from slurmkit import SlurmParams, slurm_function, submit_function
from natsort import natsorted
import click
from iohub import open_ome_zarr
from recOrder.cli.settings import ReconstructionSettings
import torch
from recOrder.io import utils
from recOrder.cli.utils import (
    apply_inverse_to_zyx_and_save,
    create_empty_hcs_zarr,
)
from recOrder.cli.compute_transfer_function import (
    compute_transfer_function_cli,
)

from recOrder.cli.apply_inverse_transfer_function import (
    get_reconstruction_output_metadata,
    apply_inverse_transfer_function_single_position,
)
from pathlib import Path


# Reconstruction parameters
config_path = (
    "/home/eduardo.hirata/repos/recOrder/recOrder/tests/cli_tests/phase.yml"
)
transfer_function_path = "/home/eduardo.hirata/repos/recOrder/recOrder/tests/cli_tests/TF_phase3D.zarr"

# io parameters
input_position_dirpaths = "/home/eduardo.hirata/repos/recOrder/recOrder/tests/cli_tests/data_temp/2022_08_04_20x_04NA_BF.zarr/*/*/*"
output_dirpath = "/home/eduardo.hirata/repos/recOrder/recOrder/tests/cli_tests/test_delete_phase.zarr"
# sbatch and resource parameters
cpus_per_task = 16
mem_per_cpu = "16G"
time = 40  # minutes

# Path handling
input_position_dirpaths = [
    Path(path) for path in natsorted(glob.glob(input_position_dirpaths))
]
output_dirpath = Path(output_dirpath)
slurm_out_path = output_dirpath.parent / "slurm_output/recon-%j.out"

transfer_function_path = Path(transfer_function_path)
config_path = Path(config_path)

## First compute-tf
# Handle transfer function path
# Compute transfer function
compute_transfer_function_cli(
    input_position_dirpath=input_position_dirpaths[0],
    config_filepath=config_path,
    output_dirpath=transfer_function_path,
)

## Second apply-inv-tf
output_metadata = get_reconstruction_output_metadata(
    input_position_dirpaths[0], config_path
)

create_empty_hcs_zarr(
    store_path=output_dirpath,
    position_keys=[p.parts[-3:] for p in input_position_dirpaths],
    **output_metadata,
)

click.echo(f"in: {input_position_dirpaths}, out: {output_dirpath}")

# prepare slurm parameters
params = SlurmParams(
    partition="cpu",
    cpus_per_task=cpus_per_task,
    mem_per_cpu=mem_per_cpu,
    time=datetime.timedelta(minutes=time),
    output=slurm_out_path,
)

# wrap our process_single_position() function with slurmkit
slurm_reconstruct_single_position = slurm_function(
    apply_inverse_transfer_function_single_position
)
reconstruct_func = slurm_reconstruct_single_position(
    transfer_function_dirpath=transfer_function_path,
    config_filepath=config_path,
    num_processes=cpus_per_task,
)

# generate an array of jobs by passing the in_path and out_path to slurm wrapped function
recon_jobs = [
    submit_function(
        reconstruct_func,
        slurm_params=params,
        input_position_dirpath=input_position_dirpath,
        output_position_dirpath=output_dirpath
        / Path(*input_position_dirpath.parts[-3:]),
    )
    for input_position_dirpath in input_position_dirpaths
]
