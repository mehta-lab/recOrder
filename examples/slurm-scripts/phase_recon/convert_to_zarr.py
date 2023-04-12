import click
import os
from datetime import datetime
from iohub.convert import TIFFConverter

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")


@click.group()
def cli():
    pass


@cli.command()
@click.help_option("-h", "--help")
@click.option(
    "--input",
    required=True,
    type=click.Path(exists=True),
    help="path to the RAW Zarrstore",
)
def convert_tiff_to_zarr(input):
    # Store the zarr inside the dataset folder
    datset_folder = os.path.join(input, os.pardir)
    temp_path = os.path.join(
        datset_folder, input + "_" + timestamp + "_tmp.zarr"
    )
    converter = TIFFConverter(input, temp_path)
    converter.run()
    print(temp_path)
    return temp_path


if __name__ == "__main__":
    convert_tiff_to_zarr()
