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
#seq settings acq order mode 
manager = studio.getAcquisitionManager()

intended_dims = datastore.getSummaryMetadata().getIntendedDimensions()
p_max = intended_dims.getP() - 1
t_max = intended_dims.getT() - 1
c_max = intended_dims.getC() - 1
z_max = intended_dims.getZ() - 1

p = 0
prev_pixels = None
while datastore:
    if engine.isFinished():
        if p < p_max:
            raise RuntimeError("Not finished properly")
        print("Finished!")
        break
    required_coord = (
        intended_dims.copyBuilder().p(p).t(t_max).c(c_max).z(z_max).build()
    )

    written_coords = datastore.getUnorderedImageCoords()
    found = False
    print(written_coords)
    if mode == "ND_TIFF":
        written_coords = written_coords.iterator()
        while written_coords.hasNext():
            next_coord = written_coords.next()
            if next_coord.toString() == required_coord.toString():
                found = True 
                break
    elif written_coords.contains(required_coord.toString()):
            found = True
    if found:
        print(f"Found position {p}")
        print(next_coord.toString())
        image = datastore.getImage(next_coord)
        print(image)
        height = image.getHeight()
        width = image.getWidth()
        intensity_at_mid = image.getIntensityStringAt(70, 350)
        metadata = image.getMetadata()
        x_stage = metadata.getXPositionUm()
        y_stage = metadata.getYPositionUm()
        pixels = image.getRawPixels()
        print(type(pixels))
        print(f"Match: {np.array_equiv(pixels, prev_pixels)}")
        print(f"Height: {height} \nWidth: {width}\nPoint Intensity: {intensity_at_mid}")
        print(f"Metadata: {metadata} \nPixels: {pixels}")
        print(f"Stage position: ({x_stage}, {y_stage})")
        p += 1
        prev_pixels = pixels
    print("Waiting...")
    time.sleep(1.5)