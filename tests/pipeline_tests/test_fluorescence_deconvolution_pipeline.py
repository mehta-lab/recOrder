import pytest
from recOrder.io.config_reader import ConfigReader
from recOrder.pipelines.pipeline_manager import PipelineManager
from recOrder.pipelines.fluor_deconv import FluorescenceDeconvolution
from waveorder.io.writer import WaveorderWriter
from recOrder.compute.fluorescence_deconvolution import calculate_background, deconvolve_fluorescence_3D, \
    deconvolve_fluorescence_2D

from os.path import dirname, abspath
import numpy as np
import os
import zarr

def test_pipeline_manager_initiate(setup_test_data_zarr, setup_data_save_folder):

    folder, data = setup_test_data_zarr
    save_folder = setup_data_save_folder

    path_to_config = os.path.join(dirname(dirname(abspath(__file__))),
                                  'test_configs/fluor_deconv/config_fluor_full_pytest.yml')
    config = ConfigReader(path_to_config, data_dir=data, save_dir=save_folder)

    manager = PipelineManager(config)
    assert(manager.config is not None)
    assert(manager.data is not None)
    assert(manager.data.get_num_positions()*manager.data.frames == len(manager.pt_set))
    assert(manager.pipeline is not None)
    assert(isinstance(manager.pipeline, FluorescenceDeconvolution))

def test_fluor_decon_pipeline_initiate(setup_test_data_zarr, setup_data_save_folder):
    folder, data = setup_test_data_zarr
    save_folder = setup_data_save_folder

    path_to_config = os.path.join(dirname(dirname(abspath(__file__))),
                                  'test_configs/fluor_deconv/config_fluor_full_pytest.yml')
    config = ConfigReader(path_to_config, data_dir=data, save_dir=save_folder)

    manager = PipelineManager(config)

    pipeline = manager.pipeline
    assert(pipeline.config == manager.config)
    assert(pipeline.data == manager.data)
    assert(pipeline.t == manager.num_t)
    assert(pipeline.mode == '3D')
    assert(pipeline.slices == manager.data.slices)
    assert(pipeline.img_dim == (manager.data.height, manager.data.width, manager.data.slices))
    assert(pipeline.fluor_idxs == [0, 1])
    assert(pipeline.data_shape == (manager.data.frames, len(config.output_channels),
                                   manager.data.slices, manager.data.height, manager.data.width))
    assert(pipeline.chunk_size == (1, 1, 1, manager.data.height, manager.data.width))
    assert(isinstance(pipeline.writer, WaveorderWriter))
    assert(pipeline.reconstructor is not None)

def test_pipeline_manager_run(setup_test_data_zarr, setup_data_save_folder):

    folder, data = setup_test_data_zarr
    save_folder = setup_data_save_folder

    path_to_config = os.path.join(dirname(dirname(abspath(__file__))),
                                  'test_configs/fluor_deconv/config_fluor_full_pytest.yml')
    config = ConfigReader(path_to_config, data_dir=data, save_dir=save_folder)

    manager = PipelineManager(config)
    manager.run()

    store = zarr.open(os.path.join(save_folder, '2T_3P_81Z_231Y_498X_Kazansky.zarr'))
    array = store['Row_0']['Col_0']['Pos_000']['array']

    assert (store.attrs.asdict()['Config'] == config.yaml_dict)
    assert (store['Row_0']['Col_0']['Pos_000'])
    assert (store['Row_0']['Col_1']['Pos_001'])
    assert (store['Row_0']['Col_2']['Pos_002'])
    assert (array.shape == (2, 2, 81, manager.data.height, manager.data.width))

def test_3D_reconstruction(setup_test_data_zarr, setup_data_save_folder):
    folder, data = setup_test_data_zarr
    save_folder = setup_data_save_folder

    path_to_config = os.path.join(dirname(dirname(abspath(__file__))),
                                  'test_configs/fluor_deconv/config_fluor_3D_pytest.yml')
    config = ConfigReader(path_to_config, data_dir=data, save_dir=save_folder)

    manager = PipelineManager(config)
    assert(manager.pipeline.mode == '3D')
    manager.run()

    pos, t, z = 1, 0, 40
    data = manager.data.get_array(pos)
    bg_level = calculate_background(data[t, 0, manager.data.slices // 2])
    recon = manager.pipeline.reconstructor

    print(f'BG LEVEL: {bg_level}')
    fluor3D = deconvolve_fluorescence_3D(data[t, 0], recon, bg_level, [config.reg])
    fluor3D = np.transpose(fluor3D, (-1, -3, -2))

    store = zarr.open(os.path.join(save_folder, '2T_3P_81Z_231Y_498X_Kazansky.zarr'), 'r')
    array = store['Row_0']['Col_1']['Pos_001']['array']

    # Check Shape
    assert(array.shape == (1, len(config.output_channels), 81, 231, 498))

    # Check deconvolved fluor
    assert (np.sum(np.abs(fluor3D[z] - array[0, 0, z]) ** 2) / np.sum(np.abs(fluor3D[z])**2) < 0.1)

def test_2D_reconstruction(setup_test_data_zarr, setup_data_save_folder):
    folder, data = setup_test_data_zarr
    save_folder = setup_data_save_folder

    path_to_config = os.path.join(dirname(dirname(abspath(__file__))),
                                  'test_configs/fluor_deconv/config_fluor_2D_pytest.yml')
    config = ConfigReader(path_to_config, data_dir=data, save_dir=save_folder)

    manager = PipelineManager(config)
    assert(manager.pipeline.slices == 1)
    assert(manager.pipeline.mode == '2D')
    manager.run()

    pos, t, z = 1, 0, 40
    data = manager.data.get_array(pos)
    bg_level = calculate_background(data[t, 0, z])
    recon = manager.pipeline.reconstructor

    fluor2D = deconvolve_fluorescence_2D(data[t, 0, z], recon, bg_level, reg=[config.reg])
    store = zarr.open(os.path.join(save_folder, '2T_3P_81Z_231Y_498X_Kazansky.zarr'), 'r')
    array = store['Row_0']['Col_1']['Pos_001']['array']

    # Check Shapes
    assert(array.shape == (1, len(config.output_channels), 1, 231, 498))

    # Check Deconvolved Fluor
    assert (np.sum(np.abs(fluor2D - array[0, 0, 0]) ** 2) / np.sum(np.abs(fluor2D)**2) < 0.1)


def test_deconvolution_and_registration(setup_test_data_zarr, setup_data_save_folder):

    folder, data = setup_test_data_zarr
    save_folder = setup_data_save_folder

    path_to_config = os.path.join(dirname(dirname(abspath(__file__))),
                                  'test_configs/fluor_deconv/config_fluor_full_registration_pytest.yml')
    config = ConfigReader(path_to_config, data_dir=data, save_dir=save_folder)

    manager = PipelineManager(config)
    manager.run()

    pos, t, z = 1, 0, manager.data.slices // 2
    data = manager.data.get_array(pos)
    recon = manager.pipeline.reconstructor

    data_decon = np.asarray([data[t, 0], data[t, 1]])
    bg_level = calculate_background(data_decon[:, z])
    fluor3D = deconvolve_fluorescence_3D(data_decon, recon, bg_level, reg=[config.reg]*2)
    fluor3D = np.transpose(fluor3D, (-4, -1, -3, -2))

    store = zarr.open(os.path.join(save_folder, '2T_3P_81Z_231Y_498X_Kazansky.zarr'), 'r')
    array = store['Row_0']['Col_1']['Pos_001']['array']

    # Check Registration - Chan0
    assert(np.sum(np.abs(array[0, 0, z, 100:, 100:] - fluor3D[0, z, 0:-100, 0:-100])**2)
           / np.sum(np.abs(array[0, 0, z, 100:, 100:])**2) < 0.1)
    assert(np.mean(array[0, 0, z, 0:100, 0:100]) == 0.0)

    # Check Registration - Chan1
    assert(np.sum(np.abs(array[0, 1, z, 100:, 100:] - fluor3D[1, z, 0:-100, 0:-100])**2)
           / np.sum(np.abs(array[0, 1, z, 100:, 100:])**2) < 0.1)
    assert(np.mean(array[0, 1, z, 0:100, 0:100]) == 0.0)

    # Check Registration - Chan2
    assert(np.sum(np.abs(array[0, 2, z, 100:, 100:] - data[t, 2, z, 0:-100, 0:-100])**2)
           / np.sum(np.abs(array[0, 2, z, 100:, 100:])**2) < 0.1)
    assert(np.mean(array[0, 2, z, 0:100, 0:100]) == 0.0)