# 1. Create a dummy function that writes to a zarr store every couple of seconds
#    to mimick the listener writing to a zarr file.
# 2. Implement the threading of opening the zarr store, reading the data, yielding
#    data to the other thread of updating the napari layers
# Notes: There should be 3 components to this in the end:
#           1. MDA Listener (which also writes to zarr)
#           2. Zarr Listener (which should yield data)
#           3. Napari opener

from iohub.ngff import open_ome_zarr
import numpy as np
from napari.qt import thread_worker
import time
import napari

viewer = napari.Viewer()
# Set path here
path = "/Applications/Micro-Manager-2.0.1-20220920/prac_folder/napari_test/example.zarr"

channel_names = ["DAPI", "GFP"]

# Dummy function to write to a zarr store
def write_to_zarr(max_position, initialize, write_to_position):

    # Set shape here (T, C, Z, Y, X)
    shape = (5, 2, 3, 512, 512)
    dtype = np.uint16
    print(initialize)

    if initialize:
        with open_ome_zarr(
            store_path=path,
            layout="hcs",
            mode="w",
            channel_names=channel_names
        ) as dataset:
            for index in range(max_position):
                position = dataset.create_position("0", index, "0")
                position["0"] = np.zeros(shape, dtype=dtype)
            dataset.print_tree()
    else:
        with open_ome_zarr(
            store_path=path,
            mode="a",
        ) as dataset:
            curr_position = dataset[f"0/{write_to_position}/0"]
            curr_position["0"][:] = np.ones(shape=shape[:], dtype=dtype) * (write_to_position * 20000)

# Update the napari layer with data
def update_layers(info_name_tuple):
    # Update the napari viewer
    # Understand how the data is organized in the zarr file
    # How can I access each image and bring it up individually to the viewer
    # Need to look more into napari stuff
    #   - Do I have to build all the layers?
    #   - Will the layers already be there?
    data = info_name_tuple[0]
    layer_name = info_name_tuple[1]
    if layer_name in viewer.layers:
        viewer.layers[layer_name].data = data
        viewer.layers[layer_name].refresh()
    else:
        viewer.add_image(data, name=layer_name)

@thread_worker(connect={'yielded': update_layers})
def check_zarr_store():
    # 1. Write to zarr store
    # 2. Open up the zarr store
    # 3. Yield the data from the zarr store
    last_exec_time = time.time()
    write_to_position = 0
    initialize = True

    while True:
        curr_time = time.time()
        max_position = 5
        # print(last_exec_time)
        if write_to_position == max_position:
            break
        if initialize == True:
            write_to_zarr(max_position, True, write_to_position)
            last_exec_time = curr_time
            initialize = False
        if curr_time - last_exec_time > 5:
            write_to_zarr(max_position, False, write_to_position)
            last_exec_time = curr_time
            write_to_position += 1
        with open_ome_zarr(
            store_path=path,
            layout="hcs",
            mode="r",
            channel_names=channel_names
        ) as dataset:
            for name, position in dataset.positions():
                # print(name, position)
                # print(position.data.shape)
                yield (position.data, name)

        # yield data

def update_dimensions(acq_mode, curr_p, curr_t, curr_c, curr_z,
                      p_max, t_max, c_max, z_max):
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

check_zarr_store()
napari.run()