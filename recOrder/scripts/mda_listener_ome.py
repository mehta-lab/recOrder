 
from pycromanager import Studio
import numpy as np
# import tifffile as tiff
# from matplotlib import pyplot as plt
from iohub import open_ome_zarr
import os
import sys

studio = Studio(convert_camel_case=False)
manager = studio.getAcquisitionManager()
manager.runAcquisitionNonblocking()

engine = studio.getAcquisitionEngine()
datastore = engine.getAcquisitionDatastore()
mode = datastore.getPreferredSaveMode(studio).toString()
data_manager = studio.data()
sequence_settings = engine.getSequenceSettings()
acq_mode = sequence_settings.acqOrderMode()
print(acq_mode)

channel_names_string = datastore.getSummaryMetadata().getChannelNameList().toString()
channel_names = channel_names_string.strip('][').split(', ')

intended_dims = datastore.getSummaryMetadata().getIntendedDimensions()
print(intended_dims.toString())
p_max = intended_dims.getP() - 1
t_max = intended_dims.getT() - 1
c_max = intended_dims.getC() - 1
z_max = intended_dims.getZ() - 1

acq_dictionary = {
    0: "TPZC",
    1: "TPCZ",
    2: "PTZC",
    3: "PTCZ"
}
sequence_settings = engine.getSequenceSettings()
acq_mode = acq_dictionary[sequence_settings.acqOrderMode()]
print(acq_mode)

def update_dimensions(acq_mode, curr_p, curr_t, curr_c, curr_z):
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
r"c:\\Users\\Cameron\\Desktop\\Clinton_test\\example.zarr"

storage = datastore.getStorage()
reader_map = storage.getCoordsToReader()
print(storage)
print(reader_map)

path = datastore.getSavePath()
file_header = os.path.basename(path)
initialize = True
i = 0
while datastore:
    if engine.isFinished():
        print(f"Found {i} images\nFinished!")
        break
    # These are the current Image coords that we want
    # print(intended_dims.toString())
    required_coord = (
        intended_dims.copyBuilder().p(curr_p).t(curr_t).c(curr_c).z(curr_z).build()
    )
    # print(required_coord_builder.toString())
    found = False
    # Check if the storage has the Image coords
    # print(required_coord.toString())
    # print(storage.getCoordsToReader().toString())
    if storage.getCoordsToReader().containsKey(required_coord):
        i += 1
        print("Found", i)
        found = True
    if found:
        # Current OME-TIFF file that is being written to
        curr_file = os.path.join(path, f"{file_header}_MMStack_Pos{curr_p}.ome.tif") 

        # f"{path}/{file_header}_MMStack_Pos{curr_p}.ome.tif"

        print(f"Current p: {curr_p}\t Current t: {curr_t}\t Current c: {curr_c}\t Current z: {curr_z}")

        # Initialize the zarr store
        if initialize:
            image = storage.getImage(required_coord)
            height = image.getHeight()
            width = image.getWidth()
            with open_ome_zarr(
                zarr_path,
                layout="hcs",
                mode="w",
                channel_names=channel_names
            ) as dataset:
                for p in range(p_max + 1):
                    position = dataset.create_position("0", p, "0")
                    position["0"] = np.zeros((t_max + 1, c_max + 1, z_max + 1, height, width))
            if acq_mode == "TPCZ" or acq_mode == "PTCZ":
                z_array = np.zeros((z_max + 1, height, width), dtype=np.uint16)
            elif acq_mode == "TPZC" or acq_mode == "PTZC":
                czyx_array = np.zeros((c_max + 1, z_max + 1, height, width), dtype=np.uint16)
            initialize = False

        # Obtain the reader and get the offset for the current image
        curr_reader = reader_map.get(required_coord)
        offset = curr_reader.getCoordsToOffset().get(required_coord)
        if curr_p == 0 and curr_t == 0 and curr_c == 0 and curr_z == 0:
            offset += 210
        else:
            offset += 162

        # Access the data with the current offset
        print(file_header, curr_file)
        data = np.memmap(
            filename=curr_file,
            dtype=np.uint16,
            mode="r",
            offset=offset,
            shape = (height, width)
        )
        
        # Based on the acq_mode, update the zarr store
        # Write every z-stack or every channel finish
        # if acq_mode == "TPCZ" or acq_mode == "PTCZ":
        #     z_array[curr_z] = data
        #     if curr_z == z_max:
        #         with open_ome_zarr(
        #             zarr_path,
        #             mode="a"
        #         ) as dataset:
        #             img = dataset[f"0/{curr_p}/0"]
        #             img["0"][curr_t, curr_c] = z_array
        #         z_array = np.zeros((z_max + 1, height, width), dtype=np.uint16)
        # elif acq_mode == "TPZC" or acq_mode == "PTZC":
        #     czyx_array[curr_c, curr_z] = data
        #     if curr_c == c_max and curr_z == z_max:
        #         with open_ome_zarr(
        #             zarr_path,
        #             mode="a"
        #         ) as dataset:
        #             img = dataset[f"0/{curr_p}/0"]
        #             for c in range(c_max + 1):
        #                 img["0"][curr_t, c] = czyx_array[c]
        #         czyx_array = np.zeros((c_max + 1, z_max + 1, height, width))

        # Write every image
        with open_ome_zarr(
            zarr_path,
            mode="a"
        ) as dataset:
            img = dataset[f"0/{curr_p}/0"]
            img["0"][curr_t, curr_c, curr_z] = data

        if curr_p == p_max and curr_t == t_max and curr_c == c_max and curr_z == z_max:
            print(f"Reached max images {i}")
            break

        # Update the dimensions
        curr_p, curr_t, curr_c, curr_z = update_dimensions(acq_mode, curr_p, curr_t, curr_c, curr_z)
    # print("Waiting...")

