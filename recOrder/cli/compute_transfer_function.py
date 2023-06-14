import click
import numpy as np
import yaml
from iohub import open_ome_zarr
from recOrder.cli.printing import echo_settings, echo_headline
from recOrder.cli.settings import TransferFunctionSettings
from recOrder.cli.parsing import config_path_option, output_dataset_options
from waveorder.models import (
    inplane_oriented_thick_pol3d,
    isotropic_thin_3d,
    phase_thick_3d,
)


def compute_transfer_function_cli(config_path, output_path):
    # Load config file
    if config_path is None:
        settings = TransferFunctionSettings()
    else:
        with open(config_path) as file:
            raw_settings = yaml.safe_load(file)
        settings = TransferFunctionSettings(**raw_settings)

    echo_headline(
        f"Generating transfer functions and storing in {output_path}\n"
    )

    dataset = open_ome_zarr(
        output_path, layout="fov", mode="w", channel_names=["None"]
    )

    echo_headline("Generating transfer functions with universal settings:")
    echo_settings(settings.universal_settings)

    # Pass settings to appropriate calculate_transfer_function and save
    if settings.universal_settings.reconstruct_birefringence:
        echo_headline(
            "Generating birefringence transfer function with settings:"
        )
        echo_settings(settings.birefringence_transfer_function_settings)

        # Calculate transfer functions
        intensity_to_stokes_matrix = (
            inplane_oriented_thick_pol3d.calculate_transfer_function(
                **settings.birefringence_transfer_function_settings.dict()
            )
        )
        # Save
        dataset[
            "intensity_to_stokes_matrix"
        ] = intensity_to_stokes_matrix.cpu().numpy()[None, None, None, ...]

    if settings.universal_settings.reconstruct_phase:
        echo_headline("Generating phase transfer function with settings:")
        echo_settings(settings.phase_transfer_function_settings)

        if settings.universal_settings.reconstruction_dimension == 2:
            # Convert zyx_shape and z_pixel_size into yx_shape and z_position_list
            settings_dict = settings.phase_transfer_function_settings.dict()
            z_shape, y_shape, x_shape = settings_dict["zyx_shape"]
            settings_dict["yx_shape"] = [y_shape, x_shape]
            settings_dict["z_position_list"] = list(
                -(np.arange(z_shape) - z_shape // 2)
                * settings_dict["z_pixel_size"]
            )

            # Remove unused parameters
            settings_dict.pop("zyx_shape")
            settings_dict.pop("z_pixel_size")
            settings_dict.pop("z_padding")

            # Calculate transfer functions
            (
                absorption_transfer_function,
                phase_transfer_function,
            ) = isotropic_thin_3d.calculate_transfer_function(
                **settings_dict,
                wavelength_illumination=settings.universal_settings.wavelength_illumination,
            )

            # Save
            dataset[
                "absorption_transfer_function"
            ] = absorption_transfer_function.cpu().numpy()[None, None, ...]
            dataset[
                "phase_transfer_function"
            ] = phase_transfer_function.cpu().numpy()[None, None, ...]

        elif settings.universal_settings.reconstruction_dimension == 3:
            # Calculate transfer functions
            (
                real_potential_transfer_function,
                imaginary_potential_transfer_function,
            ) = phase_thick_3d.calculate_transfer_function(
                **settings.phase_transfer_function_settings.dict(),
                wavelength_illumination=settings.universal_settings.wavelength_illumination,
            )
            # Save
            dataset[
                "real_potential_transfer_function"
            ] = real_potential_transfer_function.cpu().numpy()[None, None, ...]
            dataset[
                "imaginary_potential_transfer_function"
            ] = imaginary_potential_transfer_function.cpu().numpy()[
                None, None, ...
            ]

    # Write settings to metadata
    dataset.zattrs["transfer_function_settings"] = settings.dict()

    echo_headline(f"Closing {output_path}\n")
    dataset.close()

    echo_headline(
        f"Recreate this transfer function with:\n>> recorder compute-transfer-function {config_path} -o {output_path}"
    )


@click.command()
@config_path_option()
@output_dataset_options(default="./transfer-function.zarr")
def compute_transfer_function(config_path, output_path):
    "Compute a transfer function from a configuration file"
    compute_transfer_function_cli(config_path, output_path)
