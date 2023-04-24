from recOrder.plugin.main_widget import MainWidget
# import napari
from napari.viewer import ViewerModel


def test_dock_widget(make_napari_viewer):
    viewer: ViewerModel = make_napari_viewer()
    viewer.window.add_dock_widget(MainWidget(viewer))
    assert "recOrder" in list(viewer._window._dock_widgets.keys())[0]
