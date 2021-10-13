from napari_plugin_engine import napari_hook_implementation
from recOrder.plugin.widget.calibration_plugin_widget import recOrder_Widget

"""
each of these GUI files is generated by qtdesigner.
To generate a new .py file from the designer's .ui file, type this in terminal

pyuic5 -x <.ui input file> -o <.py output file>

"""


@napari_hook_implementation
def napari_experimental_provide_dock_widget():
    # you can return either a single widget, or a sequence of widgets
    # each widget is accessible as a new plugin that stacks in the side panel
    return [recOrder_Widget, {'name': 'recOrder'}]