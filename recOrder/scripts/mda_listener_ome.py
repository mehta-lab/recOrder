from pycromanager import Studio
import numpy as np
from iohub import open_ome_zarr
import os
import sys
import time

studio = Studio(convert_camel_case=False)
manager = studio.getAcquisitionManager()
manager.runAcquisitionNonblocking()

engine = studio.getAcquisitionEngine()
datastore = engine.getAcquisitionDatastore()
mode = datastore.getPreferredSaveMode(studio).toString()
data_manager = studio.data()

channel_names_string = datastore.getSummaryMetadata().getChannelNameList().toString()
channel_names = channel_names_string.strip("][").split(", ")

intended_dims = datastore.getSummaryMetadata().getIntendedDimensions()
# 1 off
p_max = intended_dims.getP() - 1
t_max = intended_dims.getT() - 1
c_max = intended_dims.getC() - 1
z_max = intended_dims.getZ() - 1

# Get the acquisition mode
acq_dictionary = {0: "TPZC", 1: "TPCZ", 2: "PTZC", 3: "PTCZ"}
sequence_settings = engine.getSequenceSettings()
acq_mode = acq_dictionary[sequence_settings.acqOrderMode()]


def update_dimensions(
    acq_mode, curr_p, curr_t, curr_c, curr_z, p_max, t_max, c_max, z_max
):
    if acq_mode == "TPZC":
        if curr_c < c_max:
            curr_c += 1
        else:
            curr_c = 0
            if curr_z < z_max:
                curr_z += 1
            else:
                curr_z = 0
                if curr_p < p_max:
                    curr_p += 1
                else:
                    if curr_t < t_max:
                        curr_t += 1
                        curr_p = 0

    if acq_mode == "TPCZ":
        if curr_z < z_max:
            curr_z += 1
        else:
            curr_z = 0
            if curr_c < c_max:
                curr_c += 1
            else:
                curr_c = 0
                if curr_p < p_max:
                    curr_p += 1
                else:
                    if curr_t < t_max:
                        curr_t += 1
                        curr_p = 0

    if acq_mode == "PTZC":
        if curr_c < c_max:
            curr_c += 1
        else:
            curr_c = 0
            if curr_z < z_max:
                curr_z += 1
            else:
                curr_z = 0
                if curr_t < t_max:
                    curr_t += 1
                else:
                    if curr_p < p_max:
                        curr_p += 1
                        curr_t = 0

    if acq_mode == "PTCZ":
        if curr_z < z_max:
            curr_z += 1
        else:
            curr_z = 0
            if curr_c < c_max:
                curr_c += 1
            else:
                curr_c = 0
                if curr_t < t_max:
                    curr_t += 1
                else:
                    if curr_p < p_max:
                        curr_p += 1
                        curr_t = 0
    return curr_p, curr_t, curr_c, curr_z


print(f"max p: {p_max}\t max t: {t_max}\t max c: {c_max}\t max z: {z_max}")

curr_p = 0
curr_t = 0
curr_z = 0
curr_c = 0
img_count = 0

max_images = (p_max + 1) * (t_max + 1) * (c_max + 1) * (z_max + 1)
zarr_path = sys.argv[1]

storage = datastore.getStorage()
reader_map = storage.getCoordsToReader()

path = datastore.getSavePath()
file_header = os.path.basename(path)
initialize = True
while datastore:
    if engine.isFinished() and img_count == max_images:
        print(f"Found {img_count} images\nFinished!")
        break
    # Get coords of current image
    required_coord = (
        intended_dims.copyBuilder().p(curr_p).t(curr_t).c(curr_c).z(curr_z).build()
    )
    found = False
    # Check if the storage has the Image coords
    if storage.getCoordsToReader().containsKey(required_coord):
        img_count += 1
        print("Found", img_count)
        found = True
    if found:
        # Current OME-TIFF file that is being written to
        curr_file = os.path.join(path, f"{file_header}_MMStack_Pos{curr_p}.ome.tif")
        print(
            f"Current p: {curr_p}\t Current t: {curr_t}\t Current c: {curr_c}\t Current z: {curr_z}"
        )
        while not os.path.exists(curr_file):
            print(f"Waiting for file... {curr_file}")
            time.sleep(0.5)

        # f"{path}/{file_header}_MMStack_Pos{curr_p}.ome.tif"

        # Initialize the zarr store
        if initialize:
            image = storage.getImage(required_coord)
            height = image.getHeight()
            width = image.getWidth()
            with open_ome_zarr(
                zarr_path, layout="hcs", mode="w", channel_names=channel_names
            ) as dataset:
                for p in range(p_max + 1):
                    position = dataset.create_position("0", p, "0")
                    position["0"] = np.zeros(
                        (t_max + 1, c_max + 1, z_max + 1, height, width)
                    )
            if acq_mode == "TPCZ" or acq_mode == "PTCZ":
                z_array = np.zeros((z_max + 1, height, width), dtype=np.uint16)
            elif acq_mode == "TPZC" or acq_mode == "PTZC":
                czyx_array = np.zeros(
                    (c_max + 1, z_max + 1, height, width), dtype=np.uint16
                )
            initialize = False

        # Obtain the reader and get the offset for the current image
        curr_reader = reader_map.get(required_coord)
        offset = curr_reader.getCoordsToOffset().get(required_coord)
        # Add an offset, based on if the image is the first of the file
        if curr_t == 0 and curr_c == 0 and curr_z == 0:
            offset += 210
        else:
            offset += 162

        # Access the data with the current offset
        data = np.memmap(
            filename=curr_file,
            dtype=np.uint16,
            mode="r",
            offset=offset,
            shape=(height, width),
        )

        # Based on the acq_mode, update the zarr store
        # Write every z-stack or every channel finish
        if acq_mode == "TPCZ" or acq_mode == "PTCZ":
            z_array[curr_z] = data
            if curr_z == z_max:
                with open_ome_zarr(zarr_path, mode="a") as dataset:
                    img = dataset[f"0/{curr_p}/0"]
                    img["0"][curr_t, curr_c] = z_array
                z_array = np.zeros((z_max + 1, height, width), dtype=np.uint16)
        elif acq_mode == "TPZC" or acq_mode == "PTZC":
            czyx_array[curr_c, curr_z] = data
            if curr_c == c_max and curr_z == z_max:
                with open_ome_zarr(zarr_path, mode="a") as dataset:
                    img = dataset[f"0/{curr_p}/0"]
                    for c in range(c_max + 1):
                        img["0"][curr_t, c] = czyx_array[c]
                czyx_array = np.zeros((c_max + 1, z_max + 1, height, width))

        # # Write every image
        # with open_ome_zarr(zarr_path, mode="a") as dataset:
        #     img = dataset[f"0/{curr_p}/0"]
        #     img["0"][curr_t, curr_c, curr_z] = data

        # If last dimension, it should finish
        if curr_p == p_max and curr_t == t_max and curr_c == c_max and curr_z == z_max:
            print(f"Reached max images {img_count}")
            break

        # Update the dimensions
        curr_p, curr_t, curr_c, curr_z = update_dimensions(
            acq_mode, curr_p, curr_t, curr_c, curr_z, p_max, t_max, c_max, z_max
        )
    # print("Waiting...")
