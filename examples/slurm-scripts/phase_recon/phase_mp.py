# %%
import tempfile
from datetime import datetime
import numpy as np
import os
from recOrder.compute.reconstructions import (
    initialize_reconstructor,
    reconstruct_phase3D,
)
import waveorder as wo
from iohub.reader import read_micromanager
from iohub.ngff import open_ome_zarr

# Only for GPU

# debugging
import time
from tqdm import tqdm
import click


# %%
@click.group()
def cli():
    pass


@click.command()
@click.option(
    "--input",
    required=True,
    type=click.Path(exists=True),
    help="RAW ZARR Path",
)
@click.option(
    "--output",
    required=True,
    type=click.Path(exists=True),
    help="Output zarr path",
)
@click.option("-p", required=True, help="Position")
@click.option("--gpu", required=True, help="Nvidia-smi device number")
def phase_mp(input, output, p, gpu):
    print(f"USING GPU: {gpu}")
    p = int(p)
    reader = read_micromanager(input)
    channel_names = reader.channel_names
    BF_idx = [
        i for i, elem in enumerate(channel_names) if elem.find("BF") != -1
    ]
    if len(BF_idx) < 1:
        BF_idx = 0
    print(f"Channels: {channel_names},BF_idx {BF_idx}")
    T, C, Z, Y, X = reader.shape
    print(f"Input array shape: {reader.shape}")

    # %%
    # Splitting the FOV
    N_full = int(Y)
    M_full = int(X)
    overlapping_range = [0, 45]
    max_image_size = [200, 200]
    N_edge, N_space, M_space = wo.generate_FOV_splitting_parameters(
        (N_full, M_full), overlapping_range, max_image_size
    )
    # Create sub-FOV list
    Ns = N_space + N_edge
    Ms = M_space + N_edge
    ns, ms = wo.generate_sub_FOV_coordinates(
        (Y, X), (N_space, M_space), (N_edge, N_edge)
    )
    # Get the chunk sizes and data shapes
    row_list = (ns // N_space).astype("int")
    column_list = (ms // M_space).astype("int")
    # Chunking the data
    dchunks = (1, 1, Z, int(Ns), int(Ms))
    zchunks = (1, 1, 1, int(Ns), int(Ms))
    # Create intermediate zarr store
    tmp_store = f"{tempfile.gettempdir()}"
    if not os.path.isdir(tmp_store):
        os.mkdir(tmp_store)
    timestamp = datetime.now().strftime("/phase_tiles_%d%H%M%S_")
    tmp_store = tmp_store + timestamp + str(p) + ".zarr"
    # Initialize the empty zarr store once for intermediate in  case of multiprocessing
    with open_ome_zarr(
        tmp_store,
        layout="hcs",
        mode="w-",
        channel_names=["Phase_3D"],
    ) as dataset:
        # Make the positions
        for i in tqdm(range(len(ns))):
            pos = dataset.create_position("position", "0", str(i))
            # this is a 'hack' to create placeholder metadata
            # future iohub should expose a public API for emtpy images
            pos._create_image_meta("0")
            arr = pos.zgroup.zeros(
                "0",
                shape=dchunks,
                chunks=zchunks,
                dtype=np.float32,
                **pos._storage_options,
            )
        dataset.print_tree()

    # setup reconstructor.
    reconstructor_args = {
        "image_dim": (Ns, Ms),
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
        "use_gpu": True,
        "gpu_id": gpu,
    }

    reconstructor = initialize_reconstructor(
        pipeline="QLIPP", **reconstructor_args
    )

    for t in range(T):
        with open_ome_zarr(tmp_store, mode="r+") as dataset:
            for ll in tqdm(range(len(ns))):
                n_start = [int(ns[ll]), int(ms[ll])]
                start_time = time.time()
                S0 = reader.get_zarr(p)[
                    t,
                    BF_idx,
                    :Z,
                    n_start[0] : n_start[0] + Ns,
                    n_start[1] : n_start[1] + Ms,
                ]
                print(S0.shape)
                phase3D = reconstruct_phase3D(
                    S0, reconstructor, method="Tikhonov", reg_re=5e-2
                )
                phase3D = phase3D[np.newaxis, ...]
                # print(f"Shape of 3D phase data: {np.shape(phase3D)}")
                # print(f'3D Phase elapsed time:{time.time() - start_time}')
                print(
                    "Finish process at (y, x) = (%d, %d), elapsed time: %.2f"
                    % (ns[ll], ms[ll], time.time() - start_time)
                )
                stack = dataset["position/0/" + str(ll) + "/0"]
                stack[0] = phase3D.astype(np.float32)
        dataset.print_tree()

        # Save the stitched results
        # Open the tiled store path
        tiled_dataset = open_ome_zarr(tmp_store, mode="r")
        coord_list = (row_list, column_list)
        overlap = (int(np.array(N_edge)), int(np.array(N_edge)))
        # file_loading_func = lambda x: np.transpose(tiled_datset.get_zarr(x), (3, 4, 0, 1, 2))
        file_loading_func = lambda x: np.transpose(
            tiled_dataset["position/0/" + str(x) + "/0"], (3, 4, 0, 1, 2)
        )
        img_normalized, ref_stitch = wo.image_stitching(
            coord_list,
            overlap,
            file_loading_func,
            gen_ref_map=True,
            ref_stitch=None,
        )
        tiled_dataset.close()
        img_normalized = np.transpose(img_normalized, (2, 3, 4, 0, 1))
        # %%
        with open_ome_zarr(output, mode="r+") as dataset:
            stack = dataset["position/" + str(p) + "/0/0"]
            stack[t, 0, :Z, :Y, :X] = img_normalized[0, 0]
        print(f"FINISHED t:{t},pos:{p}")


if __name__ == "__main__":
    phase_mp()
