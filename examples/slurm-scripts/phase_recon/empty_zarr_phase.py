# %%%
from iohub.reader import read_micromanager
from iohub.ngff import open_ome_zarr

# debugging
from tqdm import tqdm
import click
import numpy as np
from datetime import datetime


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
@click.option(
    "--output",
    required=True,
    type=str,
    help="path to save the bire + fluor dataset (i.e /tmp)",
)
def make_empty_array(input, output):
    # Define the Output path
    reader = read_micromanager(input)
    T, C, Z, Y, X = reader.shape
    num_positions = reader.get_num_positions()
    # [Ret,Ori,BF,DoP + fluorescence channels]
    recon_chan_names = ["Phase 3D"]
    C_tot = len(recon_chan_names)

    dchunks = (T, C_tot, Z, Y, X)
    zchunks = (1, 1, 1, Y, X)
    # Grab additional channel names typically from fluor channels and append
    with open_ome_zarr(
        output,
        layout="hcs",
        mode="w-",
        channel_names=recon_chan_names,
    ) as dataset:
        # Make the positions
        for i in tqdm(range(num_positions)):
            pos = dataset.create_position("position", str(i), "0")
            # this is a 'hack' to create placeholder metadata
            # future iohub should expose a public API for emtpy images
            pos._create_image_meta("0")
            arr = pos.zgroup.zeros(
                "0",
                shape=dchunks,
                chunks=zchunks,
                dtype=np.float32,
                **pos._storage_options
            )
        dataset.print_tree()


if __name__ == "__main__":
    make_empty_array()
