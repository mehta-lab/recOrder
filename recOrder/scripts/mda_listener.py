import time
from pycromanager import Studio
import numpy as np
from ndtiff import Dataset
from iohub.ngff import open_ome_zarr
import tempfile

# Test OME TIFF
# Test diff orders
# Can display those into napari

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

position_list = tuple((0, i, 0) for i in range(p_max + 1))

zarr_path = "/Applications/Micro-Manager-2.0.1-20220920/prac_folder/hcs.zarr"

max_images = (p_max + 1) * (t_max + 1) * (c_max + 1) * (z_max + 1)

initialize = True
refresh_p = False
while datastore:
    if engine.isFinished():
        with open_ome_zarr(
            zarr_path,
            layout="hcs",
            mode="a",
            channel_names=channel_names
        ) as dataset:
            print(curr_p)
            position = dataset.create_position(curr_p + 1, "0", "0")
            position["0"] = position_array
            dataset.print_tree()
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
        # datastore get tiff location, list of readers/arrays, need to read source code
        # similar code mm to python -> may point to how to get tiff file location with memory mapping
        path = datastore.getSavePath()
        data = Dataset(path)
        image = data.read_image(curr_c, curr_z, curr_t, curr_p)

        if initialize:
            height, width = image.shape
            print(height, width)
            position_array = np.zeros((t_max + 1, c_max + 1, z_max + 1, width, height), dtype=np.uint16)
            initialize = False
        elif refresh_p:
            with open_ome_zarr(
                zarr_path,
                layout="hcs",
                mode="a",
                channel_names=channel_names
            ) as dataset:
                print(curr_p)
                position = dataset.create_position(curr_p, "0", "0")
                position["0"] = position_array
                dataset.print_tree()
            height, width = image.shape
            position_array = np.zeros((t_max + 1, c_max + 1, z_max + 1, width, height), dtype=np.uint16)
            refresh_p = False
            print(refresh_p)
        position_array[curr_t, curr_c, curr_z] = image

        img_count += 1

        # Update the dimensions
        # 0=TPZC, 1=TPCZ, 2=PTZC, 3=PTCZ
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
                            refresh_p = True
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
                            refresh_p = True
                            curr_t = 0


    print("Waiting..")
    # time.sleep(0.1)
