import numpy as np
import napari
import os
import sys
from ndtiff import Dataset
from iohub.ngff import open_ome_zarr, ImageArray
import time
from napari.qt import thread_worker
from pycromanager import Studio
from recOrder.cli.compute_transfer_function import (
    compute_transfer_function_cli,
)
from recOrder.cli.apply_inverse_transfer_function import (
    apply_inverse_transfer_function_cli,
    _load_configuration_settings,
)
from recOrder.io.utils import ret_ori_overlay
from queue import Queue
import zarr

viewer = napari.Viewer()


def update_dimensions(
    acq_mode, curr_p, curr_t, curr_c, curr_z, p_max, t_max, c_max, z_max
):
    """
    Helper function to update the dimensions to follow the Multi-Dimensional Acquisition (MDA),
    based on the acquisition mode.

    Parameters
    ----------
    acq_mode : string
        The current acquisition mode of the MDA
    curr_p : int
        Current position
    curr_t : int
        Current time
    curr_c : int
        Current channel
    curr_z : int
        Current z
    p_max : int
        Max position
    t_max : int
        Max time
    c_max : int
        Max channel
    z_max : int
        Max z

    Returns
    -------
    tuple(int, int, int, int)
    Returns the current position, time, channel, and z as ints in a tuple (in that order).
    """
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
    elif acq_mode == "TPCZ":
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
    elif acq_mode == "PTZC":
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
    elif acq_mode == "PTCZ":
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


def update_layers(data_name_tuple):
    """
    Updates the napari viewer at the given layer name with the given data.

    Parameters
    ----------
    data_name_tuple : tuple(ImageArray or numpy array, string)
        A tuple containing image data as a numpy array and the layer name, to update, as a string.
    """
    position_data: ImageArray or np.ndarray = data_name_tuple[0]
    layer_name: str = data_name_tuple[1]
    print(f"Updating napari layer {layer_name}")
    if layer_name in viewer.layers:
        viewer.layers[layer_name].data = position_data
    else:
        viewer.add_image(position_data, name=layer_name)


@thread_worker(connect={"yielded": update_layers})
def reconstruct_zarr(queue):
    """
    Reconstructs the imaging data in the queue and yields the data to update_layers.

    Parameters
    ----------
    queue: Queue
        A FIFO queue that has information for the reconstruction to happen.

    Yields
    ------
    tuple(ImageArray or numpy array, string)
        A tuple of the position data as an array and the layer name as a string.
    #"""
    last_pos = None
    while True:
        path_position_tfpath_tuple = queue.get()
        if path_position_tfpath_tuple:
            recon_start_time = time.time()
            zarr_path: str = path_position_tfpath_tuple[0]
            curr_position: int = path_position_tfpath_tuple[1]
            transfer_function_path: str = path_position_tfpath_tuple[2]
            curr_time: int = path_position_tfpath_tuple[3]

            # Input data path should be where the zarr store is and accessing each position
            input_data_path = os.path.join(
                zarr_path, "0", str(curr_position), "0"
            )
            # Find a way to customize this config path
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(zarr_path)),
                "birefringence.yml",
            )
            # Creates a pydantic model of the configuration settings
            config_settings = _load_configuration_settings(config_path)
            config_settings.time_indices = curr_time

            # Find a way to customize this transfer function path
            transfer_function_path = os.path.join(
                os.path.dirname(zarr_path), "transfer_function.zarr"
            )
            # Find a way to customize this output path of the reconstructions
            output_path = os.path.join(
                os.path.dirname(zarr_path),
                f"reconstruction{curr_position}.zarr",
            )
            # Birefringence only
            if (config_settings.birefringence is not None) and (
                not config_settings.phase
            ):
                print(f"\nApplying birefringence inverse transfer function\n")
                # Apply inverse transfer function on czyx stack and then apply the ret_ori_overlay
                apply_inverse_transfer_function_cli(
                    input_data_path,
                    transfer_function_path,
                    config_settings,
                    output_path,
                )
                with open_ome_zarr(
                    output_path, layout="fov", mode="r"
                ) as dataset:
                    position_data = dataset[0]
                    retardance = position_data[curr_time, 0]
                    orientation = position_data[curr_time, 1]
                    data = ret_ori_overlay(
                        retardance,
                        orientation,
                        ret_max=np.percentile(np.ravel(retardance), 89.99),
                        cmap="HSV",
                    )
                if curr_position != last_pos:
                    # Find a way to customize this temp zarr path
                    zarr_array = zarr.open_array(
                        store=os.path.join(
                            os.path.dirname(zarr_path),
                            f"temp_zarr{curr_position}",
                        ),
                        mode="w",
                        shape=data.shape,
                    )
                    zarr_array[:] = data
                    last_pos = curr_position
                else:
                    zarr_array.append(data)
                print(
                    f"Reconstruction finished in {time.time() - recon_start_time}"
                )
                yield zarr_array, f"Overlay{curr_position}"
                queue.task_done()
            # Phase only
            elif (config_settings.phase is not None) and (
                not config_settings.birefringence
            ):
                print(f"\nApplying phase inverse transfer function\n")
                apply_inverse_transfer_function_cli(
                    input_data_path,
                    transfer_function_path,
                    config_settings,
                    output_path,
                )
                print(
                    f"Reconstruction finished in {time.time() - recon_start_time}"
                )
                with open_ome_zarr(
                    output_path, layout="fov", mode="r"
                ) as dataset:
                    print(f"Getting data from position {curr_position}")
                    dataset.print_tree()
                    position_data = dataset[0]
                    yield position_data, f"Position {curr_position}"
                queue.task_done()


def initialize_transfer_function_call(zarr_path: str, curr_p: int):
    """
    Once the first z-stack is finished, initialize the transfer function that will be used
    for future reconstructions.

    Parameters
    ----------
    zarr_path : string
        The path of the zarr store that contains imaging data.
    curr_p : int
        The current position.

    Returns
    -------
    string
        The path of the computed transfer function.
    """
    tf_start_time = time.time()
    input_data_path = os.path.join(zarr_path, "0", str(curr_p), "0")
    # Find a way to customize this config path
    config_path = os.path.join(
        zarr_path, os.pardir, os.pardir, "birefringence.yml"
    )
    # Find a way to customize this transfer function path
    transfer_function_path = os.path.join(
        zarr_path, os.pardir, "transfer_function.zarr"
    )
    print(f"\nInitializing transfer function at {transfer_function_path}\n")
    compute_transfer_function_cli(
        input_data_path, config_path, transfer_function_path
    )
    initialize_tf_time = time.time() - tf_start_time
    print(f"\nInitialize transfer function in {initialize_tf_time} seconds\n")
    return transfer_function_path


@thread_worker(connect={"yielded": reconstruct_zarr})
def mda_to_zarr():
    """
    Runs an Multi-Dimensional Acquisition (MDA) and writes the image data (OME-TIFF or ND-TIFF)
    to zarr. Constantly updates a job queue with the next reconstruction job.

    Yields
    ------
    Queue
        A FIFO queue that has information for reconstructions.
    """
    studio = Studio(convert_camel_case=False)
    manager = studio.getAcquisitionManager()
    # Run non blocking acquisition
    manager.runAcquisitionNonblocking()
    start_time = time.time()
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
    # Command arguments
    zarr_path = sys.argv[1]
    reconstruction_type = sys.argv[2]
    # Only for OME TIFF
    storage = datastore.getStorage()
    if save_mode == "MULTIPAGE_TIFF":
        reader_map = storage.getCoordsToReader()
    path = datastore.getSavePath()
    file_header = os.path.basename(path)

    # Dictionary to convert the acqusition mode into a string format
    acq_dictionary = {0: "TPZC", 1: "TPCZ", 2: "PTZC", 3: "PTCZ"}
    sequence_settings = engine.getSequenceSettings()
    acq_mode = acq_dictionary[sequence_settings.acqOrderMode()]
    curr_p, curr_t, curr_c, curr_z, img_count = 0, 0, 0, 0, 0
    initialize = True
    initialize_transfer_function = True
    first_page = True
    last_file = None
    queue = Queue()
    yield queue

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
        # Check if the storage has the Image coords (NDTIFF)
        if save_mode == "ND_TIFF":
            if storage.hasImage(required_coord):
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
            if save_mode == "ND_TIFF":
                curr_file = path
            elif save_mode == "MULTIPAGE_TIFF":
                curr_file = os.path.join(
                    path, f"{file_header}_MMStack_Pos{curr_p}.ome.tif"
                )
                if last_file != curr_file:
                    first_page = True
                    last_file = curr_file
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
                        position.create_zeros(
                            name="0",
                            shape=(
                                t_max + 1,
                                c_max + 1,
                                z_max + 1,
                                height,
                                width,
                            ),
                            dtype=np.uint16,
                            chunks=(1, 1, 1, height, width),
                        )
                initialize = False

            # Get the image data
            if save_mode == "ND_TIFF":
                data = Dataset(path)
                while not data.has_image(curr_c, curr_z, curr_t, curr_p):
                    time.sleep(0.1)
                    data = Dataset(path)
                image = data.read_image(curr_c, curr_z, curr_t, curr_p)
            elif save_mode == "MULTIPAGE_TIFF":
                # Obtain the reader and get the offset for the current image
                curr_reader = reader_map.get(required_coord)
                offset = curr_reader.getCoordsToOffset().get(required_coord)
                # Add an offset, based on if the image is the first of the file
                if first_page:
                    offset += 210
                    first_page = False
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

            # Write every image
            with open_ome_zarr(zarr_path, mode="a") as dataset:
                img = dataset[f"0/{curr_p}/0"]
                img["0"][curr_t, curr_c, curr_z] = image

            print(
                f"Current p: {curr_p}\t Current t: {curr_t}\t Current c: {curr_c}\t Current z: {curr_z}"
            )

            # Monitoring zyx chunks for phase reconstruction
            if reconstruction_type == "phase":
                z_done = False
                if acq_mode == "TPCZ" or acq_mode == "PTCZ":
                    if curr_z == z_max:
                        z_done = True
                elif acq_mode == "TPZC" or acq_mode == "PTZC":
                    if curr_z == z_max and curr_c == c_max:
                        z_done = True

                if z_done and initialize_transfer_function:
                    transfer_function_path = initialize_transfer_function_call(
                        zarr_path, curr_p
                    )
                    initialize_transfer_function = False

                # Update the queue
                if z_done:
                    send_tuple = (
                        zarr_path,
                        curr_p,
                        transfer_function_path,
                        curr_t,
                    )
                    queue.put(send_tuple)
            # Monitoring czyx chunks for birefringence reconstruction
            elif reconstruction_type == "birefringence":
                c_done = False
                if curr_z == z_max and curr_c == c_max:
                    c_done = True
                if c_done and initialize_transfer_function:
                    transfer_function_path = initialize_transfer_function_call(
                        zarr_path, curr_p
                    )
                    initialize_transfer_function = False

                if c_done:
                    send_tuple = (
                        zarr_path,
                        curr_p,
                        transfer_function_path,
                        curr_t,
                    )
                    queue.put(send_tuple)

            if (
                curr_p == p_max
                and curr_t == t_max
                and curr_c == c_max
                and curr_z == z_max
            ):
                print(f"Reached max images {img_count}/{max_images}")
                print(
                    f"Wrote all images to zarr in {time.time() - start_time} seconds."
                )
                queue.join()
                # This is when the queue finishes all jobs -> finish time
                print(
                    f"Finished all reconstructions in {time.time() - start_time}!"
                )
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
    # queue.join()


mda_to_zarr()
napari.run()
