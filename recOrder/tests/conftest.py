import pytest
import shutil
import os
from wget import download


@pytest.fixture(scope="session")
def setup_test_data():
    # create /pytest_temp/ and /pytest_temp/rawdata/ folders,
    temp_folder = os.path.join(os.getcwd(), "pytest_temp")
    test_data = os.path.join(temp_folder, "test_data")
    if not os.path.isdir(temp_folder):
        os.mkdir(temp_folder)
        print("\nsetting up temp folder")
    if not os.path.isdir(test_data):
        os.mkdir(test_data)

    #  download data to /pytest_temp/ folder if it doesn't already exist
    url = "https://zenodo.org/record/6983916/files/recOrder_test_data.zip?download=1"
    output = os.path.join(test_data, "recOrder_test_Data.zip")
    if not os.listdir(test_data):
        print("Downloading test files...")
        download(url, out=output)
        shutil.unpack_archive(output, extract_dir=test_data)

    yield test_data


@pytest.fixture()
def get_ometiff_data_dir(setup_test_data):
    test_data = setup_test_data

    ometiff_data = os.path.join(
        test_data,
        "2022_08_04_recOrder_pytest_20x_04NA",
        "2T_3P_16Z_128Y_256X_Kazansky_1",
    )

    return test_data, ometiff_data


@pytest.fixture()
def get_zarr_data_dir(setup_test_data):
    test_data = setup_test_data

    zarr_data = os.path.join(
        test_data,
        "2022_08_04_recOrder_pytest_20x_04NA_zarr",
        "2T_3P_16Z_128Y_256X_Kazansky.zarr",
    )

    return test_data, zarr_data


@pytest.fixture()
def get_bf_data_dir(setup_test_data):
    test_data = setup_test_data

    bf_data = os.path.join(
        test_data,
        "2022_08_04_recOrder_pytest_20x_04NA_BF",
        "2T_3P_16Z_128Y_256X_Kazansky_BF_1",
    )

    return test_data, bf_data


@pytest.fixture()
def get_pycromanager_data_dir(setup_test_data):
    test_data = setup_test_data

    pm_data = os.path.join(test_data, "mm2.0-20210713_pm0.13.2_2p_3t_2c_7z_1")

    return test_data, pm_data


# create /pytest_temp/data_save folder for each test then delete when test is done
@pytest.fixture(scope="function")
def setup_data_save_folder():
    temp_folder = os.path.join(os.getcwd(), "pytest_temp")
    data_save_folder = os.path.join(temp_folder, "data_save")
    if not os.path.isdir(data_save_folder):
        os.mkdir(data_save_folder)
        print("\nsetting up data_save folder")

    yield data_save_folder

    try:
        # remove temp folder
        shutil.rmtree(data_save_folder)
    except OSError as e:
        print(f"Error while deleting temp folder: {e.strerror}")
