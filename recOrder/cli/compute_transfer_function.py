import click
import yaml
import numpy as np
from iohub import open_ome_zarr
from recOrder.cli.settings import TransferFunctionSettings
from recOrder.cli.parsing import config_path_option, output_dataset_options
from waveorder.models import (
    inplane_anisotropic_thin_pol3d,
    isotropic_thin_3d,
    phase_thick_3d,
)


@click.command()
@config_path_option()
@output_dataset_options()
def compute_transfer_function(config_path, output_path):
    "Compute a transfer function from configuration"

    # Load config file
    if config_path is None:
        settings = TransferFunctionSettings()
    else:
        with open(config_path) as file:
            raw_settings = yaml.safe_load(file)
        settings = TransferFunctionSettings(**raw_settings)

    click.echo("Generating transfer functions with settings:\n")
    click.echo(yaml.dump(settings.dict()))
    click.echo(f"Generating transfer functions and storing in {output_path}\n")

    dataset = open_ome_zarr(
        output_path, layout="fov", mode="w", channel_names=["None"]
    )

    # Pass settings to appropriate calculate_transfer_function and save
    if settings.reconstruct_phase:
        if settings.reconstruction_dimension == 2:
            # Convert zyx_shape and z_pixel_size into yx_shape and z_position_list
            settings_dict = settings.phase_transfer_function_settings.dict()
            z_shape, y_shape, x_shape = settings_dict["zyx_shape"]
            settings_dict["yx_shape"] = [y_shape, x_shape]
            settings_dict["z_position_list"] = list(
                (np.arange(z_shape) - z_shape // 2)
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
                wavelength_illumination=settings.wavelength_illumination,
            )

            # Save
            dataset["absorption"] = absorption_transfer_function.cpu().numpy()[
                None, None, ...
            ]
            dataset["phase"] = phase_transfer_function.cpu().numpy()[
                None, None, ...
            ]

        elif settings.reconstruction_dimension == 3:
            (
                real_transfer_function,
                imaginary_transfer_function,
            ) = phase_thick_3d.calculate_transfer_function(
                **settings.phase_transfer_function_settings.dict(),
                wavelength_illumination=settings.wavelength_illumination,
            )
            dataset["real"] = real_transfer_function.cpu().numpy()[
                None, None, ...
            ]
            dataset["imaginary"] = imaginary_transfer_function.cpu().numpy()[
                None, None, ...
            ]

    if settings.reconstruct_birefringence:
        i2s_matrix = (
            inplane_anisotropic_thin_pol3d.calculate_transfer_function(
                **settings.birefringence_transfer_function_settings.dict()
            )
        )
        dataset["i2s matrix"] = i2s_matrix.cpu().numpy()[None, None, None, ...]

    dataset.close()
