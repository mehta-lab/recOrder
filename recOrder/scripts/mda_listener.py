import time
from pycromanager import Studio
import numpy as np

# Test OME TIFF
# Test diff orders
# Can display those into napari

studio = Studio(convert_camel_case=False)
manager = studio.getAcquisitionManager()
# manager.runAcquisition()

engine = studio.getAcquisitionEngine()
datastore = engine.getAcquisitionDatastore()
mode = datastore.getPreferredSaveMode(studio).toString()
data_manager = studio.data()

sequence_settings = engine.getSequenceSettings()
acq_mode = sequence_settings.acqOrderMode() # 0=TPZC, 1=TPCZ, 2=PTZC, 3=PTCZ
print(acq_mode)
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
i = 0
while datastore:
    # print('Hello')
    if engine.isFinished():
        print(f"Found {i} images")
        if curr_p < p_max:
            raise RuntimeError("Position not finished properly")
        elif curr_t < t_max:
            print(curr_t, t_max)
            raise RuntimeError("Time not finished properly")
        print(f"End p: {curr_p}\t End t: {curr_t}")
        print("Finished!")
        break
    required_coord = (
        intended_dims.copyBuilder().p(curr_p).t(curr_t).c(curr_c).z(curr_z).build()
    )
    found = False
    # Look into how the datastore is being saved/are we traversing the whole datastore the whole time
    # -> might slow down the whole call if you have to traverse through the whole list
    if datastore.hasImage(required_coord):
        print("Found")
        found = True
    if found:
        i += 1
        # Do stuff w data
        print(f"Signal coord: {required_coord.toString()}")
        image = datastore.getImage(required_coord)
        # print(np.array(image.getRawPixels()).shape)
        print(f"Current p: {curr_p}\t Current t: {curr_t}\t Current c: {curr_c}\t Current z: {curr_z}")

        # Update p or t
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

    # print("Waiting..")
    # time.sleep(0.1)