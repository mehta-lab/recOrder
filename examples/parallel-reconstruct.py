import shutil
import os
import numpy as np
import multiprocessing as mp
from wget import download
from datetime import datetime
from iohub import open_ome_zarr
from iohub.convert import TIFFConverter
from recOrder.io.utils import load_bg
from recOrder.compute.reconstructions import (
    initialize_reconstructor,
    reconstruct_qlipp_stokes,
    reconstruct_qlipp_birefringence,
    reconstruct_phase3D,
)

# This example demonstrates a 3D-pol-to-birfringence reconstruction applied
# to each position and time point of a micromanager dataset. The example
# uses multiprocessing to apply the reconstructions in parallel.

# This example will download a ~50 MB test dataset to your working directory.

N_processes = 6  # (should have at least this many cores available)


def precomputation():

    # download test data
    data_folder = os.path.join(os.getcwd(), "data_temp")
    os.makedirs(data_folder, exist_ok=True)
    url = "https://zenodo.org/record/6983916/files/recOrder_test_data.zip?download=1"
    zip_file = "recOrder_test_Data.zip"
    output = os.path.join(data_folder, zip_file)
    if not os.path.exists(output):
        print("Downloading test files...")
        download(url, out=output)
        shutil.unpack_archive(output, extract_dir=data_folder)

    temp_path = os.path.join(data_folder, "temp.zarr")
    converter = TIFFConverter(
        os.path.join(
            data_folder,
            "2022_08_04_recOrder_pytest_20x_04NA/2T_3P_16Z_128Y_256X_Kazansky_1",
        ),
        temp_path,
    )
    converter.run()

    # setup input reader
    reader = open_ome_zarr(temp_path, mode="r+")
    T, C, Z, Y, X = reader["0/0/0"].data.shape
    dtype = reader["0/0/0"].data.dtype
    P = len(list(reader.positions()))
    bg_data = load_bg(
        os.path.join(data_folder, "2022_08_04_recOrder_pytest_20x_04NA/BG/"),
        height=Y,
        width=X,
    )

    # setup output zarr
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    writer = open_ome_zarr(
        "./output/reconstructions_" + timestamp + ".zarr",
        layout="hcs",
        mode="w-",
        channel_names=[
            "Retardance",
            "Orientation",
            "BF - computed",
            "DoP",
            "Phase",
        ],
    )
    for p in range(P):
        position = writer.create_position("0", str(p), "0")
        position.create_zeros(name="0", shape=(T, 5, Z, Y, X), dtype=dtype)

    return (reader, bg_data, writer)


# define the work to be done on a single process
# in this example a single process will loop through a set of CZYX volumes, and
# for each volume it will read the data, apply a reconstruction, then save the
# result to a hcs-format zarr
def single_process(i, reader, bg_data, writer, vol_start, vol_end):
    T, C, Z, Y, X = reader["0/0/0"].data.shape
    for vol in range(vol_start, vol_end + 1):
        print("DEBUG:", i, vol)
        p = int(np.floor(vol / T))
        t = int(vol % T)
        print(f"Reconstructing vol={vol}, pos={p}, time={t}")

        data = reader["0/" + str(p) + "/0"]["0"][t, ...]

        # Set up a reconstructor.
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
            "bg_correction": "local_fit",  # BG correction method: "None", "local_fit", "global"
            "mode": "3D",  # phase reconstruction mode, "2D" or "3D"
            "use_gpu": False,
            "gpu_id": 0,
        }
        reconstructor = initialize_reconstructor(
            pipeline="QLIPP", **reconstructor_args
        )

        # Reconstruct background Stokes
        bg_stokes = reconstruct_qlipp_stokes(bg_data, reconstructor)

        # Reconstruct data Stokes w/ background correction
        stokes = reconstruct_qlipp_stokes(data, reconstructor, bg_stokes)

        # Reconstruct Birefringence from Stokes
        # Shape of the output birefringence will be (C, Z, Y, X) where
        # Channel order = Retardance [nm], Orientation [rad], Brightfield (S0), Degree of Polarization
        birefringence = reconstruct_qlipp_birefringence(stokes, reconstructor)
        birefringence[0] = (
            birefringence[0]
            / (2 * np.pi)
            * reconstructor_args["wavelength_nm"]
        )

        # Reconstruct Phase3D from S0
        S0 = birefringence[2]
        phase3D = reconstruct_phase3D(
            S0, reconstructor, method="Tikhonov", reg_re=1e-2
        )

        writer["0/" + str(p) + "/0"]["0"][t, 0:4] = birefringence
        writer["0/" + str(p) + "/0"]["0"][t, 4] = phase3D


# prepare the processes
# we will apply the same reconstruction to each position and time point, so we
# need to split the CZYX volumes among the processes
if __name__ == "__main__":
    reader, bg_data, writer = precomputation()
    processes = []
    V = len(list(reader.positions())) * reader["0/0/0"].data.shape[0]
    vol_per_process = int(np.ceil(V / N_processes))
    print("vol_per_process", vol_per_process)
    for i in range(N_processes):
        vol_start = i * vol_per_process
        vol_end = np.minimum(vol_start + vol_per_process - 1, V - 1)
        print(f"Preparing volumes {vol_start}-{vol_end} for process {i}")
        processes.append(
            mp.Process(
                target=single_process,
                args=(i, reader, bg_data, writer, vol_start, vol_end),
            )
        )
    print("STARTING PROCESSES")
    # run the processes
    for process in processes:
        process.start()
    for process in processes:
        process.join()

    writer.close()
