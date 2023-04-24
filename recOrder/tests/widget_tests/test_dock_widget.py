from recOrder.plugin.main_widget import MainWidget
import napari


def test_dock_widget(make_napari_viewer, qtbot):
    viewer: napari.Viewer = make_napari_viewer()
    widget = MainWidget(viewer)
    viewer.window.add_dock_widget(widget)
    assert "recOrder" in list(viewer._window._dock_widgets.keys())[0]
    widget.deleteLater()
    qtbot.wait(50)
