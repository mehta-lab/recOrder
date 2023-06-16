import click
import numpy as np
from iohub import open_ome_zarr
from recOrder.cli.printing import echo_settings, echo_headline
from recOrder.cli.settings import ReconstructionSettings
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
    isotropic_fluorescent_thick_3d,
)


def compute_transfer_function_cli(input_data_path, config_path, output_path):
    # Load config file
    if config_path is None:
        settings = ReconstructionSettings()
    else:
        settings = utils.yaml_to_model(config_path, ReconstructionSettings)

    echo_headline(
        f"Generating transfer functions and storing in {output_path}\n"
    )

    # Read shape from input dataset
    input_dataset = open_ome_zarr(input_data_path, layout="fov", mode="r")
    (
        _,
        _,
        z_shape,
        y_shape,
        x_shape,
    ) = input_dataset.data.shape  # only loads a single position "0"

    # Prepare output dataset
    output_dataset = open_ome_zarr(
        output_path, layout="fov", mode="w", channel_names=["None"]
    )

    # Pass settings to appropriate calculate_transfer_function and save
    if settings.birefringence is not None:
        echo_headline(
            "Generating birefringence transfer function with settings:"
        )
        echo_settings(settings.birefringence.transfer_function)

        # Calculate transfer functions
        intensity_to_stokes_matrix = (
            inplane_oriented_thick_pol3d.calculate_transfer_function(
                **settings.birefringence.transfer_function.dict()
            )
        )
        # Save
        output_dataset[
            "intensity_to_stokes_matrix"
        ] = intensity_to_stokes_matrix.cpu().numpy()[None, None, None, ...]

    if settings.phase is not None:
        echo_headline("Generating phase transfer function with settings:")
        echo_settings(settings.phase.transfer_function)

        if settings.reconstruction_dimension == 2:
            # Convert zyx_shape and z_pixel_size into yx_shape and z_position_list
            settings_dict = settings.phase.transfer_function.dict()
            settings_dict["yx_shape"] = [y_shape, x_shape]
            settings_dict["z_position_list"] = list(
                -(np.arange(z_shape) - z_shape // 2)
                * settings_dict["z_pixel_size"]
            )

            # Remove unused parameters
            settings_dict.pop("z_pixel_size")
            settings_dict.pop("z_padding")

            # Calculate transfer functions
            (
                absorption_transfer_function,
                phase_transfer_function,
            ) = isotropic_thin_3d.calculate_transfer_function(
                **settings_dict,
            )

            # Save
            output_dataset[
                "absorption_transfer_function"
            ] = absorption_transfer_function.cpu().numpy()[None, None, ...]
            output_dataset[
                "phase_transfer_function"
            ] = phase_transfer_function.cpu().numpy()[None, None, ...]

        elif settings.reconstruction_dimension == 3:
            # Calculate transfer functions
            (
                real_potential_transfer_function,
                imaginary_potential_transfer_function,
            ) = phase_thick_3d.calculate_transfer_function(
                zyx_shape=(z_shape, y_shape, x_shape),
                **settings.phase.transfer_function.dict(),
            )
            # Save
            output_dataset[
                "real_potential_transfer_function"
            ] = real_potential_transfer_function.cpu().numpy()[None, None, ...]
            output_dataset[
                "imaginary_potential_transfer_function"
            ] = imaginary_potential_transfer_function.cpu().numpy()[
                None, None, ...
            ]

    if settings.fluorescence is not None:
        echo_headline(
            "Generating fluorescence transfer function with settings:"
        )
        echo_settings(settings.fluorescence.transfer_function)

        if settings.reconstruction_dimension == 2:
            raise NotImplementedError
        elif settings.reconstruction_dimension == 3:
            # Calculate transfer functions
            optical_transfer_function = (
                isotropic_fluorescent_thick_3d.calculate_transfer_function(
                    zyx_shape=(z_shape, y_shape, x_shape),
                    **settings.fluorescence.transfer_function.dict(),
                )
            )
            # Save
            output_dataset[
                "optical_transfer_function"
            ] = optical_transfer_function.cpu().numpy()[None, None, ...]

    # Write settings to metadata
    output_dataset.zattrs["settings"] = settings.dict()

    echo_headline(f"Closing {output_path}\n")
    output_dataset.close()

    echo_headline(
        f"Recreate this transfer function with:\n>> recorder compute-tf {input_data_path} -c {config_path} -o {output_path}"
    )


@click.command()
@click.help_option("-h", "--help")
@input_data_path_argument()
@config_path_option()
@output_dataset_options(default="./transfer-function.zarr")
def compute_tf(input_data_path, config_path, output_path):
    """
    Compute a transfer function using a a dataset and configuration file.

    See /examples/settings/ for example configuration files.

    Example usage:\n
    $ recorder compute-tf input.zarr -c /examples/settings/birefringence.yml -o output.zarr
    """
    compute_transfer_function_cli(input_data_path, config_path, output_path)
