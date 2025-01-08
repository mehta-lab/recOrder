# qtpy defaults to PyQt5/PySide2 which can be present in upgraded environments
import qtpy

if qtpy.PYQT5:
    raise RuntimeError(
        """
        The current environment uses PyQt5, which is not supported by recOrder.
        If you are in an environment with an existing napari installation, 
        use `pip install napari[pyqt6]` to install PyQt6 then try again.
        """
    )
elif qtpy.PYSIDE2:
    raise RuntimeError(
        """
        The current environment uses PySide2, which is not supported by recOrder.
        If you are in an environment with an existing napari installation, 
        use `pip install napari[pyside6_experimental]` to install PySide6 then try again.
        """
    )
