import numpy as np
import napari
import os
import sys
from ndtiff import Dataset
from iohub.ngff import open_ome_zarr
import time
from napari.qt import thread_worker
from pycromanager import Studio

viewer = napari.Viewer()


# Helper function to update the dimensions
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


# Update the napari layers given image data
def update_layers(data_name_tuple):
    img_data = data_name_tuple[0]
    layer_name = data_name_tuple[1]
    print(layer_name in viewer.layers)
    if layer_name in viewer.layers:
        viewer.layers[layer_name].data = img_data
    else:
        viewer.add_image(img_data, name=layer_name)


channel_names = ""


# Reads the zarr files and yields the image data to update_layers
@thread_worker(connect={"yielded": update_layers})
def read_zarr(path_and_coord_tuple):
    path = path_and_coord_tuple[0]
    curr_p = path_and_coord_tuple[1]
    # while True:
    with open_ome_zarr(
        path, layout="hcs", mode="r", channel_names=channel_names
    ) as dataset:
        position_data = dataset[f"0/{curr_p}/0"]["0"]
        print(curr_p)
        yield position_data, f"Position {curr_p}"


# Runs the MDA and converts the data to ome-zarr, yielding the zarr path to read_zarr
@thread_worker(connect={"yielded": read_zarr})
def mda_to_zarr():
    studio = Studio(convert_camel_case=False)
    manager = studio.getAcquisitionManager()
    # Run non blocking acquisition
    manager.runAcquisitionNonblocking()
    engine = studio.getAcquisitionEngine()
    datastore = engine.getAcquisitionDatastore()
    save_mode = datastore.getPreferredSaveMode(studio).toString()
    summary_metadata = datastore.getSummaryMetadata()
    channel_names_string = summary_metadata.getChannelNameList().toString()
    channel_names = channel_names_string.strip("][]").split(", ")
    intended_dimensions = summary_metadata.getIntendedDimensions()

    p_max = intended_dimensions.getP() - 1
    t_max = intended_dimensions.getT() - 1
    c_max = intended_dimensions.getC() - 1
    z_max = intended_dimensions.getZ() - 1

    max_images = (p_max + 1) * (t_max + 1) * (c_max + 1) * (z_max + 1)
    zarr_path = sys.argv[1]
    # Only for OME TIFF
    storage = datastore.getStorage()
    reader_map = storage.getCoordsToReader()
    path = datastore.getSavePath()
    file_header = os.path.basename(path)
    initialize = True

    acq_dictionary = {0: "TPZC", 1: "TPCZ", 2: "PTZC", 3: "PTCZ"}
    sequence_settings = engine.getSequenceSettings()
    acq_mode = acq_dictionary[sequence_settings.acqOrderMode()]
    curr_p, curr_t, curr_c, curr_z, img_count = 0, 0, 0, 0, 0
    initialize = True

    while datastore:
        if engine.isFinished() and img_count == max_images:
            print(f"Found {img_count} images\n Finished!")
            break
        # Current coord of image we want to get
        required_coord = (
            intended_dimensions.copyBuilder()
            .p(curr_p)
            .t(curr_t)
            .c(curr_c)
            .z(curr_z)
            .build()
        )
        found = False
        if save_mode == "ND_TIFF":
            if datastore.hasImage(required_coord):
                img_count += 1
                print(f"Found {img_count}")
                found = True
        # Check if the storage has the Image coords (OMETIFF)
        elif save_mode == "MULTIPAGE_TIFF":
            if storage.getCoordsToReader().containsKey(required_coord):
                img_count += 1
                print(f"Found {img_count}")
                found = True
        if found:
            curr_file = os.path.join(
                path, f"{file_header}_MMStack_Pos{curr_p}.ome.tif"
            )
            print(curr_file)
            # Wait for file to exist before reading
            while not os.path.exists(curr_file):
                print(f"Waiting for file... {curr_file}")
                time.sleep(0.5)

            # Initialize the zarr store
            if initialize:
                if save_mode == "ND_TIFF":
                    data = Dataset(path)
                    image = data.read_image(curr_c, curr_z, curr_t, curr_p)
                    height, width = image.shape
                elif save_mode == "MULTIPAGE_TIFF":
                    image = storage.getImage(required_coord)
                    height = image.getHeight()
                    width = image.getWidth()
                with open_ome_zarr(
                    zarr_path,
                    layout="hcs",
                    mode="w",
                    channel_names=channel_names,
                ) as dataset:
                    for p in range(p_max + 1):
                        position = dataset.create_position("0", p, "0")
                        position["0"] = np.zeros(
                            (t_max + 1, c_max + 1, z_max + 1, height, width)
                        )
                if acq_mode == "TPCZ" or acq_mode == "PTCZ":
                    zyx_array = np.zeros(
                        (z_max + 1, height, width), dtype=np.uint16
                    )
                elif acq_mode == "TPZC" or acq_mode == "PTZC":
                    czyx_array = np.zeros(
                        (c_max + 1, z_max + 1, height, width), dtype=np.uint16
                    )
                initialize = False

            if save_mode == "ND_TIFF":
                data = Dataset(path)
                image = data.read_image(curr_c, curr_z, curr_t, curr_p)
            elif save_mode == "MULTIPAGE_TIFF":
                # # Obtain the reader and get the offset for the current image
                curr_reader = reader_map.get(required_coord)
                offset = curr_reader.getCoordsToOffset().get(required_coord)
                # Add an offset, based on if the image is the first of the file
                if curr_t == 0 and curr_c == 0 and curr_z == 0:
                    offset += 210
                else:
                    offset += 162

                # Access the data with the current offset
                image = np.memmap(
                    filename=curr_file,
                    dtype=np.uint16,
                    mode="r",
                    offset=offset,
                    shape=(height, width),
                )

            # Based on the acq_mode, update the zarr store
            # Write every z-stack of every channel finish
            # if acq_mode == "TPCZ" or acq_mode == "PTCZ":
            #     zyx_array[curr_z] = image
            #     if curr_z == z_max:
            #         with open_ome_zarr(zarr_path, mode="a") as dataset:
            #             img = dataset[f"0/{curr_p}/0"]
            #             img["0"][curr_t, curr_c] = zyx_array
            #         zyx_array = np.zeros((z_max + 1, height, width), dtype=np.uint16)
            # elif acq_mode == "TPZC" or acq_mode == "PTZC":
            #     czyx_array[curr_c, curr_z] = image
            #     if curr_c == c_max and curr_z == z_max:
            #         with open_ome_zarr(zarr_path, mode="a") as dataset:
            #             img = dataset[f"0/{curr_p}/0"]
            #             for c in range(c_max + 1):
            #                 img["0"][curr_t, c] = czyx_array[c]
            #         czyx_array = np.zeros((c_max + 1, z_max + 1, height, width))

            # Write every image
            with open_ome_zarr(zarr_path, mode="a") as dataset:
                img = dataset[f"0/{curr_p}/0"]
                img["0"][curr_t, curr_c, curr_z] = image

            print(
                f"Current p: {curr_p}\t Current t: {curr_t}\t Current c: {curr_c}\t Current z: {curr_z}"
            )

            yield (zarr_path, curr_p, curr_t, curr_c, curr_z)

            if (
                curr_p == p_max
                and curr_t == t_max
                and curr_c == c_max
                and curr_z == z_max
            ):
                print(f"Reached max images {img_count}/{max_images}")
                break

            curr_p, curr_t, curr_c, curr_z = update_dimensions(
                acq_mode,
                curr_p,
                curr_t,
                curr_c,
                curr_z,
                p_max,
                t_max,
                c_max,
                z_max,
            )


mda_to_zarr()
napari.run()
