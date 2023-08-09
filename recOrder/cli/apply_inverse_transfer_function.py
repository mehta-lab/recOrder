from typing import List

import click
import numpy as np
import torch
from iohub import open_ome_zarr
from iohub.ngff_meta import TransformationMeta
from waveorder.models import (
    inplane_oriented_thick_pol3d,
    isotropic_fluorescent_thick_3d,
    isotropic_thin_3d,
    phase_thick_3d,
)

from recOrder.cli.parsing import (
    config_filepath,
    input_position_dirpaths,
    output_dirpath,
    transfer_function_dirpath,
)
from recOrder.cli.printing import echo_headline, echo_settings
from recOrder.cli.settings import ReconstructionSettings
from recOrder.cli.utils import get_output_paths
from recOrder.io import utils


def _check_background_consistency(background_shape, data_shape):
    data_cyx_shape = (data_shape[1],) + data_shape[3:]
    if background_shape != data_cyx_shape:
        raise ValueError(
            f"Background shape {background_shape} does not match data shape {data_cyx_shape}"
        )


def apply_inverse_transfer_function_cli(
    input_position_dirpath,
    transfer_function_dirpath,
    config_filepath,
    output_position_dirpath,
):
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
            channel_names.append(fluor_name + "2D")
        elif recon_dim == 3:
            channel_names.append(fluor_name + "3D")

    if recon_dim == 2:
        output_z_shape = 1
    elif recon_dim == 3:
        output_z_shape = input_dataset.data.shape[2]

    output_shape = (
        input_dataset.data.shape[0],
        len(channel_names),
        output_z_shape,
    ) + input_dataset.data.shape[3:]

    # Create output dataset
    output_dataset = open_ome_zarr(
        output_position_dirpath, layout="fov", mode="a", channel_names=channel_names
    )

    # Create an empty TCZYX array if it doesn't exist
    if "0" not in output_dataset:
        output_array = output_dataset.create_zeros(
            name="0",
            shape=output_shape,
            dtype=np.float32,
            chunks=(
                1,
                1,
                1,
            )
            + input_dataset.data.shape[3:],  # chunk by YX
            transform=[
                TransformationMeta(type="scale", scale=input_dataset.scale)
            ],
        )
    else:
        output_array = output_dataset[0]

    # Load data
    tczyx_uint16_numpy = input_dataset.data.oindex[:, channel_indices]
    tczyx_data = torch.tensor(
        np.int32(tczyx_uint16_numpy), dtype=torch.float32
    )  # convert to np.int32 (torch doesn't accept np.uint16), then convert to tensor float32

    # Prepare background dataset
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

    # Main reconstruction logic
    # Eight different cases [2, 3] x [biref only, phase only, biref and phase, fluorescence]

    # [biref only] [2 or 3]
    if recon_biref and (not recon_phase):
        echo_headline("Reconstructing birefringence with settings:")
        echo_settings(settings.birefringence.apply_inverse)
        echo_headline("Reconstructing birefringence...")

        # Load transfer function
        intensity_to_stokes_matrix = torch.tensor(
            transfer_function_dataset["intensity_to_stokes_matrix"][0, 0, 0]
        )

        for time_index in time_indices:
            # Apply
            reconstructed_parameters = (
                inplane_oriented_thick_pol3d.apply_inverse_transfer_function(
                    tczyx_data[time_index],
                    intensity_to_stokes_matrix,
                    cyx_no_sample_data=cyx_no_sample_data,
                    project_stokes_to_2d=(recon_dim == 2),
                    **biref_inverse_dict,
                )
            )
            # Save
            for param_index, parameter in enumerate(reconstructed_parameters):
                output_array[time_index, param_index] = parameter

    # [phase only]
    if recon_phase and (not recon_biref):
        echo_headline("Reconstructing phase with settings:")
        echo_settings(settings.phase.apply_inverse)
        echo_headline("Reconstructing phase...")

        # check data shapes
        if tczyx_data.shape[1] != 1:
            raise ValueError(
                "You have requested a phase-only reconstruction, but the input dataset has more than one channel."
            )

        # [phase only, 2]
        if recon_dim == 2:
            # Load transfer functions
            absorption_transfer_function = torch.tensor(
                transfer_function_dataset["absorption_transfer_function"][0, 0]
            )
            phase_transfer_function = torch.tensor(
                transfer_function_dataset["phase_transfer_function"][0, 0]
            )

            for time_index in time_indices:
                # Apply
                (
                    _,
                    yx_phase,
                ) = isotropic_thin_3d.apply_inverse_transfer_function(
                    tczyx_data[time_index, 0],
                    absorption_transfer_function,
                    phase_transfer_function,
                    **settings.phase.apply_inverse.dict(),
                )

                # Save
                output_array[time_index, -1, 0] = yx_phase

        # [phase only, 3]
        elif recon_dim == 3:
            # Load transfer functions
            real_potential_transfer_function = torch.tensor(
                transfer_function_dataset["real_potential_transfer_function"][
                    0, 0
                ]
            )
            imaginary_potential_transfer_function = torch.tensor(
                transfer_function_dataset[
                    "imaginary_potential_transfer_function"
                ][0, 0]
            )

            # Apply
            for time_index in time_indices:
                zyx_phase = phase_thick_3d.apply_inverse_transfer_function(
                    tczyx_data[time_index, 0],
                    real_potential_transfer_function,
                    imaginary_potential_transfer_function,
                    z_padding=settings.phase.transfer_function.z_padding,
                    z_pixel_size=settings.phase.transfer_function.z_pixel_size,
                    wavelength_illumination=settings.phase.transfer_function.wavelength_illumination,
                    **settings.phase.apply_inverse.dict(),
                )
                # Save
                output_array[time_index, -1] = zyx_phase

    # [biref and phase]
    if recon_biref and recon_phase:
        echo_headline("Reconstructing phase with settings:")
        echo_settings(settings.phase.apply_inverse)
        echo_headline("Reconstructing birefringence with settings:")
        echo_settings(settings.birefringence.apply_inverse)
        echo_headline("Reconstructing...")

        # Load birefringence transfer function
        intensity_to_stokes_matrix = torch.tensor(
            transfer_function_dataset["intensity_to_stokes_matrix"][0, 0, 0]
        )

        # [biref and phase, 2]
        if recon_dim == 2:
            # Load phase transfer functions
            absorption_transfer_function = torch.tensor(
                transfer_function_dataset["absorption_transfer_function"][0, 0]
            )
            phase_transfer_function = torch.tensor(
                transfer_function_dataset["phase_transfer_function"][0, 0]
            )

            for time_index in time_indices:
                # Apply
                reconstructed_parameters_2d = inplane_oriented_thick_pol3d.apply_inverse_transfer_function(
                    tczyx_data[time_index],
                    intensity_to_stokes_matrix,
                    cyx_no_sample_data=cyx_no_sample_data,
                    project_stokes_to_2d=True,
                    **biref_inverse_dict,
                )

                reconstructed_parameters_3d = inplane_oriented_thick_pol3d.apply_inverse_transfer_function(
                    tczyx_data[time_index],
                    intensity_to_stokes_matrix,
                    cyx_no_sample_data=cyx_no_sample_data,
                    project_stokes_to_2d=False,
                    **biref_inverse_dict,
                )

                brightfield_3d = reconstructed_parameters_3d[2]

                (
                    _,
                    yx_phase,
                ) = isotropic_thin_3d.apply_inverse_transfer_function(
                    brightfield_3d,
                    absorption_transfer_function,
                    phase_transfer_function,
                    **settings.phase.apply_inverse.dict(),
                )

                # Save
                for param_index, parameter in enumerate(
                    reconstructed_parameters_2d
                ):
                    output_array[time_index, param_index] = parameter
                output_array[time_index, -1, 0] = yx_phase

        # [biref and phase, 3]
        elif recon_dim == 3:
            # Load phase transfer functions
            intensity_to_stokes_matrix = torch.tensor(
                transfer_function_dataset["intensity_to_stokes_matrix"][
                    0, 0, 0
                ]
            )
            # Load transfer functions
            real_potential_transfer_function = torch.tensor(
                transfer_function_dataset["real_potential_transfer_function"][
                    0, 0
                ]
            )
            imaginary_potential_transfer_function = torch.tensor(
                transfer_function_dataset[
                    "imaginary_potential_transfer_function"
                ][0, 0]
            )

            # Apply
            for time_index in time_indices:
                reconstructed_parameters_3d = inplane_oriented_thick_pol3d.apply_inverse_transfer_function(
                    tczyx_data[time_index],
                    intensity_to_stokes_matrix,
                    cyx_no_sample_data=cyx_no_sample_data,
                    project_stokes_to_2d=False,
                    **biref_inverse_dict,
                )

                brightfield_3d = reconstructed_parameters_3d[2]

                zyx_phase = phase_thick_3d.apply_inverse_transfer_function(
                    brightfield_3d,
                    real_potential_transfer_function,
                    imaginary_potential_transfer_function,
                    z_padding=settings.phase.transfer_function.z_padding,
                    z_pixel_size=settings.phase.transfer_function.z_pixel_size,
                    wavelength_illumination=settings.phase.transfer_function.wavelength_illumination,
                    **settings.phase.apply_inverse.dict(),
                )
                # Save
                for param_index, parameter in enumerate(
                    reconstructed_parameters_3d
                ):
                    output_array[time_index, param_index] = parameter
                output_array[time_index, -1] = zyx_phase

    # [fluo]
    if recon_fluo:
        echo_headline("Reconstructing fluorescence with settings:")
        echo_settings(settings.fluorescence.apply_inverse)
        echo_headline("Reconstructing...")

        # [fluo, 2]
        if recon_dim == 2:
            raise NotImplementedError
        # [fluo, 3]
        elif recon_dim == 3:
            # Load transfer functions
            optical_transfer_function = torch.tensor(
                transfer_function_dataset["optical_transfer_function"][0, 0]
            )

            # Apply
            for time_index in time_indices:
                zyx_recon = isotropic_fluorescent_thick_3d.apply_inverse_transfer_function(
                    tczyx_data[time_index, 0],
                    optical_transfer_function,
                    settings.fluorescence.transfer_function.z_padding,
                    **settings.fluorescence.apply_inverse.dict(),
                )

                # Save
                output_array[time_index, 0] = zyx_recon

    output_dataset.zattrs["settings"] = settings.dict()

    echo_headline(f"Closing {output_position_dirpath}\n")
    output_dataset.close()
    transfer_function_dataset.close()
    input_dataset.close()

    echo_headline(
        f"Recreate this reconstruction with:\n$ recorder apply-inv-tf {input_position_dirpath} {transfer_function_dirpath} -c {config_filepath} -o {output_position_dirpath}"
    )


@click.command()
@input_position_dirpaths()
@transfer_function_dirpath()
@config_filepath()
@output_dirpath()
def apply_inv_tf(
    input_position_dirpaths: List[str],
    transfer_function_dirpath: str,
    config_filepath: str,
    output_dirpath: str,
):
    """
    Apply an inverse transfer function to a dataset using a configuration file.

    See /examples for example configuration files.

    >> recorder apply-inv-tf -i ./input.zarr/*/*/* -t ./transfer-function.zarr -c /examples/birefringence.yml -o ./output.zarr
    """

    output_position_dirpaths = get_output_paths(
        input_position_dirpaths, output_dirpath
    )

    for input_position_dirpath, output_position_dirpath in zip(
        input_position_dirpaths, output_position_dirpaths
    ):
        apply_inverse_transfer_function_cli(
            input_position_dirpath,
            transfer_function_dirpath,
            config_filepath,
            output_position_dirpath,
        )
