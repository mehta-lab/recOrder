import numpy as np
import napari
from skimage import data
from matplotlib import pyplot as plt
from iohub.ngff import open_ome_zarr
import time
from napari.qt import thread_worker

brain_data = data.brain()
# plt.imshow(brain_data[5])
# plt.show()

viewer = napari.Viewer()

path = "/Applications/Micro-Manager-2.0.1-20220920/prac_folder/napari_test/brain.zarr"

def initialize(path):
    with open_ome_zarr(
        path,
        layout="hcs",
        mode="w",
        channel_names=["BF"]
    ) as dataset:
        position = dataset.create_position("0", "0", "0")
        position["0"] = np.zeros(shape=(1, 1, 10, 256, 256), dtype=np.uint16)

def update_layers(data_name_tuple):
    img_data = data_name_tuple[0]
    layer_name = data_name_tuple[1]
    if layer_name in viewer.layers:
        viewer.layers["0"].data = img_data
    else:
        viewer.add_image(img_data, name=layer_name)


@thread_worker(connect={"yielded": update_layers})
def read_zarr(path):
    # while True:
        with open_ome_zarr(
            path,
            layout="hcs",
            mode="r",
            channel_names=["BF"]
        ) as dataset:
            img = dataset["0/0/0"]
            img_array = []
            for index in range(brain_data.shape[0]):
                img_data = img["0"][0, 0, index]
                img_array.append(img_data)
                # update_layers((np.array(img_array), "0"))
                yield np.array(img_array), "0"

@thread_worker(connect={"yielded": read_zarr})
def zarr_write(path):
    with open_ome_zarr(
        path,
        layout="hcs",
        mode="a",
        channel_names=["BF"]
    ) as dataset:
        data = dataset["0/0/0"]
        img = data["0"]
        for index in range(brain_data.shape[0]):
            time.sleep(2)
            img[0, 0, index] = brain_data[index]
            yield path

initialize(path)
zarr_write(path)
time.sleep(2)
napari.run()