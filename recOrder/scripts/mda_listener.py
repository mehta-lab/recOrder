import time
from pycromanager import Studio
import numpy as np
from ndtiff import Dataset
from iohub.ngff import open_ome_zarr
import tempfile

# Test OME TIFF
# Test diff orders
# Can display those into napari
def update_dimensions(acq_mode, curr_p, curr_t, curr_c, curr_z):
    if acq_mode == 0:
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

    if acq_mode == 1:
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

    if acq_mode == 2:
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

    if acq_mode == 3:
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

studio = Studio(convert_camel_case=False)
manager = studio.getAcquisitionManager()
manager.runAcquisitionNonblocking()
# look for acq run non-blocking

engine = studio.getAcquisitionEngine()
datastore = engine.getAcquisitionDatastore()
mode = datastore.getPreferredSaveMode(studio).toString()
data_manager = studio.data()

sequence_settings = engine.getSequenceSettings()
acq_mode = sequence_settings.acqOrderMode() # 0=TPZC, 1=TPCZ, 2=PTZC, 3=PTCZ
print(acq_mode)
channel_names_string = datastore.getSummaryMetadata().getChannelNameList().toString()
print(type(channel_names_string))
channel_names = channel_names_string.strip('][').split(', ')
print(channel_names)
#seq settings acq order mode 

intended_dims = datastore.getSummaryMetadata().getIntendedDimensions()
p_max = intended_dims.getP() - 1 
t_max = intended_dims.getT() - 1
c_max = intended_dims.getC() - 1
z_max = intended_dims.getZ() - 1

print(f"max p: {p_max}\t max t: {t_max}\t max c: {c_max}\t max z: {z_max}")

curr_p = 0
curr_t = 0
curr_z = 0
curr_c = 0
img_count = 0

#f"{tempfile.gettempdir()}/hcs.zarr" 
zarr_path = "/Applications/Micro-Manager-2.0.1-20220920/prac_folder/hcs.zarr"

max_images = (p_max + 1) * (t_max + 1) * (c_max + 1) * (z_max + 1)

initialize = True
refresh_p = False
while datastore:
    if engine.isFinished():
        print(zarr_path)
        assert img_count == max_images, f"Found {img_count} images but should be {max_images}"
        if curr_p < p_max:
            raise RuntimeError("Position not finished properly")
        elif curr_t < t_max:
            raise RuntimeError("Time not finished properly")
        print(f"Found {img_count} images\nFinished!\nFinal position: {curr_p}")
        break
    required_coord = (
        intended_dims.copyBuilder().p(curr_p).t(curr_t).c(curr_c).z(curr_z).build()
    )
    found = False
    if datastore.hasImage(required_coord):
        print("Found")
        found = True
    if found:
        # Do stuff w data
        print(f"Signal coord: {required_coord.toString()}")
        print(f"Current p: {curr_p}\t Current t: {curr_t}\t Current c: {curr_c}\t Current z: {curr_z}")
        path = datastore.getSavePath()
        data = Dataset(path)
        image = data.read_image(curr_c, curr_z, curr_t, curr_p)

        # Initialize zarr store with same shape as data
        if initialize:
            height, width = image.shape
            with open_ome_zarr(
                zarr_path,
                layout="hcs",
                mode="w",
                channel_names=channel_names
            ) as dataset:
                print(zarr_path)
                for p in range(p_max + 1):
                    position = dataset.create_position("0", p, "0")
                    position["0"] = np.zeros((t_max + 1, c_max + 1, z_max + 1, height, width))
            if acq_mode == 1 or acq_mode == 3:
                z_array = np.zeros((z_max + 1, height, width), dtype=np.uint16)
            elif acq_mode == 0 or acq_mode == 2:
                czyx_array = np.zeros((c_max + 1, z_max + 1, height, width), dtype=np.uint16)
            initialize = False

        if acq_mode == 1 or acq_mode == 3:
            z_array[curr_z] = image
        elif acq_mode == 0 or acq_mode == 2:
            czyx_array[curr_c, curr_z] = image
            print(czyx_array)

        # Want to continuously update the zarr store with z-stacks
        if acq_mode == 1 or acq_mode == 3:
            if curr_z == z_max:
                with open_ome_zarr(
                    zarr_path,
                    mode="a",
                ) as dataset:
                    img = dataset[f"0/{curr_p}/0"]
                    img["0"][curr_t, curr_c] = z_array
                z_array = np.zeros((z_max + 1, height, width), dtype=np.uint16)
        elif acq_mode == 0 or acq_mode == 2:
            if curr_c == c_max and curr_z == z_max:
                with open_ome_zarr(
                    zarr_path,
                    mode="a",
                ) as dataset:
                    img = dataset[f"0/{curr_p}/0"]
                    for c in range(c_max + 1):
                        img["0"][curr_t, c] = czyx_array[c]
                        dataset.print_tree()
                czyx_array = np.zeros((c_max + 1, z_max + 1, height, width))

        img_count += 1

        # Update the dimensions
        # 0=TPZC, 1=TPCZ, 2=PTZC, 3=PTCZ
        curr_p, curr_t, curr_c, curr_z = update_dimensions(acq_mode, curr_p, curr_t, curr_c, curr_z)

    print("Waiting..")
    # time.sleep(0.1)

# If the engine finished before the script -> need to finish.
if img_count < max_images:
    # Need to know what the current dimensions are
    # Need to know the save path
    # Get the image
    # Save it to the zarr and iterate through
    print(curr_p, curr_t)

def update_zarr_store(zarr_path, layout, mode, array, curr_p):
    return