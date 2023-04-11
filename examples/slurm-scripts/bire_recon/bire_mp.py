# %%%
from iohub.reader import read_micromanager
from iohub.ngff import open_ome_zarr
from recOrder.io.utils import load_bg
import numpy as np
import multiprocessing as mp
from recOrder.compute.reconstructions import (
    initialize_reconstructor,
    reconstruct_qlipp_stokes,
)
import cv2

# debugging
from tqdm import tqdm
import click
import os


def mp_recon(args):
    (
        reader,
        bg_stokes,
        reconstructor,
        reconstructor_args,
        store_path,
        stack_info,
        states_chan,
    ) = args
    P, T, C_tot, Z, Y, X = stack_info
    stack = reader.get_zarr(P)[T, min(states_chan) : max(states_chan) + 1, Z]
    stack = np.expand_dims(stack, 1)
    stokes = reconstruct_qlipp_stokes(
        stack, reconstructor, bg_stokes=bg_stokes
    )
    birefringence = reconstructor.Polarization_recon(stokes)
    birefringence[0] = (
        birefringence[0] / (2 * np.pi) * reconstructor_args["wavelength_nm"]
    )
    with open_ome_zarr(store_path, mode="r+") as dataset:
        stack = dataset["0/0/" + str(P) + "/0"]
        # [Retardance, Orientation, BF, DoP]
        stack[T, : len(states_chan), Z] = birefringence[:, 0]


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
@click.option(
    "--bg",
    required=True,
    type=click.Path(exists=True),
    help="path to save the bire + fluor dataset (i.e /tmp)",
)
@click.option(
    "-p",
    required=True,
    help="number of positions to be processed",
)
def bire_mp(input, output, bg, p):
    p = int(p)
    print(input)
    print(output)

    #  Setup Readers 0
    reader = read_micromanager(input)
    T, C, Z, Y, X = reader.shape
    bg_data = load_bg(bg, height=Y, width=X)
    channel_names = reader.channel_names
    state_indices = [
        i for i, elem in enumerate(channel_names) if elem.find("State") != -1
    ]
    bire_channels = 4     #[Ret, Ori, BF, DoP]
    # Reconstruction Parameters
    reconstructor_args = {
        "image_dim": (Y, X),
        "mag": 20,  # magnification
        "pixel_size_um": 6.5,  # pixel size in um
        "n_slices": Z,  # number of slices in z-stack
        "z_step_um": 2,  # z-step size in um
        "wavelength_nm": 532,
        "swing": 0.1,
        "calibration_scheme": "4-State",  # "4-State" or "5-State"
        "NA_obj": 0.4,  # numerical aperture of objective
        "NA_illu": 0.2,  # numerical aperture of condenser
        "n_obj_media": 1.0,  # refractive index of objective immersion media
        "pad_z": 5,  # slices to pad for phase reconstruction boundary artifacts
        "bg_correction": "global",  # BG correction method: "None", "local_fit", "global"
        "mode": "3D",  # phase reconstruction mode, "2D" or "3D"
        "use_gpu": False,
        "gpu_id": 0,
    }
    reconstructor = initialize_reconstructor(
        pipeline="birefringence", **reconstructor_args
    )
    bg_stokes = reconstruct_qlipp_stokes(bg_data, reconstructor)

    mp_args = []
    for t in range(T):
        for z in range(Z):
            stack_info = (p, t, bire_channels, z, Y, X)
            mp_args.append(
                (
                    reader,
                    bg_stokes,
                    reconstructor,
                    reconstructor_args,
                    output,
                    stack_info,
                    state_indices,
                )
            )
    nProc = mp.cpu_count()
    pool = mp.Pool(nProc)
    print(nProc)
    results = []
    for result in tqdm(pool.imap(mp_recon, mp_args), total=len(mp_args)):
        results.append(result)


if __name__ == "__main__":
    bire_mp()

# %%
##
