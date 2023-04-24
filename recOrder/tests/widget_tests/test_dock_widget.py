from recOrder.plugin.main_widget import MainWidget
import napari


def test_dock_widget(make_napari_viewer, qtbot):
    viewer: napari.Viewer = make_napari_viewer()
    assert viewer
