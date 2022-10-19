from unittest.mock import MagicMock, Mock
from numpy.random import randint

# tested components
from recOrder.io.core_functions import *


# dynamic range
TIFF_I_MAX = 2**16
# image size
IMAGE_WIDTH = randint(1, 2**12)
IMAGE_HEIGHT = randint(1, 2**12)
PIXEL_COUNT = IMAGE_HEIGHT * IMAGE_WIDTH
# serialized image from the pycromanager bridge
SERIAL_IMAGE = randint(0, TIFF_I_MAX, size=(PIXEL_COUNT))


def get_mmcore_mock():
    """Creates a mock for the `pycromanager.Core` object.

    Returns
    -------
    MagicMock
        MMCore mock object
    """
    mmcore_mock_config = {"getImage": Mock(return_value=SERIAL_IMAGE)}
    return MagicMock(**mmcore_mock_config)


def get_snap_manager_mock():
    """Creates a mock for the pycromanager remote Snap Live Window Manager object.

    Returns
    -------
    MagicMock
        Mock object for `org.micromanager.internal.SnapLiveManager` via pycromanager
    """
    sm = MagicMock()
    get_snap_mocks = {
        "getHeight": Mock(return_value=IMAGE_HEIGHT),
        "getWidth": Mock(return_value=IMAGE_WIDTH),
        "getRawPixels": Mock(return_value=SERIAL_IMAGE),
    }
    # TODO: break down these JAVA call stack chains for maintainability
    sm.getDisplay.return_value.getDisplayedImages.return_value.get = Mock(
        # return image object mock with H, W, and pixel values
        return_value=Mock(**get_snap_mocks)
    )
    sm.getDisplay.return_value.getImagePlus.return_value.getStatistics = Mock(
        # return statistics object mock with the attribute "umean"
        return_value=Mock(umean=SERIAL_IMAGE.mean())
    )
    return sm


def is_int(data):
    """Check if the data type is integer.

    Parameters
    ----------
    data

    Returns
    -------
    bool
        True if the data type is any integer type.
    """
    return np.issubdtype(data.dtype, np.integer)


def test_snap_image():
    """Test `recOrder.io.core_functions.snap_image`."""
    mmc = get_mmcore_mock()
    image = snap_image(mmc)
    mmc.snapImage.assert_called_once()
    mmc.getImage.assert_called_once()
    assert is_int(image), image.dtype
    assert image.shape == (PIXEL_COUNT,), image.shape


def test_suspend_live_mm():
    """Test `recOrder.io.core_functions.suspend_live_mm`."""
    snap_manager = get_snap_manager_mock()
    with suspend_live_sm(snap_manager) as sm:
        sm.setSuspended.assert_called_once_with(True)
    snap_manager.setSuspended.assert_called_with(False)


def test_snap_and_get_image():
    """Test `recOrder.io.core_functions.snap_and_get_image`."""
    sm = get_snap_manager_mock()
    image = snap_and_get_image(sm)
    assert is_int(image), image.dtype
    assert image.shape == (IMAGE_HEIGHT, IMAGE_WIDTH), image.shape


def test_snap_and_average():
    """Test `recOrder.io.core_functions.snap_and_average`."""
    sm = get_snap_manager_mock()
    mean = snap_and_average(sm)
    assert mean == SERIAL_IMAGE.mean(), mean
