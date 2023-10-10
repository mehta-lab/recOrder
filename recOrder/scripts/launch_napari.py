import napari
from recOrder.plugin._widget import MainWidget


def main():
    viewer = napari.Viewer()
    viewer.window.add_dock_widget(MainWidget(viewer))
    napari.run()


if __name__ == "__main__":
    main()
