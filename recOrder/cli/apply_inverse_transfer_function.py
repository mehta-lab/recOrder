import click
import numpy as np
import torch
import yaml
from iohub import open_ome_zarr
from recOrder.cli.printing import echo_headline, echo_settings
from recOrder.cli.settings import (
    TransferFunctionSettings,
    ApplyInverseSettings,
)
from recOrder.cli.parsing import (
    input_data_path_argument,
    config_path_option,
    output_dataset_options,
)
from recOrder.io import utils
from waveorder.models import (
    inplane_oriented_thick_pol3d,
    isotropic_thin_3d,
    phase_thick_3d,
)

# Imports for multiprocessing
import glob
import os
from natsort import natsorted
from typing import List, Union
from pathlib import Path
from functools import partial
import functools
import itertools
import pdb

# TODO: Change this to pytorch
import multiprocessing as mp


def get_output_paths(list_pos: List[str], output_path: Path) -> List[str]:
    """ "  Generates a mirrored output path list given an the input list of positions"""
    list_output_path = []
    for filepath in list_pos:
        path_strings = filepath.split(os.path.sep)[-3:]
        list_output_path.append(os.path.join(output_path, *path_strings))
    return list_output_path


def create_empty_zarr(
    input_data_path, transfer_function_path, config_path, output_data_path
):
    # Load datasets
    # Take position 0 as sample
    transfer_function_dataset = open_ome_zarr(transfer_function_path)
    input_dataset = open_ome_zarr(str(input_data_path[0]), mode="r")

    # Load transfer settings
    settings = TransferFunctionSettings(
        **transfer_function_dataset.zattrs["transfer_function_settings"]
    )

    # Load dataset shape and check for consistency
    _check_shape_consistency(
        settings, input_dataset.data.shape  # only loads a single position "0"
    )
    t_shape = input_dataset.data.shape[0]

    # Simplify important settings names
    recon_biref = settings.universal_settings.reconstruct_birefringence
    recon_phase = settings.universal_settings.reconstruct_phase
    recon_dim = settings.universal_settings.reconstruction_dimension

    # Prepare output dataset
    channel_names = []
    if recon_biref:
        channel_names.append("Retardance")
        channel_names.append("Orientation")
        channel_names.append("BF")
        channel_names.append("Pol")
        output_z_shape = input_dataset.data.shape[2]
    if recon_phase:
        if recon_dim == 2:
            channel_names.append("Phase2D")
            output_z_shape = 1
        elif recon_dim == 3:
            channel_names.append("Phase3D")
            output_z_shape = input_dataset.data.shape[2]

    # Output shape based on the type of reconstruction
    output_shape = (
        t_shape,
        len(channel_names),
        output_z_shape,
    ) + input_dataset.data.shape[3:]

    # Create output dataset
    output_dataset = open_ome_zarr(
        output_data_path, layout="hcs", mode="w", channel_names=channel_names
    )
    for filepath in input_data_path:
        path_strings = filepath.split(os.path.sep)[-3:]
        pos = output_dataset.create_position(
            str(path_strings[0]), str(path_strings[1]), str(path_strings[2])
        )
        _ = pos.create_zeros(
            name="0",
            shape=output_shape,
            dtype=np.float32,
            chunks=(
                1,
                1,
                1,
            )
            + input_dataset.data.shape[3:],  # chunk by YX
        )
    input_dataset.close()


# -------------------  PARALLELIZATION FUNCTIONS--------------------
def save_output(
    output_path, result, t_out=Ellipsis, c_out=Ellipsis, z_out=Ellipsis
):
    with open_ome_zarr(output_path) as out_array:
        out_array[0][t_out, c_out, z_out] = result


def apply_n_store(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Filter kwargs based on the function parameters
        params = func.__code__.co_varnames[: func.__code__.co_argcount]
        # Args corresponding to apply_inverse_funcs
        filtered_kwargs = {
            key: value
            for key, value in kwargs.items()
            if key in func.__code__.co_varnames
        }
        # Args corresponding to save to ome_zarr
        output_params = {
            key: value for key, value in kwargs.items() if key not in params
        }

        # Call the function with the filtered kwargs
        result = func(*args, **filtered_kwargs)

        # Save the result
        save_output(**output_params)

    return wrapper


def repeat_with_pool(num_cores, range_values):
    def decorator(func):
        def wrapper(*args, **kwargs):
            with mp.Pool(num_cores) as p:
                p.starmap(
                    partial(func, *args, **kwargs),
                    itertools.product(range_values),
                )
        return wrapper
    return decorator


# --------------SINGLE PROCESS FUNCTIONS-------------------


def bire_reconstruction(tczyx_data, output_data, recon_parameters, t):
    (
        intensity_to_stokes_matrix,
        wavelength,
        cyx_no_sample_data,
        project_stokes_to_2d,
        biref_inverse_dict,
        c_out,
        z_out,
    ) = recon_parameters

    click.echo(f"recon_params {recon_parameters}")
    click.echo(f"time {t}")
    reconstructed_parameters = (
        inplane_oriented_thick_pol3d.apply_inverse_transfer_function(
            tczyx_data[t],
            intensity_to_stokes_matrix,
            wavelength,
            cyx_no_sample_data,
            project_stokes_to_2d,
            **biref_inverse_dict,
        )
    )
    # click.echo(f'recon {reconstruction[0].shape}')
    with open_ome_zarr(output_data, mode="r+") as output_array:
        # Save
        for param_index, parameter in enumerate(reconstructed_parameters):
            click.echo(f"shape {parameter.numpy().shape}")
            output_array[0][t, param_index] = parameter.numpy()


def phase_reconstruction(tczyx_data, output_data, recon_parameters, t):
    (
        absorption_transfer_function,
        phase_transfer_function,
        settings,
    ) = recon_parameters
    _, yx_phase = isotropic_thin_3d.apply_inverse_transfer_function(
        tczyx_data[t, 0],
        absorption_transfer_function,
        phase_transfer_function,
        method=settings.reconstruction_algorithm,
        reg_p=settings.strength,
        rho=settings.TV_rho_strength,
        itr=settings.TV_iterations,
    )

    with open_ome_zarr(output_data, mode="r+") as output_array:
        # Save
        output_array[0][t, -1, 0] = yx_phase


# -------------- untouched functions from 0.4.0dev


def _check_shape_consistency(settings, data_shape):
    c_shape = data_shape[1]
    zyx_shape = data_shape[2:]

    # Check zyx dimensions for phase
    if settings.universal_settings.reconstruct_phase:
        if settings.phase_transfer_function_settings.zyx_shape != list(
            zyx_shape
        ):
            raise (
                ValueError(
                    f"Transfer function shape = {settings.phase_transfer_function_settings.zyx_shape} is not the same as the data shape = {zyx_shape}. Consider regenerating the transfer function."
                )
            )

    # Check c dimensions for birefringence
    if settings.universal_settings.reconstruct_birefringence:
        if (
            int(settings.birefringence_transfer_function_settings.scheme[0])
            != c_shape
        ):
            raise (
                ValueError(
                    f"scheme = {settings.birefringence_transfer_function_settings.scheme} is not the same as the data's channel shape = {c_shape}. Consider regenerating the transfer function or finding compatible data."
                )
            )


def _check_background_consistency(background_shape, data_shape):
    data_cyx_shape = (data_shape[1],) + data_shape[3:]
    if background_shape != data_cyx_shape:
        raise ValueError(
            f"Background shape {background_shape} does not match data shape {data_cyx_shape}"
        )


def apply_inverse_transfer_function_cli(
    input_data_path,
    transfer_function_path,
    config_path,
    output_path,
    num_cores,
):
    echo_headline("Starting reconstruction...")

    # Load datasets
    transfer_function_dataset = open_ome_zarr(transfer_function_path)
    input_dataset = open_ome_zarr(input_data_path)

    # Load config file
    if config_path is None:
        inverse_settings = ApplyInverseSettings()
    else:
        with open(config_path) as file:
            raw_settings = yaml.safe_load(file)
        inverse_settings = ApplyInverseSettings(**raw_settings)

    # Load transfer settings
    settings = TransferFunctionSettings(
        **transfer_function_dataset.zattrs["transfer_function_settings"]
    )

    # Load dataset shape and check for consistency
    _check_shape_consistency(
        settings, input_dataset.data.shape  # only loads a single position "0"
    )
    t_shape = input_dataset.data.shape[0]

    # Simplify important settings names
    recon_biref = settings.universal_settings.reconstruct_birefringence
    recon_phase = settings.universal_settings.reconstruct_phase
    recon_dim = settings.universal_settings.reconstruction_dimension
    wavelength = settings.universal_settings.wavelength_illumination

    # -----------------------------------------------------------------

    # Load data
    tczyx_data = torch.tensor(input_dataset[0], dtype=torch.float32)

    # Prepare background dataset
    if recon_biref:
        biref_inverse_dict = (
            inverse_settings.birefringence_apply_inverse_settings.dict()
        )

        # Resolve background path into array
        background_path = biref_inverse_dict["background_path"]
        biref_inverse_dict.pop("background_path")
        if background_path != "":
            cyx_no_sample_data = utils.new_load_background(background_path)
            _check_background_consistency(
                cyx_no_sample_data.shape, input_dataset.data.shape
            )
        else:
            cyx_no_sample_data = None

    # Main reconstruction logic
    # Six different cases [2, 3] x [biref only, phase only, both]

    # [biref only] [2 or 3]
    if recon_biref and (not recon_phase):
        echo_headline("Reconstructing birefringence with settings:")
        echo_settings(inverse_settings.birefringence_apply_inverse_settings)
        echo_headline("Reconstructing birefringence...")

        # Load transfer function
        intensity_to_stokes_matrix = torch.tensor(
            transfer_function_dataset["intensity_to_stokes_matrix"][0, 0, 0]
        )
        # Do the reconstruction
        recon_parameters = (
            intensity_to_stokes_matrix,
            wavelength,
            cyx_no_sample_data,
            False,
            biref_inverse_dict,
            slice(4),
            slice(None),
        )

        with mp.Pool(num_cores) as p:
            p.starmap(
                partial(
                    bire_reconstruction,
                    tczyx_data,
                    output_path,
                    recon_parameters,
                ),
                itertools.product(range(t_shape)),
            )

    # # [phase only]
    if recon_phase and (not recon_biref):
        echo_headline("Reconstructing phase with settings:")
        echo_settings(inverse_settings.phase_apply_inverse_settings)
        echo_headline("Reconstructing phase...")

        # check data shapes
        if input_dataset.data.shape[1] != 1:
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

            recon_parameters = (
                absorption_transfer_function,
                phase_transfer_function,
                inverse_settings.phase_apply_inverse_settings
            )        
            
            with mp.Pool(num_cores) as p:
                p.starmap(
                    partial(
                        phase_reconstruction,
                        tczyx_data,
                        output_path,
                        recon_parameters,
                    ),
                    itertools.product(range(t_shape)),
                )

    #     # [phase only, 3]
        # elif recon_dim == 3:
        #     # Load transfer functions
        #     real_potential_transfer_function = torch.tensor(
        #         transfer_function_dataset["real_potential_transfer_function"][
        #             0, 0
        #         ]
        #     )
        #     imaginary_potential_transfer_function = torch.tensor(
        #         transfer_function_dataset[
        #             "imaginary_potential_transfer_function"
        #         ][0, 0]
        #     )

    #         # Apply
    #         for time_index in range(t_shape):
    #             zyx_phase = phase_thick_3d.apply_inverse_transfer_function(
    #                 tczyx_data[time_index, 0],
    #                 real_potential_transfer_function,
    #                 imaginary_potential_transfer_function,
    #                 z_padding=settings.phase_transfer_function_settings.z_padding,
    #                 z_pixel_size=settings.phase_transfer_function_settings.z_pixel_size,
    #                 wavelength_illumination=wavelength,
    #                 method=inverse_settings.phase_apply_inverse_settings.reconstruction_algorithm,
    #                 reg_re=inverse_settings.phase_apply_inverse_settings.strength,
    #                 rho=inverse_settings.phase_apply_inverse_settings.TV_rho_strength,
    #                 itr=inverse_settings.phase_apply_inverse_settings.TV_iterations,
    #             )
    #             # Save
    #             output_array[time_index, -1] = zyx_phase

    # # [biref and phase]
    # if recon_biref and recon_phase:
    #     echo_headline("Reconstructing phase with settings:")
    #     echo_settings(inverse_settings.phase_apply_inverse_settings)
    #     echo_headline("Reconstructing birefringence with settings:")
    #     echo_settings(inverse_settings.birefringence_apply_inverse_settings)
    #     echo_headline("Reconstructing...")

    #     # Load birefringence transfer function
    #     intensity_to_stokes_matrix = torch.tensor(
    #         transfer_function_dataset["intensity_to_stokes_matrix"][0, 0, 0]
    #     )

    #     # [biref and phase, 2]
    #     if recon_dim == 2:
    #         # Load phase transfer functions
    #         absorption_transfer_function = torch.tensor(
    #             transfer_function_dataset["absorption_transfer_function"][0, 0]
    #         )
    #         phase_transfer_function = torch.tensor(
    #             transfer_function_dataset["phase_transfer_function"][0, 0]
    #         )

    #         for time_index in range(t_shape):
    #             # Apply
    #             reconstructed_parameters_2d = inplane_oriented_thick_pol3d.apply_inverse_transfer_function(
    #                 tczyx_data[time_index],
    #                 intensity_to_stokes_matrix,
    #                 wavelength,
    #                 cyx_no_sample_data,
    #                 project_stokes_to_2d=True,
    #                 **biref_inverse_dict,
    #             )

    #             reconstructed_parameters_3d = inplane_oriented_thick_pol3d.apply_inverse_transfer_function(
    #                 tczyx_data[time_index],
    #                 intensity_to_stokes_matrix,
    #                 wavelength,
    #                 cyx_no_sample_data,
    #                 project_stokes_to_2d=False,
    #                 **biref_inverse_dict,
    #             )

    #             brightfield_3d = reconstructed_parameters_3d[2]

    #             (
    #                 _,
    #                 yx_phase,
    #             ) = isotropic_thin_3d.apply_inverse_transfer_function(
    #                 brightfield_3d,
    #                 absorption_transfer_function,
    #                 phase_transfer_function,
    #                 method=inverse_settings.phase_apply_inverse_settings.reconstruction_algorithm,
    #                 reg_p=inverse_settings.phase_apply_inverse_settings.strength,
    #                 rho=inverse_settings.phase_apply_inverse_settings.TV_rho_strength,
    #                 itr=inverse_settings.phase_apply_inverse_settings.TV_iterations,
    #             )

    #             # Save
    #             for param_index, parameter in enumerate(
    #                 reconstructed_parameters_2d
    #             ):
    #                 output_array[time_index, param_index] = parameter
    #             output_array[time_index, -1, 0] = yx_phase

    #     # [biref and phase, 3]
    #     elif recon_dim == 3:
    #         # Load phase transfer functions
    #         intensity_to_stokes_matrix = torch.tensor(
    #             transfer_function_dataset["intensity_to_stokes_matrix"][
    #                 0, 0, 0
    #             ]
    #         )
    #         # Load transfer functions
    #         real_potential_transfer_function = torch.tensor(
    #             transfer_function_dataset["real_potential_transfer_function"][
    #                 0, 0
    #             ]
    #         )
    #         imaginary_potential_transfer_function = torch.tensor(
    #             transfer_function_dataset[
    #                 "imaginary_potential_transfer_function"
    #             ][0, 0]
    #         )

    #         # Apply
    #         for time_index in range(t_shape):
    #             reconstructed_parameters_3d = inplane_oriented_thick_pol3d.apply_inverse_transfer_function(
    #                 tczyx_data[time_index],
    #                 intensity_to_stokes_matrix,
    #                 wavelength,
    #                 cyx_no_sample_data,
    #                 project_stokes_to_2d=False,
    #                 **biref_inverse_dict,
    #             )

    #             brightfield_3d = reconstructed_parameters_3d[2]

    #             zyx_phase = phase_thick_3d.apply_inverse_transfer_function(
    #                 brightfield_3d,
    #                 real_potential_transfer_function,
    #                 imaginary_potential_transfer_function,
    #                 z_padding=settings.phase_transfer_function_settings.z_padding,
    #                 z_pixel_size=settings.phase_transfer_function_settings.z_pixel_size,
    #                 wavelength_illumination=wavelength,
    #                 method=inverse_settings.phase_apply_inverse_settings.reconstruction_algorithm,
    #                 reg_re=inverse_settings.phase_apply_inverse_settings.strength,
    #                 rho=inverse_settings.phase_apply_inverse_settings.TV_rho_strength,
    #                 itr=inverse_settings.phase_apply_inverse_settings.TV_iterations,
    #             )
    #             # Save
    #             for param_index, parameter in enumerate(
    #                 reconstructed_parameters_3d
    #             ):
    #                 output_array[time_index, param_index] = parameter
    #             output_array[time_index, -1] = zyx_phase

    output_dataset = open_ome_zarr(output_path, mode="r+")
    output_dataset.zattrs["transfer_function_settings"] = settings.dict()
    output_dataset.zattrs["apply_inverse_settings"] = inverse_settings.dict()

    echo_headline(f"Closing {output_path}\n")
    output_dataset.close()
    transfer_function_dataset.close()
    input_dataset.close()

    echo_headline(
        f"Recreate this reconstruction with:\n>> recorder apply-inverse-transfer-function {input_data_path} {transfer_function_path} -c {config_path} -o {output_path}"
    )


@click.command()
@input_data_path_argument()
@click.argument(
    "transfer_function_path",
    type=click.Path(exists=True),
)
@config_path_option()
@output_dataset_options(default="./reconstruction.zarr")
@click.option(
    "--num-cores",
    "-j",
    default=mp.cpu_count(),
    help="Number of cores",
    required=False,
    type=int,
)
def apply_inverse_transfer_function(
    input_data_path,
    transfer_function_path,
    config_path,
    output_path,
    num_cores,
):
    "Invert and apply a transfer function"

    # Sort the input as nargs=-1 will not be natsorted
    input_data_path = natsorted(input_data_path)
    # Handle single position or wildcard filepath
    list_output_pos = get_output_paths(input_data_path, output_path)
    click.echo(
        f"List of input pos:{input_data_path} output_pos:{list_output_pos}"
    )

    # Create a zarr store output to mirror the input
    create_empty_zarr(
        input_data_path, transfer_function_path, config_path, output_path
    )
    # Multiprocess per position
    for pos_in, pos_out in zip(input_data_path, list_output_pos):
        apply_inverse_transfer_function_cli(
            input_data_path=pos_in,
            transfer_function_path=transfer_function_path,
            config_path=config_path,
            output_path=pos_out,
            num_cores=num_cores,
        )


# recorder apply-inverse-transfer-function ./data_temp/20230426_211658_temp.zarr/0/0/0 ./230615_TF.zarr -c test_config.yaml -o ./test_delete.zarr
# recorder apply-inverse-transfer-function ./data_temp/20230426_211658_temp.zarr/*/*/* ./230615_TF_BIRE_ONLY.zarr -c ./test_config.yaml -o ./test_delete.zarr
