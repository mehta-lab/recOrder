import click
import numpy as np
import torch
import yaml
from iohub import open_ome_zarr
from recOrder.cli.printing import echo_headline, echo_settings
import torch.multiprocessing as mp
import glob
from tqdm import tqdm
import os

from recOrder.cli.settings import (
    TransferFunctionSettings,
    ApplyInverseSettings,
)
from recOrder.cli.parsing import (
    input_data_path_argument,
    config_path_option,
    output_dataset_options,
    cores_option,
)
from recOrder.io import utils
from waveorder.models import (
    inplane_anisotropic_thin_pol3d,
    isotropic_thin_3d,
    phase_thick_3d,
)

MULTIPROCESSING_FLAG = True


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


def multiprocess_position(args):
    (
        mp_flag,
        position,
        time_index,
        input_dataset,
        output_path,
        transfer_function_dataset,
        reconstructor_params,
    ) = args
    t, c, z, y, x = input_dataset.data.shape
    # Load the time
    tczyx_data = torch.tensor(
        input_dataset.data[time_index].astype(np.float32), dtype=torch.float32
    )

    if mp_flag == 1:  # Unpack the reconstructor specific parameters
        (
            wavelength,
            cyx_no_sample_data,
            biref_inverse_dict,
        ) = reconstructor_params

        # Load transfer function
        intensity_to_stokes_matrix = torch.tensor(
            transfer_function_dataset["intensity_to_stokes_matrix"][0, 0, 0]
        )
        output = (
            inplane_anisotropic_thin_pol3d.apply_inverse_transfer_function(
                tczyx_data,
                intensity_to_stokes_matrix,
                wavelength,
                cyx_no_sample_data,
                project_stokes_to_2d=False,
                **biref_inverse_dict,
            )
        )
        # Save
        with open_ome_zarr(output_path, mode="r+") as output_array:
            input
            # TODO: add position string if we will loop for positions.
            for parameter_idx, parameter in enumerate(output):
                output_array[0][time_index, parameter_idx] = parameter.numpy()

    elif mp_flag == 2:
        # Unpack parameters
        inverse_settings = reconstructor_params
        # Load transfer functions
        absorption_transfer_function = torch.tensor(
            transfer_function_dataset["absorption_transfer_function"][0, 0]
        )
        phase_transfer_function = torch.tensor(
            transfer_function_dataset["phase_transfer_function"][0, 0]
        )
        _, output = isotropic_thin_3d.apply_inverse_transfer_function(
            tczyx_data[0],
            absorption_transfer_function,
            phase_transfer_function,
            method=inverse_settings.phase_apply_inverse_settings.reconstruction_algorithm,
            reg_p=inverse_settings.phase_apply_inverse_settings.strength,
            rho=inverse_settings.phase_apply_inverse_settings.TV_rho_strength,
            itr=inverse_settings.phase_apply_inverse_settings.TV_iterations,
        )
        with open_ome_zarr(output_path, mode="r+") as output_array:
            output_array[0][time_index, -1, 0] = output.numpy()

    elif mp_flag == 3:
        # Phase reconstruction parameters
        wavelength, settings, inverse_settings = reconstructor_params
        # Load the tensors
        real_potential_transfer_function = torch.tensor(
            transfer_function_dataset["real_potential_transfer_function"][0, 0]
        )
        imaginary_potential_transfer_function = torch.tensor(
            transfer_function_dataset["imaginary_potential_transfer_function"][
                0, 0
            ]
        )
        output = phase_thick_3d.apply_inverse_transfer_function(
            tczyx_data[0],
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
        with open_ome_zarr(output_path, mode="r+") as output_array:
            output_array[0][time_index, -1] = output.numpy()

    elif mp_flag == 4:
        (
            wavelength,
            cyx_no_sample_data,
            biref_inverse_dict,
            inverse_settings,
        ) = reconstructor_params

        # Load phase transfer functions
        absorption_transfer_function = torch.tensor(
            transfer_function_dataset["absorption_transfer_function"][0, 0]
        )
        phase_transfer_function = torch.tensor(
            transfer_function_dataset["phase_transfer_function"][0, 0]
        )
        intensity_to_stokes_matrix = torch.tensor(
            transfer_function_dataset["intensity_to_stokes_matrix"][0, 0, 0]
        )

        # Apply
        reconstructed_parameters_2d = (
            inplane_anisotropic_thin_pol3d.apply_inverse_transfer_function(
                tczyx_data,
                intensity_to_stokes_matrix,
                wavelength,
                cyx_no_sample_data,
                project_stokes_to_2d=True,
                **biref_inverse_dict,
            )
        )

        reconstructed_parameters_3d = (
            inplane_anisotropic_thin_pol3d.apply_inverse_transfer_function(
                tczyx_data,
                intensity_to_stokes_matrix,
                wavelength,
                cyx_no_sample_data,
                project_stokes_to_2d=False,
                **biref_inverse_dict,
            )
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
        with open_ome_zarr(output_path, mode="r+") as output_array:
            for parameter_idx, parameter in enumerate(
                reconstructed_parameters_2d
            ):
                output_array[0][time_index, parameter_idx] = parameter.numpy()
            output_array[0][time_index, -1, 0] = yx_phase.numpy()

    elif mp_flag == 5:
        (
            wavelength,
            cyx_no_sample_data,
            biref_inverse_dict,
            inverse_settings,
            settings,
        ) = reconstructor_params

        # Load phase transfer functions
        intensity_to_stokes_matrix = torch.tensor(
            transfer_function_dataset["intensity_to_stokes_matrix"][0, 0, 0]
        )
        # Load transfer functions
        real_potential_transfer_function = torch.tensor(
            transfer_function_dataset["real_potential_transfer_function"][0, 0]
        )
        imaginary_potential_transfer_function = torch.tensor(
            transfer_function_dataset["imaginary_potential_transfer_function"][
                0, 0
            ]
        )

        reconstructed_parameters_3d = (
            inplane_anisotropic_thin_pol3d.apply_inverse_transfer_function(
                tczyx_data,
                intensity_to_stokes_matrix,
                wavelength,
                cyx_no_sample_data,
                project_stokes_to_2d=False,
                **biref_inverse_dict,
            )
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

        with open_ome_zarr(output_path, mode="r+") as output_array:
            for parameter_idx, parameter in enumerate(
                reconstructed_parameters_3d
            ):
                output_array[0][time_index, parameter_idx] = parameter.numpy()
            output_array[0][time_index, -1] = zyx_phase.numpy()


def apply_inverse_transfer_function_cli(
    input_data_path,
    transfer_function_path,
    config_path,
    output_path,
    num_cores,
):
    echo_headline("Starting reconstruction...")
    # Parse the argument list and get parameterst to mirror the I/O file tree
    position_paths = []
    output_path_strings = []
    for path in input_data_path:
        for filepath in glob.glob(path):
            position_paths.append(filepath)
            path_strings = path.split(os.path.sep)[
                -3:
            ]  # get the last 4 path components
            output_path_strings.append(path_strings)
    echo_headline("Reconstructing positions:")
    click.echo(f"{position_paths}\n")

    # Load datasets
    # Take position 0 as sample
    transfer_function_dataset = open_ome_zarr(transfer_function_path)
    input_dataset = open_ome_zarr(position_paths[0])

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
        output_path, layout="hcs", mode="w", channel_names=channel_names
    )
    for plate, row, column in output_path_strings:
        pos = output_dataset.create_position(str(plate), str(row), str(column))
        output_array = pos.create_zeros(
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

    # -----------------------------------------------------------------
    # Set-up the multiprocessing queue
    multiprocessing_queue = []
    for position in range(len(position_paths)):
        # Input and output paths
        input_dataset = open_ome_zarr(position_paths[position])
        output_pos_path = os.path.join(
            output_path,
            str(output_path_strings[position][0]),
            str(output_path_strings[position][1]),
            str(output_path_strings[position][2]),
        )
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
            _mp_flag = 1
            echo_headline("Reconstructing birefringence with settings:")
            echo_settings(
                inverse_settings.birefringence_apply_inverse_settings
            )
            echo_headline("Reconstructing birefringence...")

            _bire_MP_params = []
            # TODO We could also iterate through Z... ?
            for time_index in range(t_shape):
                _bire_MP_params = [
                    _mp_flag,
                    position,
                    time_index,
                    input_dataset,
                    output_pos_path,
                    transfer_function_dataset,
                    (wavelength, cyx_no_sample_data, biref_inverse_dict),
                ]
                # Add to the the multiprocessing queue list
                multiprocessing_queue.append(_bire_MP_params)

        # [phase only]
        if recon_phase and (not recon_biref):
            _phase_MP_params = []
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
                _mp_flag = 2
                for time_index in range(t_shape):
                    _phase_MP_params = [
                        _mp_flag,
                        position,
                        time_index,
                        input_dataset,
                        output_pos_path,
                        transfer_function_dataset,
                        (inverse_settings),
                    ]
                    # Add to the the multiprocessing queue list
                    multiprocessing_queue.append(_phase_MP_params)

            # [phase only, 3]
            elif recon_dim == 3:
                _mp_flag = 3
                # Apply
                for time_index in range(t_shape):
                    _phase_MP_params = [
                        _mp_flag,
                        position,
                        time_index,
                        input_dataset,
                        output_pos_path,
                        transfer_function_dataset,
                        (wavelength, settings, inverse_settings),
                    ]
                    # Add to the the multiprocessing queue list
                    multiprocessing_queue.append(_phase_MP_params)

        # # [biref and phase]
        if recon_biref and recon_phase:
            _phase_MP_params = []

            echo_headline("Reconstructing phase with settings:")
            echo_settings(inverse_settings.phase_apply_inverse_settings)
            echo_headline("Reconstructing birefringence with settings:")
            echo_settings(
                inverse_settings.birefringence_apply_inverse_settings
            )
            echo_headline("Reconstructing...")

            # Load birefringence transfer function
            intensity_to_stokes_matrix = torch.tensor(
                transfer_function_dataset["intensity_to_stokes_matrix"][
                    0, 0, 0
                ]
            )

            # [biref and phase, 2]
            if recon_dim == 2:
                _mp_flag = 4

                for time_index in range(t_shape):
                    _phase_MP_params = [
                        _mp_flag,
                        position,
                        time_index,
                        input_dataset,
                        output_pos_path,
                        transfer_function_dataset,
                        (
                            wavelength,
                            cyx_no_sample_data,
                            biref_inverse_dict,
                            inverse_settings,
                        ),
                    ]
                    multiprocessing_queue.append(_phase_MP_params)

            # [biref and phase, 3]
            elif recon_dim == 3:
                _mp_flag = 5

                # Apply
                for time_index in range(t_shape):
                    _phase_MP_params = [
                        _mp_flag,
                        position,
                        time_index,
                        input_dataset,
                        output_pos_path,
                        transfer_function_dataset,
                        (
                            wavelength,
                            cyx_no_sample_data,
                            biref_inverse_dict,
                            inverse_settings,
                            settings,
                        ),
                    ]
                    multiprocessing_queue.append(_phase_MP_params)

    output_dataset.zattrs["transfer_function_settings"] = settings.dict()
    output_dataset.zattrs["apply_inverse_settings"] = inverse_settings.dict()

    ## Multiprocessing
    pool = mp.Pool(num_cores)
    echo_headline(f"Processing with < {num_cores} > cores\n")
    results = []
    for result in tqdm(
        pool.imap(multiprocess_position, multiprocessing_queue),
        total=len(multiprocessing_queue),
    ):
        results.append(result)
    pool.close()
    pool.join()

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
@cores_option(default=mp.cpu_count())
def apply_inverse_transfer_function(
    input_data_path,
    transfer_function_path,
    config_path,
    output_path,
    num_cores,
):
    "Invert and apply a transfer function"
    apply_inverse_transfer_function_cli(
        input_data_path,
        transfer_function_path,
        config_path,
        output_path,
        num_cores,
    )
