import click
import napari
import numpy as np
from iohub.reader import print_info
from iohub import read_micromanager


@click.group()
def cli():
    print(
        "\033[92mrecOrder: Computational Toolkit for Label-Free Imaging\033[0m\n"
    )


@cli.command()
@click.help_option("-h", "--help")
@click.argument("filename")
@click.option(
    "--positions",
    "-p",
    default=None,
    multiple=True,
    help="Integer positions to open. Accepts multiple positions: -p 0 -p 1 -p 10.",
)
@click.option(
    "--layers",
    "-l",
    default="position",
    type=click.Choice(["position", "channel", "p", "c"]),
    help="Layers as 'position' ('p') or 'channel' ('c')",
)
def view(filename, positions=None, layers=None):
    """View a dataset in napari"""
    click.echo(f"Reading file:\t {filename}")
    print_info(filename)

    reader = read_micromanager(filename)

    if positions == ():  # If empty, open all positions
        positions = range(reader.get_num_positions())
    positions = [int(x) for x in positions]

    v = napari.Viewer()
    v.text_overlay.visible = True
    v.text_overlay.color = "green"
    if layers == "position" or layers == "p":
        for position in positions:
            try:
                name = reader.stage_positions[position]["Label"]
            except:
                name = "Pos" + str(position)
            v.add_image(reader.get_zarr(position), name=name)
            v.layers[-1].reset_contrast_limits()
        v.dims.axis_labels = ("T", "C", "Z", "Y", "X")

        # Overlay the channel name
        def text_overlay():
            v.text_overlay.text = (
                f"Channel: {reader.channel_names[v.dims.current_step[1]]}"
            )

        v.dims.events.current_step.connect(text_overlay)
        text_overlay()

    elif layers == "channel" or layers == "c":
        print(
            "WARNING: sending channels to layers is more expensive than sending positions to layers. "
            "Try loading a small number of positions."
        )

        ptzyx = (len(positions),) + (reader.shape[0],) + reader.shape[2:]
        for channel in range(int(reader.channels)):
            temp_data = np.zeros(ptzyx)
            for k, position in enumerate(positions):
                temp_data[k] = reader.get_array(position)[:, channel, ...]
            v.add_image(temp_data, name=reader.channel_names[channel])
            v.layers[-1].reset_contrast_limits()
        v.dims.axis_labels = ("P", "T", "Z", "Y", "X")

    napari.run()
