from pathlib import Path

import click
import numpy as np
import torch
from iohub import open_ome_zarr

from recOrder.cli import apply_inverse_models
from recOrder.cli.parsing import (
    config_filepath,
    input_position_dirpaths,
    output_dirpath,
    transfer_function_dirpath,
)
from recOrder.cli.printing import echo_headline, echo_settings
from recOrder.cli.settings import ReconstructionSettings
from recOrder.cli.utils import create_empty_hcs_zarr
from recOrder.io import utils


def _check_background_consistency(background_shape, data_shape):
    data_cyx_shape = (data_shape[1],) + data_shape[3:]
    if background_shape != data_cyx_shape:
        raise ValueError(
            f"Background shape {background_shape} does not match data shape {data_cyx_shape}"
        )


def get_reconstruction_output_metadata(position_path: Path, config_path: Path):
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
    else:
        raise ValueError("recon_dims not 2 nor 3. Please double check value")

    return {
        "shape": (T, len(channel_names), output_z_shape, Y, X),
        "chunks": (1, 1, 1, Y, X),
        "scale": input_dataset.scale,
        "channel_names": channel_names,
        "dtype": np.float32,
    }


def apply_inverse_transfer_function_single_position(
    input_position_dirpath: Path,
    transfer_function_dirpath: Path,
    config_filepath: Path,
    output_position_dirpath: Path,
) -> None:
    echo_headline("Starting reconstruction...")

    # Load datasets
    transfer_function_dataset = open_ome_zarr(transfer_function_dirpath)
    input_dataset = open_ome_zarr(input_position_dirpath)

    # Load config file
    settings = utils.yaml_to_model(config_filepath, ReconstructionSettings)

    # Check input channel names
    if not set(settings.input_channel_names).issubset(
        input_dataset.channel_names
    ):
        raise ValueError(
            f"Each of the input_channel_names = {settings.input_channel_names} in {config_filepath} must appear in the dataset {input_position_dirpath} which currently contains channel_names = {input_dataset.channel_names}."
        )

    # Find channel indices
    channel_indices = []
    for input_channel_name in settings.input_channel_names:
        channel_indices.append(
            input_dataset.channel_names.index(input_channel_name)
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

    # Open output dataset
    output_dataset = open_ome_zarr(
        output_position_dirpath,
        layout="fov",
        mode="a",
    )
    output_array = output_dataset[0]

    # Load data
    tczyx_uint16_numpy = input_dataset.data.oindex[:, channel_indices]
    tczyx_data = torch.tensor(
        np.int32(tczyx_uint16_numpy), dtype=torch.float32
    )  # convert to np.int32 (torch doesn't accept np.uint16), then convert to tensor float32

    # Load background
    if settings.birefringence is not None:
        biref_inverse_dict = settings.birefringence.apply_inverse.dict()

        # Resolve background path into array
        background_path = biref_inverse_dict["background_path"]
        biref_inverse_dict.pop("background_path")
        if background_path != "":
            cyx_no_sample_data = utils.load_background(background_path)
            _check_background_consistency(
                cyx_no_sample_data.shape, input_dataset.data.shape
            )
        else:
            cyx_no_sample_data = None

    for time_index in time_indices:
        # [biref only]
        if recon_biref and (not recon_phase):
            echo_headline("Reconstructing birefringence with settings:")
            echo_settings(settings.birefringence)
            echo_headline("Reconstructing birefringence...")
            output = apply_inverse_models.birefringence(
                tczyx_data[time_index],
                cyx_no_sample_data,
                recon_dim,
                biref_inverse_dict,
                transfer_function_dataset,
            )
        # [phase only]
        if recon_phase and (not recon_biref):
            echo_headline("Reconstructing phase with settings:")
            echo_settings(settings.phase.apply_inverse)
            echo_headline("Reconstructing phase...")
            output = apply_inverse_models.phase(
                tczyx_data[time_index, 0],
                recon_dim,
                settings.phase,
                transfer_function_dataset,
            )

        # [biref and phase]
        if recon_biref and recon_phase:
            echo_headline("Reconstructing phase with settings:")
            echo_settings(settings.phase.apply_inverse)
            echo_headline("Reconstructing birefringence with settings:")
            echo_settings(settings.birefringence.apply_inverse)
            echo_headline("Reconstructing...")
            output = apply_inverse_models.birefringence_and_phase(
                tczyx_data[time_index],
                cyx_no_sample_data,
                recon_dim,
                biref_inverse_dict,
                settings.phase,
                transfer_function_dataset,
            )

        # [fluo]
        if recon_fluo:
            echo_headline("Reconstructing fluorescence with settings:")
            echo_settings(settings.fluorescence.apply_inverse)
            echo_headline("Reconstructing...")
            output = apply_inverse_models.fluorescence(
                tczyx_data[time_index, 0],
                recon_dim,
                settings.fluorescence,
                transfer_function_dataset,
            )

        # Pad to CZYX
        while output.ndim != 4:
            output = torch.unsqueeze(output, 0)

        # Save
        output_array[time_index] = output

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
) -> None:
    output_metadata = get_reconstruction_output_metadata(
        input_position_dirpaths[0], config_filepath
    )
    create_empty_hcs_zarr(
        store_path=output_dirpath,
        position_keys=[p.parts[-3:] for p in input_position_dirpaths],
        **output_metadata,
    )

    for input_position_dirpath in input_position_dirpaths:
        apply_inverse_transfer_function_single_position(
            input_position_dirpath,
            transfer_function_dirpath,
            config_filepath,
            output_dirpath / Path(*input_position_dirpath.parts[-3:]),
        )


@click.command()
@input_position_dirpaths()
@transfer_function_dirpath()
@config_filepath()
@output_dirpath()
def apply_inv_tf(
    input_position_dirpaths: list[Path],
    transfer_function_dirpath: Path,
    config_filepath: Path,
    output_dirpath: Path,
) -> None:
    """
    Apply an inverse transfer function to a dataset using a configuration file.

    Applies a transfer function to all positions in the list `input-position-dirpaths`,
    so all positions must have the same TCZYX shape.

    See /examples for example configuration files.

    >> recorder apply-inv-tf -i ./input.zarr/*/*/* -t ./transfer-function.zarr -c /examples/birefringence.yml -o ./output.zarr
    """
    apply_inverse_transfer_function_cli(
        input_position_dirpaths,
        transfer_function_dirpath,
        config_filepath,
        output_dirpath,
    )
