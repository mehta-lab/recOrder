# %%
# this script demonstrates how to obtain the current acquisition progress
# from a running MM MDA through JAVA calls translated with pycromanager

import time
from pycromanager import Studio

studio = Studio(convert_camel_case=False)

engine = studio.getAcquisitionEngine()

# %%
# here the MDA should be in PTCZ order for the demo to work
# since it detects and print finished positions
# start MDA before running this block or the data store will be None

datastore = engine.getAcquisitionDatastore()
mode = datastore.getPreferredSaveMode(studio).toString()

intended_dims = datastore.getSummaryMetadata().getIntendedDimensions()
p_max = intended_dims.getP() - 1
t_max = intended_dims.getT() - 1
c_max = intended_dims.getC() - 1
z_max = intended_dims.getZ() - 1

p = 0
last = False

while datastore:
    if engine.isFinished():
        if p < p_max:
            raise RuntimeError("not finished properly")
        print("Finished!")
        break
    required_coord = (
        intended_dims.copyBuilder().p(p).t(t_max).c(c_max).z(z_max).build()
    )
    # this call is guaranteed to get the coordinates that are already
    # written to files in an OME-TIFF storage to avoid race, see:
    # https://github.com/micro-manager/micro-manager/blob/4fd5cfa15f420fb553ae176243f8fdb5d4cb80ed/mmstudio/src/main/java/org/micromanager/data/internal/multipagetiff/StorageMultipageTiff.java#L989-L992 #noqa
    # not sure if NF-TIFF follows the same behavior
    # NDTiffAdaptor also returns a different type (iterator) than a set in OME-TIFF:
    # https://github.com/micro-manager/micro-manager/blob/4fd5cfa15f420fb553ae176243f8fdb5d4cb80ed/mmstudio/src/main/java/org/micromanager/data/internal/ndtiff/NDTiffAdapter.java#L198-L205 #noqa
    written_coords = datastore.getUnorderedImageCoords()
    found = False
    if mode == "ND_TIFF":
        written_coords = written_coords.iterator()
        while written_coords.hasNext():
            if written_coords.next().toString() == required_coord.toString():
                found = True
                break
    else:
        if written_coords.contains(required_coord):
            found = True
    if found:
        print(f"Found {p}")
        print(required_coord)
        p += 1
    print("Waiting...")
    time.sleep(1)

# %%
