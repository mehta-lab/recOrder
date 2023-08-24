from iohub import open_ome_zarr


def read_polarization_target_data():
    dataset = open_ome_zarr(
        "/Users/talon.chandler/Desktop/0.4.0-release/zenodo-v1.4.0/sample_contribution/raw_data.zarr"
    )
    layer_list = []
    for channel_index, channel_name in enumerate(dataset.channel_names):
        position = dataset["0/0/0"]
        data = (position["0"][0, channel_index],)
        layer_dict = {"name": channel_name, "scale": position.scale[3:]}
        layer_list.append((data, layer_dict))

    return layer_list


def read_polarization_target_reconstruction():
    dataset = open_ome_zarr(
        "/Users/talon.chandler/Desktop/0.4.0-release/zenodo-v1.4.0/sample_contribution/reconstruction.zarr"
    )
    layer_list = []
    for channel_index, channel_name in enumerate(
        ["Retardance", "Orientation"]
    ):
        position = dataset["0/0/0"]
        data = (position["0"][0, channel_index],)
        layer_dict = {"name": channel_name, "scale": position.scale[3:]}
        layer_list.append((data, layer_dict))

    return layer_list
