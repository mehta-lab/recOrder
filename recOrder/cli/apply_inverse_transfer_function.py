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
    inplane_anisotropic_thin_pol3d,
    isotropic_thin_3d,
    phase_thick_3d,
)

import glob
import os
import multiprocessing as mp
from tqdm import tqdm

# import torch.multiprocessing as mp


def parallel(func=None, **options):
    if func is None:
        return functools.partial(parallel, **options)

    def wrapper(*arguments):
        print(f'arguments {arguments}')
        pool = mp.Pool(mp.cpu_count())
        #Split the arguments
        position_paths = arguments[0]
        recon_params = arguments[1:]

        # Multiprocessing
        result = []
        for position in position_paths:
            print(f"filepath: {position}")
            args = (position,) + recon_params
            print(f'args: {args}')
            for results in tqdm(pool.starmap(func, [args])):
                result.append(results)
        pool.close()
        pool.join()
        return result

    return wrapper


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


def _parse_FOVs_per_filepath(input_data_path):
    # Parse the argument list and get parameterst to mirror the I/O file tree
    position_paths = []
    output_path_strings = []
    for path in input_data_path:
        for filepath in glob.glob(path):
            position_paths.append(filepath)
            path_strings = path.split(os.path.sep)[
                -3:
            ]  # get the last 4 path components
            output_path_strings.append(str(path_strings))
            print(f"output_path:{path_strings}")
    print("Reconstructing positions:")
    click.echo(f"{position_paths}\n")
    return position_paths


def apply_inverse_transfer_function_cli(
    input_data_path, transfer_function_path, config_path, output_path
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

    if recon_dim == 2:
        output_z_shape = 1
    elif recon_dim == 3:
        output_z_shape = input_dataset.data.shape[2]

    output_shape = (
        t_shape,
        len(channel_names),
        output_z_shape,
    ) + input_dataset.data.shape[3:]

    # Create output dataset
    output_dataset = open_ome_zarr(
        output_path, layout="fov", mode="w", channel_names=channel_names
    )
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
    )

    # Load data
    tczyx_data = torch.tensor(input_dataset.data, dtype=torch.float32)

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

        for time_index in range(t_shape):
            # Apply
            reconstructed_parameters = (
                inplane_anisotropic_thin_pol3d.apply_inverse_transfer_function(
                    tczyx_data[time_index],
                    intensity_to_stokes_matrix,
                    wavelength,
                    cyx_no_sample_data,
                    project_stokes_to_2d=False,
                    **biref_inverse_dict,
                )
            )
            # Save
            for param_index, parameter in enumerate(reconstructed_parameters):
                output_array[time_index, param_index] = parameter

    # [phase only]
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

            for time_index in range(t_shape):
                # Apply
                (
                    _,
                    yx_phase,
                ) = isotropic_thin_3d.apply_inverse_transfer_function(
                    tczyx_data[time_index, 0],
                    absorption_transfer_function,
                    phase_transfer_function,
                    method=inverse_settings.phase_apply_inverse_settings.reconstruction_algorithm,
                    reg_p=inverse_settings.phase_apply_inverse_settings.strength,
                    rho=inverse_settings.phase_apply_inverse_settings.TV_rho_strength,
                    itr=inverse_settings.phase_apply_inverse_settings.TV_iterations,
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
            for time_index in range(t_shape):
                zyx_phase = phase_thick_3d.apply_inverse_transfer_function(
                    tczyx_data[time_index, 0],
                    real_potential_transfer_function,
                    imaginary_potential_transfer_function,
                    z_padding=settings.phase_transfer_function_settings.z_padding,
                    z_pixel_size=settings.phase_transfer_function_settings.z_pixel_size,
                    illumination_wavelength=wavelength,
                    method=inverse_settings.phase_apply_inverse_settings.reconstruction_algorithm,
                    reg_re=inverse_settings.phase_apply_inverse_settings.strength,
                    rho=inverse_settings.phase_apply_inverse_settings.TV_rho_strength,
                    itr=inverse_settings.phase_apply_inverse_settings.TV_iterations,
                )
                # Save
                output_array[time_index, -1] = zyx_phase

    # [biref and phase]
    if recon_biref and recon_phase:
        echo_headline("Reconstructing phase with settings:")
        echo_settings(inverse_settings.phase_apply_inverse_settings)
        echo_headline("Reconstructing birefringence with settings:")
        echo_settings(inverse_settings.birefringence_apply_inverse_settings)
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

            for time_index in range(t_shape):
                # Apply
                reconstructed_parameters_2d = inplane_anisotropic_thin_pol3d.apply_inverse_transfer_function(
                    tczyx_data[time_index],
                    intensity_to_stokes_matrix,
                    wavelength,
                    cyx_no_sample_data,
                    project_stokes_to_2d=True,
                    **biref_inverse_dict,
                )

                reconstructed_parameters_3d = inplane_anisotropic_thin_pol3d.apply_inverse_transfer_function(
                    tczyx_data[time_index],
                    intensity_to_stokes_matrix,
                    wavelength,
                    cyx_no_sample_data,
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
                    method=inverse_settings.phase_apply_inverse_settings.reconstruction_algorithm,
                    reg_p=inverse_settings.phase_apply_inverse_settings.strength,
                    rho=inverse_settings.phase_apply_inverse_settings.TV_rho_strength,
                    itr=inverse_settings.phase_apply_inverse_settings.TV_iterations,
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
            for time_index in range(t_shape):
                reconstructed_parameters_3d = inplane_anisotropic_thin_pol3d.apply_inverse_transfer_function(
                    tczyx_data[time_index],
                    intensity_to_stokes_matrix,
                    wavelength,
                    cyx_no_sample_data,
                    project_stokes_to_2d=False,
                    **biref_inverse_dict,
                )

                brightfield_3d = reconstructed_parameters_3d[2]

                zyx_phase = phase_thick_3d.apply_inverse_transfer_function(
                    brightfield_3d,
                    real_potential_transfer_function,
                    imaginary_potential_transfer_function,
                    z_padding=settings.phase_transfer_function_settings.z_padding,
                    z_pixel_size=settings.phase_transfer_function_settings.z_pixel_size,
                    illumination_wavelength=wavelength,
                    method=inverse_settings.phase_apply_inverse_settings.reconstruction_algorithm,
                    reg_re=inverse_settings.phase_apply_inverse_settings.strength,
                    rho=inverse_settings.phase_apply_inverse_settings.TV_rho_strength,
                    itr=inverse_settings.phase_apply_inverse_settings.TV_iterations,
                )
                # Save
                for param_index, parameter in enumerate(
                    reconstructed_parameters_3d
                ):
                    output_array[time_index, param_index] = parameter
                output_array[time_index, -1] = zyx_phase

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
def apply_inverse_transfer_function(
    input_data_path, transfer_function_path, config_path, output_path
):
    # Handle single position or wildcard filepath
    list_pos = _parse_FOVs_per_filepath(input_data_path)
    parameters = (list_pos, transfer_function_path, config_path, output_path)
    "Invert and apply a transfer function"
    # Paralellize the function
    mp_inverse_transfer_function = parallel(
        apply_inverse_transfer_function_cli
    )
    mp_inverse_transfer_function(*parameters)


# recorder apply-inverse-transfer-function ./data_temp/2022_08_04_recOrder_pytest_20x_04NA_zarr/2T_3P_16Z_128Y_256X_Kazansky.zarr/*/*/* ../test_transfer_function.zarr -o ../test_delete2.zarr

# recorder apply-inverse-transfer-function ./data_temp/2022_08_04_recOrder_pytest_20x_04NA/2T_3P_16Z_128Y_256X_Kazansky_1.zarr/*/*/* ./TF.zarr -c test_config.yaml
