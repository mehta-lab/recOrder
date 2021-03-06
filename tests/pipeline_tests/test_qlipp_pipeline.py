import pytest
from recOrder.io.config_reader import ConfigReader
from recOrder.pipelines.pipeline_manager import PipelineManager
from recOrder.pipelines.qlipp_pipeline import qlipp_pipeline
from waveorder.io.writer import WaveorderWriter
from recOrder.compute.qlipp_compute import reconstruct_qlipp_stokes, reconstruct_qlipp_birefringence, \
    reconstruct_qlipp_phase3D, reconstruct_qlipp_phase2D
from os.path import dirname, abspath
import numpy as np
import os
import zarr

def test_pipeline_daemon_initiate(setup_test_data, setup_data_save_folder):

    folder, data = setup_test_data
    save_folder = setup_data_save_folder

    path_to_config = os.path.join(dirname(dirname(abspath(__file__))), 'test_configs/config_qlipp_full_pytest.yml')
    config = ConfigReader(path_to_config, data_dir=data, save_dir=save_folder)

    manager = PipelineManager(config)
    assert(manager.config is not None)
    assert(manager.data is not None)
    assert(manager.data.get_num_positions()*manager.data.frames == len(manager.pt_set))
    assert(manager.pipeline is not None)
    assert(isinstance(manager.pipeline, qlipp_pipeline))

def test_qlipp_pipeline_initiate(setup_test_data, setup_data_save_folder):
    folder, data = setup_test_data
    save_folder = setup_data_save_folder

    path_to_config = os.path.join(dirname(dirname(abspath(__file__))), 'test_configs/config_qlipp_full_pytest.yml')
    config = ConfigReader(path_to_config, data_dir=data, save_dir=save_folder)

    manager = PipelineManager(config)

    pipeline = manager.pipeline
    assert(pipeline.config == manager.config)
    assert(pipeline.data == manager.data)
    assert(pipeline.config.data_save_name == manager.pipeline.name)
    assert(pipeline.t == manager.num_t)
    assert(pipeline.mode == '3D')
    assert(pipeline.no_birefringence == False)
    assert(pipeline.slices == manager.data.slices)
    assert(pipeline.img_dim == (manager.data.height, manager.data.width, manager.data.slices))
    assert(pipeline.chan_names == manager.data.channel_names)
    assert(isinstance(pipeline.calib_meta, dict))
    assert(pipeline.bg_path == manager.config.background)

    #todo: assert bg dimensions when bug is fixed in calibration

    # assert(pipeline.bg_roi == (0, 0, daemon.data.width, daemon.data.height))
    assert(pipeline.s0_idx == 0)
    assert(pipeline.s1_idx == 1)
    assert(pipeline.s2_idx == 2)
    assert(pipeline.s3_idx == 3)
    assert(pipeline.fluor_idxs == [])
    assert(pipeline.data_shape == (manager.data.frames, manager.data.channels,
                                   manager.data.slices, manager.data.height, manager.data.width))
    assert(pipeline.chunk_size == (1, 1, 1, manager.data.height, manager.data.width))
    assert(isinstance(pipeline.writer, WaveorderWriter))
    assert(pipeline.reconstructor is not None)
    assert(pipeline.bg_stokes is not None)

def test_pipeline_daemon_run(setup_test_data, setup_data_save_folder):

    folder, data = setup_test_data
    save_folder = setup_data_save_folder

    path_to_config = os.path.join(dirname(dirname(abspath(__file__))), 'test_configs/config_qlipp_full_pytest.yml')
    config = ConfigReader(path_to_config, data_dir=data, save_dir=save_folder)

    manager = PipelineManager(config)
    manager.run()

    store = zarr.open(os.path.join(save_folder, '2T_3P_81Z_231Y_498X_Kazansky_2.zarr'))
    array = store['Pos_000.zarr']['physical_data']['array']

    assert(store.attrs.asdict() == config.yaml_dict)
    assert(store['Pos_000.zarr'])
    assert(store['Pos_001.zarr'])
    assert(store['Pos_002.zarr'])
    assert(array.shape == (2, 4, 81, manager.data.height, manager.data.width))

def test_3D_reconstruction(setup_test_data, setup_data_save_folder):
    folder, data = setup_test_data
    save_folder = setup_data_save_folder

    path_to_config = os.path.join(dirname(dirname(abspath(__file__))), 'test_configs/config_qlipp_full_recon_pytest.yml')
    config = ConfigReader(path_to_config, data_dir=data, save_dir=save_folder)

    manager = PipelineManager(config)
    assert(manager.pipeline.mode == '3D')
    manager.run()

    pos, t, z = 1, 0, 40
    data = manager.data.get_array(pos)
    recon = manager.pipeline.reconstructor

    stokes = reconstruct_qlipp_stokes(data[t], recon, manager.pipeline.bg_stokes)
    birefringence = reconstruct_qlipp_birefringence(stokes, recon)
    phase3D = reconstruct_qlipp_phase3D(np.transpose(stokes[:, 0], (1, 2, 0)),recon,
                                                method=config.phase_denoiser_3D,
                                                reg_re=config.Tik_reg_ph_3D, rho=config.rho_3D,
                                                lambda_re=config.TV_reg_ph_3D, itr=config.itr_3D)

    store = zarr.open(os.path.join(save_folder, '2T_3P_81Z_231Y_498X_Kazansky_2.zarr'))
    array = store['Pos_001.zarr']['physical_data']['array']

    # Check Shape
    assert(array.shape == (1, len(config.output_channels), 81, 231, 498))

    # Check Stokes
    assert(np.sum(np.abs(stokes[z, 0] - array[0, 4, z]) ** 2) / np.sum(np.abs(stokes[z, 0])**2) < 0.1)
    assert(np.sum(np.abs(stokes[z, 1] - array[0, 5, z]) ** 2) / np.sum(np.abs(stokes[z, 1])**2) < 0.1)
    assert(np.sum(np.abs(stokes[z, 2] - array[0, 6, z]) ** 2) / np.sum(np.abs(stokes[z, 2])**2) < 0.1)
    assert(np.sum(np.abs(stokes[z, 3] - array[0, 7, z]) ** 2) / np.sum(np.abs(stokes[z, 3])**2) < 0.1)

    # Check Birefringence
    assert(np.sum(np.abs((birefringence[0, z]/(2 * np.pi)*config.wavelength) - array[0, 0, z]) ** 2)
           / np.sum(np.abs(birefringence[0, z]/(2 * np.pi)*config.wavelength)**2) < 0.1)
    assert (np.sum(np.abs(birefringence[1, z] - array[0, 1, z]) ** 2) / np.sum(np.abs(birefringence[1, z])**2) < 0.1)
    assert (np.sum(np.abs(birefringence[2, z] - array[0, 2, z]) ** 2) / np.sum(np.abs(birefringence[2, z])**2) < 0.1)

    # Check Phase
    assert (np.sum(np.abs(phase3D[z] - array[0, 3, z]) ** 2) / np.sum(np.abs(phase3D[z])**2) < 0.1)


def test_2D_reconstruction(setup_test_data, setup_data_save_folder):
    folder, data = setup_test_data
    save_folder = setup_data_save_folder

    path_to_config = os.path.join(dirname(dirname(abspath(__file__))), 'test_configs/config_qlipp_2D_pytest.yml')
    config = ConfigReader(path_to_config, data_dir=data, save_dir=save_folder)

    manager = PipelineManager(config)
    assert(manager.pipeline.mode == '2D')
    manager.run()

    pos, t, z = 1, 0, manager.pipeline.focus_slice
    data = manager.data.get_array(pos)
    recon = manager.pipeline.reconstructor

    stokes = reconstruct_qlipp_stokes(data[t], recon, manager.pipeline.bg_stokes)
    birefringence = reconstruct_qlipp_birefringence(stokes[z], recon)
    phase2D = reconstruct_qlipp_phase2D(np.transpose(stokes[:, 0], (1, 2, 0)), recon,
                                        method=config.phase_denoiser_2D, reg_p=config.Tik_reg_ph_2D,
                                        rho=config.rho_2D, lambda_p=config.TV_reg_ph_2D, itr=config.itr_2D)
    store = zarr.open(os.path.join(save_folder, '2T_3P_81Z_231Y_498X_Kazansky_2.zarr'))
    array = store['Pos_001.zarr']['physical_data']['array']

    # Check Shapes
    assert(array.shape == (1, len(config.output_channels), 1, 231, 498))

    # Check Stokes
    assert(np.sum(np.abs(stokes[z, 0] - array[0, 4, 0]) ** 2) / np.sum(np.abs(stokes[z, 0]))**2 < 0.1)
    assert(np.sum(np.abs(stokes[z, 1] - array[0, 5, 0]) ** 2) / np.sum(np.abs(stokes[z, 1]))**2 < 0.1)
    assert(np.sum(np.abs(stokes[z, 2] - array[0, 6, 0]) ** 2) / np.sum(np.abs(stokes[z, 2]))**2 < 0.1)
    assert(np.sum(np.abs(stokes[z, 3] - array[0, 7, 0]) ** 2) / np.sum(np.abs(stokes[z, 3]))**2 < 0.1)

    # Check Birefringence
    assert(np.sum(np.abs((birefringence[0, 0]/(2 * np.pi)*config.wavelength) - array[0, 0, 0]) ** 2)
           / np.sum(np.abs(birefringence[0, 0]/(2 * np.pi)*config.wavelength)**2) < 0.1)
    assert (np.sum(np.abs(birefringence[1, 0] - array[0, 1, 0]) ** 2) / np.sum(np.abs(birefringence[1, 0])**2) < 0.1)
    assert (np.sum(np.abs(birefringence[2, 0] - array[0, 2, 0]) ** 2) / np.sum(np.abs(birefringence[2, 0])**2) < 0.1)

    # Check Phase
    assert (np.sum(np.abs(phase2D - array[0, 3, 0]) ** 2) / np.sum(np.abs(phase2D)**2) < 0.1)

#TODO: Add Tests for Pre/Post Processing?
#TODO: Add tests/test data for 5 state reconstruction