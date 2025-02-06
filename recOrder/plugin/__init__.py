# qtpy defaults to PyQt5/PySide2 which can be present in upgraded environments
try:
    import qtpy
except RuntimeError as error:
    if type(error).__name__ == "QtBindingsNotFoundError":
        print("Please install a supported QtBindings PyQT or PySide")
    else:
        raise

if qtpy.PYQT5:
    raise RuntimeError(
        "Please remove PyQt5 from your environment with `pip uninstall PyQt5`"
    )
elif qtpy.PYSIDE2:
    raise RuntimeError(
        "Please remove PySide2 from your environment with `pip uninstall PySide2`"
    )
