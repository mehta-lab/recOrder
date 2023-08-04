import click
import numpy as np
import torch
from typing import List
from iohub.ngff import open_ome_zarr, Position
from recOrder.cli.printing import echo_headline, echo_settings
from recOrder.cli.settings import ReconstructionSettings
from recOrder.cli.parsing import (
    input_data_path_argument,
    config_path_option,
    output_dataset_option,
    processes_option,
)
from recOrder.io import utils
from waveorder.models import (
    inplane_oriented_thick_pol3d,
    isotropic_thin_3d,
    phase_thick_3d,
    # isotropic_fluorescent_thick_3d,
)
import torch.multiprocessing as mp
from recOrder.cli import mp_utils
from pathlib import Path
import io
import contextlib
import inspect
from natsort import natsorted
from functools import partial
import itertools

# TODO: change the default from mp.count() to a variable that can be spit out by slurm


def _check_background_consistency(background_shape, data_shape):
    data_cyx_shape = (data_shape[1],) + data_shape[3:]
    if background_shape != data_cyx_shape:
        raise ValueError(
            f"Background shape {background_shape} does not match data shape {data_cyx_shape}"
        )


def apply_inverse_biref_phase_3D(czyx, birefringence_args, phase3D_args):
    reconstruction_birefringence_zyx = (
        inplane_oriented_thick_pol3d.apply_inverse_transfer_function(
            czyx, **birefringence_args
        )
    )

    brightfield_3d = reconstruction_birefringence_zyx[2]

    reconstruction_phase_zyx = phase_thick_3d.apply_inverse_transfer_function(
        brightfield_3d, **phase3D_args
    )

    reconstruction_bire_phase_3D_zyx = reconstruction_birefringence_zyx + (
        reconstruction_phase_zyx,
    )

    return reconstruction_bire_phase_3D_zyx


def apply_reconstruction_to_zyx_and_save(
    func,
    position: Position,
    output_path: Path,
    settings: ReconstructionSettings,
    c_idx: int = 4,
    c_start: int = None,
    c_end: int = None,
    t_idx: int = 0,
    **kwargs,
) -> None:
    """Load a zyx array from a Position object, apply a transformation and save the result to file"""
    click.echo(f"Reconstructing t={t_idx}")

    # Initialize torch module in each worker process
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.manual_seed(0)

    # Find channel indices
    channel_indices = []
    for input_channel_name in settings.input_channel_names:
        channel_indices.append(
            position.channel_names.index(input_channel_name)
        )
    print(f"channel_indeces {channel_indices}")
    # Load data
    # tczyx_uint16_numpy = position.data.oindex[:, channel_indices]
    # tczyx_data = torch.tensor(
    #     np.int32(tczyx_uint16_numpy), dtype=torch.float32
    # )  # convert to np.int32 (torch doesn't accept np.uint16), then convert to tensor float32
    c_slice = slice(None) if c_idx == 4 else 0
    czyx_data = torch.tensor(position[0][t_idx, c_slice], dtype=torch.float32)

    # Apply transformation
    click.echo("Applying inv transform...")
    reconstruction_zyx = func(czyx_data, **kwargs)
    click.echo("Done inv transform...")

    reconstruction_array = np.array(
        [tensor.numpy() for tensor in reconstruction_zyx]
    )
    if reconstruction_array.ndim == 3:
        reconstruction_array = np.expand_dims(reconstruction_array, axis=0)

    print(f"recon shape {reconstruction_array.shape}")
    # Write to file
    # for c, recon_zyx in enumerate(reconstruction_zyx):
    with open_ome_zarr(output_path, mode="r+") as output_dataset:
        output_dataset[0][t_idx, slice(c_start, c_end)] = reconstruction_array
    click.echo(f"Finished Writing.. t={t_idx}")


def process_single_position(
    func,
    input_data_path: Path,
    output_path: Path,
    num_processes: int = mp.cpu_count(),
    **kwargs,
) -> None:
    """Register a single position with multiprocessing parallelization over T and C"""
    # Function to be applied
    click.echo(f"Function to be applied: \t{func}")

    # Get the reader and writer
    click.echo(f"Input data path:\t{input_data_path}")
    click.echo(f"Output data path:\t{output_path}")
    input_dataset = open_ome_zarr(input_data_path)
    stdout_buffer = io.StringIO()
    with contextlib.redirect_stdout(stdout_buffer):
        input_dataset.print_tree()
    click.echo(f" Zarr Store info: {stdout_buffer.getvalue()}")

    T, _, _, _, _ = input_dataset.data.shape
    click.echo(f"Input dataset shape:\t{input_dataset.data.shape}")

    # Check the arguments for the function
    all_func_params = inspect.signature(func).parameters.keys()
    # Extract the relevant kwargs for the function 'func'
    func_args = {}
    non_func_args = {}

    for k, v in kwargs.items():
        if k in all_func_params:
            func_args[k] = v
        else:
            non_func_args[k] = v

    # Write the settings into the metadata if existing
    # TODO: alternatively we can throw all extra arguments as metadata.
    if "extra_metadata" in non_func_args:
        # For each dictionary in the nest
        with open_ome_zarr(output_path, mode="r+") as output_dataset:
            for params_metadata_keys in kwargs["extra_metadata"].keys():
                output_dataset.zattrs["extra_metadata"] = non_func_args[
                    "extra_metadata"
                ]
    # TODO: check if this is right implemented
    print("Saving settings to zattrs")
    with open_ome_zarr(output_path, mode="r+") as output_dataset:
        output_dataset.zattrs["settings"] = kwargs["settings"].dict()
    # Parse some settings from kwargs used in apply_reconstruction_to_zyx_and_save
    settings = kwargs["settings"]
    c_idx = kwargs.get("c_idx", 4)
    c_start = kwargs.get("c_start", None)
    c_end = kwargs.get("c_end", None)
    # Check if the following

    # Loop through (T, C), deskewing and writing as we go
    click.echo(f"\nStarting multiprocess pool with {num_processes} processes")
    with mp.Pool(num_processes) as p:
        p.starmap(
            partial(
                apply_reconstruction_to_zyx_and_save,
                func,
                input_dataset,
                output_path,
                settings,
                c_idx,
                c_start,
                c_end,
                **func_args,
            ),
            itertools.product(range(T)),
        )


def apply_inverse_transfer_function_cli(
    input_paths: List[Path],
    transfer_function_path: Path,
    config_path: Path,
    output_path: Path = "./reconstructed.zarr",
    num_processes: int = 1,
):
    # TODO: Since this is called without the natsort
    input_paths = [Path(path) for path in natsorted(input_paths)]

    # Handle single position or wildcard filepath
    output_paths = mp_utils.get_output_paths(input_paths, output_path)
    click.echo(f"List of input_pos:{input_paths} output_pos:{output_paths}")

    # Get the reconstruction output shapes, chunk shape and voxel size
    channel_names, output_zyx_shape = mp_utils.get_reconstruction_data_shape(
        input_paths, config_path
    )

    # TODO: should this be passed here?
    voxel_size = (1, 1, 1)
    # TODO:determine if this is a good chunk size?
    chunk_zyx_shape = (
        output_zyx_shape[0] // 10,
        output_zyx_shape[1],
        output_zyx_shape[2],
    )

    # Create a zarr store output to mirror the input
    mp_utils.create_empty_zarr(
        input_paths,
        output_path,
        output_zyx_shape=output_zyx_shape,
        chunk_zyx_shape=chunk_zyx_shape,
        voxel_size=voxel_size,
        channel_names=channel_names,
    )

    echo_headline("Starting reconstruction...")
    # Actual multiprocessing part
    for input_position_path, output_position_path in zip(
        input_paths, output_paths
    ):
        # Load datasets
        transfer_function_dataset = open_ome_zarr(transfer_function_path)
        input_dataset = open_ome_zarr(input_position_path)

        # Load config file
        settings = utils.yaml_to_model(config_path, ReconstructionSettings)

        # Check input channel names
        if not set(settings.input_channel_names).issubset(
            input_dataset.channel_names
        ):
            raise ValueError(
                f"Each of the input_channel_names = {settings.input_channel_names} in {config_path} must appear in the dataset {input_data_path} which currently contains channel_names = {input_dataset.channel_names}."
            )

        # Simplify important settings names
        recon_biref = settings.birefringence is not None
        recon_phase = settings.phase is not None
        recon_dim = settings.reconstruction_dimension

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
                transfer_function_dataset["intensity_to_stokes_matrix"][
                    0, 0, 0
                ]
            )
            apply_inverse_tf_func = (
                inplane_oriented_thick_pol3d.apply_inverse_transfer_function
            )
            reconstructor_args = {
                "intensity_to_stokes_matrix": intensity_to_stokes_matrix,
                "cyx_no_sample_data": cyx_no_sample_data,
                "project_stokes_to_2d": (recon_dim == 2),
                "c_end": 4,
                "settings": settings,
                **biref_inverse_dict,
            }

        # # [phase only]
        if recon_phase and (not recon_biref):
            echo_headline("Reconstructing phase with settings:")
            echo_settings(settings.phase.apply_inverse)
            echo_headline("Reconstructing phase...")

            # check data shapes
            if input_dataset.data.shape[1] != 1:
                raise ValueError(
                    "You have requested a phase-only reconstruction, but the input dataset has more than one channel."
                )

            # [phase only, 2]
            if recon_dim == 2:
                # Select transfer function
                apply_inverse_tf_func = (
                    isotropic_thin_3d.apply_inverse_transfer_function
                )
                # Load transfer functions
                absorption_transfer_function = torch.tensor(
                    transfer_function_dataset["absorption_transfer_function"][
                        0, 0
                    ]
                )
                phase_transfer_function = torch.tensor(
                    transfer_function_dataset["phase_transfer_function"][0, 0]
                )
                reconstructor_args = {
                    "c_idx": 0,
                    "c_start": -1,
                    "absorption_transfer_function": absorption_transfer_function,
                    "phase_transfer_function": phase_transfer_function,
                    "settings": settings,
                    **settings.phase.apply_inverse.dict(),
                }

            # [phase only, 3]
            elif recon_dim == 3:
                # Select transfer function
                apply_inverse_tf_func = (
                    phase_thick_3d.apply_inverse_transfer_function
                )

                # Load transfer functions
                real_potential_transfer_function = torch.tensor(
                    transfer_function_dataset[
                        "real_potential_transfer_function"
                    ][0, 0]
                )
                imaginary_potential_transfer_function = torch.tensor(
                    transfer_function_dataset[
                        "imaginary_potential_transfer_function"
                    ][0, 0]
                )

                reconstructor_args = {
                    "real_potential_transfer_function": real_potential_transfer_function,
                    "imaginary_potential_transfer_function": imaginary_potential_transfer_function,
                    "z_padding": settings.phase.transfer_function.z_padding,
                    "z_pixel_size": settings.phase.transfer_function.z_pixel_size,
                    "wavelength_illumination": settings.phase.transfer_function.wavelength_illumination,
                    "c_start": -1,
                    "c_idx": 0,
                    "settings": settings,
                    **settings.phase.apply_inverse.dict(),
                }

        # # [biref and phase]
        if recon_biref and recon_phase:
            #     echo_headline("Reconstructing phase with settings:")
            #     echo_settings(settings.phase.apply_inverse)
            #     echo_headline("Reconstructing birefringence with settings:")
            #     echo_settings(settings.birefringence.apply_inverse)
            #     echo_headline("Reconstructing...")

            #     # Load birefringence transfer function
            #     intensity_to_stokes_matrix = torch.tensor(
            #         transfer_function_dataset["intensity_to_stokes_matrix"][0, 0, 0]
            #     )

            # [biref and phase, 2]
            if recon_dim == 2:
                # Load phase transfer functions
                absorption_transfer_function = torch.tensor(
                    transfer_function_dataset["absorption_transfer_function"][
                        0, 0
                    ]
                )
                phase_transfer_function = torch.tensor(
                    transfer_function_dataset["phase_transfer_function"][0, 0]
                )

            #         for time_index in range(t_shape):
            #             # Apply
            #             reconstructed_parameters_2d = inplane_oriented_thick_pol3d.apply_inverse_transfer_function(
            #                 tczyx_data[time_index],
            #                 intensity_to_stokes_matrix,
            #                 cyx_no_sample_data=cyx_no_sample_data,
            #                 project_stokes_to_2d=True,
            #                 **biref_inverse_dict,
            #             )

            #             reconstructed_parameters_3d = inplane_oriented_thick_pol3d.apply_inverse_transfer_function(
            #                 tczyx_data[time_index],
            #                 intensity_to_stokes_matrix,
            #                 cyx_no_sample_data=cyx_no_sample_data,
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
            #                 **settings.phase.apply_inverse.dict(),
            #             )

            #             # Save
            #             for param_index, parameter in enumerate(
            #                 reconstructed_parameters_2d
            #             ):
            #                 output_array[time_index, param_index] = parameter
            #             output_array[time_index, -1, 0] = yx_phase

            # [biref and phase, 3]
            elif recon_dim == 3:
                apply_inverse_tf_func = apply_inverse_biref_phase_3D
                # Load phase transfer functions
                intensity_to_stokes_matrix = torch.tensor(
                    transfer_function_dataset["intensity_to_stokes_matrix"][
                        0, 0, 0
                    ]
                )
                # Load transfer functions
                real_potential_transfer_function = torch.tensor(
                    transfer_function_dataset[
                        "real_potential_transfer_function"
                    ][0, 0]
                )
                imaginary_potential_transfer_function = torch.tensor(
                    transfer_function_dataset[
                        "imaginary_potential_transfer_function"
                    ][0, 0]
                )

                birefringence_args = {
                    "intensity_to_stokes_matrix": intensity_to_stokes_matrix,
                    "cyx_no_sample_data": cyx_no_sample_data,
                    "project_stokes_to_2d": (recon_dim == 2),
                    **biref_inverse_dict,
                }

                phase3D_args = {
                    "real_potential_transfer_function": real_potential_transfer_function,
                    "imaginary_potential_transfer_function": imaginary_potential_transfer_function,
                    "z_padding": settings.phase.transfer_function.z_padding,
                    "z_pixel_size": settings.phase.transfer_function.z_pixel_size,
                    "wavelength_illumination": settings.phase.transfer_function.wavelength_illumination,
                    **settings.phase.apply_inverse.dict(),
                }

                reconstructor_args = {
                    "birefringence_args": birefringence_args,
                    "phase3D_args": phase3D_args,
                    "c_end": 5,
                    "settings": settings,
                }

        # # [fluo]
        # if recon_fluo:
        #     echo_headline("Reconstructing fluorescence with settings:")
        #     echo_settings(settings.fluorescence.apply_inverse)
        #     echo_headline("Reconstructing...")

        #     # [fluo, 2]
        #     if recon_dim == 2:
        #         raise NotImplementedError
        #     # [fluo, 3]
        #     elif recon_dim == 3:
        #         # Load transfer functions
        #         optical_transfer_function = torch.tensor(
        #             transfer_function_dataset["optical_transfer_function"][0, 0]
        #         )

        #         # Apply
        #         for time_index in range(t_shape):
        #             zyx_recon = isotropic_fluorescent_thick_3d.apply_inverse_transfer_function(
        #                 tczyx_data[time_index, 0],
        #                 optical_transfer_function,
        #                 settings.fluorescence.transfer_function.z_padding,
        #                 **settings.fluorescence.apply_inverse.dict(),
        #             )

        #             # Save
        #             output_array[time_index, 0] = zyx_recon

        process_single_position(
            apply_inverse_tf_func,
            input_data_path=input_position_path,
            output_path=output_position_path,
            num_processes=num_processes,
            **reconstructor_args,
        )

    # echo_headline(f"Closing {output_path}\n")
    # output_dataset.close()
    transfer_function_dataset.close()
    input_dataset.close()

    echo_headline(
        f"Recreate this reconstruction with:\n$ recorder apply-inv-tf {input_paths[0]} {transfer_function_path} -c {config_path} -o {output_path}"
    )


@click.command()
@click.help_option("-h", "--help")
@input_data_path_argument()
@click.argument(
    "transfer_function_path",
    type=click.Path(exists=True),
)
@config_path_option()
@output_dataset_option(default="./reconstruction.zarr")
@processes_option(default=mp.cpu_count())
def apply_inv_tf(
    input_data_path: List[Path],
    transfer_function_path: Path,
    config_path: Path,
    output_path: Path,
    num_processes: int,
):
    """
    Apply an inverse transfer function to a dataset using a configuration file.

    See /examples for example configuration files.

    Example usage:\n
    $ recorder apply-inv-tf input.zarr/0/0/0 transfer-function.zarr -c /examples/birefringence.yml -o output.zarr
    """
    apply_inverse_transfer_function_cli(
        input_paths=input_data_path,
        transfer_function_path=transfer_function_path,
        config_path=config_path,
        output_path=output_path,
        num_processes=num_processes,
    )


if __name__ == "__main__":
    import os

    print(os.getcwd())
    os.chdir("/home/eduardo.hirata/repos/recOrder/recOrder/tests/cli_tests")
    print(os.getcwd())
    apply_inv_tf(
        [
            "/home/eduardo.hirata/repos/recOrder/recOrder/tests/cli_tests/data_temp/2022_08_04_recOrder_pytest_20x_04NA.zarr/0/0/0",
            "./bire_phase_TF.zarr",
            "-c",
            "./birefringence-and-phase.yml",
            "-o",
            "./bire_phase_3D.zarr",
        ]
    )
