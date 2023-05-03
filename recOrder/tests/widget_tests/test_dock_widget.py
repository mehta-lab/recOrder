import sys
import os

import pytest
from napari.viewer import ViewerModel

from recOrder.plugin.main_widget import MainWidget


# skip this for GitHub actions Linux runner
@pytest.mark.skipif("linux" in sys.platform and os.environ.get("CI"))
def test_dock_widget(make_napari_viewer):
    viewer: ViewerModel = make_napari_viewer()
    viewer.window.add_dock_widget(MainWidget(viewer))
    assert "recOrder" in list(viewer._window._dock_widgets.keys())[0]
