import time
from pycromanager import Studio
import numpy as np

# Test OME TIFF
# Test diff orders
# Can display those into napari

studio = Studio(convert_camel_case=False)
engine = studio.getAcquisitionEngine()
datastore = engine.getAcquisitionDatastore()
mode = datastore.getPreferredSaveMode(studio).toString()
data_manager = studio.data()

sequence_settings = engine.getSequenceSettings()
acq_mode = sequence_settings.acqOrderMode() # 0=TPZC, 1=TPCZ, 2=PTZC, 3=PTCZ
print(acq_mode)
#seq settings acq order mode 
manager = studio.getAcquisitionManager()

intended_dims = datastore.getSummaryMetadata().getIntendedDimensions()
p_max = intended_dims.getP() - 1 
t_max = intended_dims.getT() - 1
c_max = intended_dims.getC() - 1
z_max = intended_dims.getZ() - 1

print(f"max p: {p_max}\t max t: {t_max}\t max c: {c_max}\t max z: {z_max}")

curr_p = 0
curr_t = 0
while datastore:
    if engine.isFinished():
        if curr_p < p_max:
            raise RuntimeError("Position not finished properly")
        elif curr_t < t_max:
            raise RuntimeError("Time not finished properly")
        print(f"Current p: {curr_p}\t Current t: {curr_t}")
        print("Finished!")
        break
    required_coord = (
        intended_dims.copyBuilder().p(curr_p).t(curr_t).c(c_max).z(z_max).build()
    )
    found = False
    if datastore.hasImage(required_coord):
        print("Found")
        found = True
    if found:
        # Do stuff w data
        print(f"Signal coord: {required_coord.toString()}")
        print(f"Current p: {curr_p}\t Current t: {curr_t}")

        # Update p or t
        if acq_mode == 0 or acq_mode == 1:
            # Do stuff
            if curr_p < p_max:
                curr_p += 1
            else:
                curr_p = 0
                curr_t += 1
        elif acq_mode == 2 or acq_mode == 3:
            if curr_t < t_max:
                curr_t += 1
            else:
                curr_t = 0
                curr_p += 1

    print("Waiting..")
    time.sleep(0.1)