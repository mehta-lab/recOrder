# bchhun, {2020-03-04}

"""
This file contains mappings between parameters and their corresponding GUI names

"""

DEFAULT_CONFIG = {
    # dataset
    'data_dir': '',
    'samples': '',
    'background': '',
    'positions': 'all',
    'z_slices': 'all',
    'timepoints': 'all',
    'processed_dir': '',
    'ROI': None,

    # processing general
    'output_channels': ['Brightfield', 'Retardance', 'Orientation', 'Polarization'],
    'circularity': 'rcp',
    'background_correction': 'None',
    'local_fit_order': 2,
    'flatfield_correction': False,
    'azimuth_offset': 0,
    'separate_positions': True,
    'n_slice_local_bg': '',
    'binning': 1,

    # phase - gpu
    'use_gpu': False,
    'gpu_id': 0,

    # phase - optics
    'pixel_size': None,
    'magnification': None,
    'NA_objective': None,
    'NA_condenser': None,
    'n_objective_media': None,
    'focus_zidx': None,

    # phase - 2D
    'phase_denoiser_2D': 'Tikhonov',
    'Tik_reg_abs_2D': 1E-6,
    'Tik_reg_ph_2D': 1E-6,
    'rho_2D': 1,
    'itr_2D': 50,
    'TV_reg_abs_2D': 1E-3,
    'TV_reg_ph_2D': 1E-5,

    # phase - 3D
    'phase_denoiser_3D': 'Tikhonov',
    'rho_3D': 1E-3,
    'itr_3D': 50,
    'Tik_reg_ph_3D': 1E-4,
    'TV_reg_ph_3D': 5E-5,

    'pad_z': 0,

    # plotting
    'normalize_color_images': True,
    'retardance_scaling': 1E3,
    'transmission_scaling': 1E4,
    'phase_2D_scaling': 1,
    'phase_3D_scaling': 1,
    'save_birefringence_fig': False,
    'save_stokes_fig': False,
    'save_polarization_fig': False,
    'save_micromanager_fig': False
}

GUI_TO_CONFIG = {

    # DATASET
    'le_data_dir': 'data_dir',
    'le_samples': 'samples',
    'le_background': 'background',
    'le_positions': 'positions',
    'le_z_slices': 'z_slices',
    'le_timepoints': 'timepoints',
    'le_processed_dir': 'processed_dir',
    'le_roi': 'ROI',

    # PROCESSING
    'le_output_channels': 'output_channels',
    'le_circularity': 'circularity',
    'le_background_correction': 'background_correction',
    'le_local_fit_order': 'local_fit_order',
    'le_flatfield_correction': 'flatfield_correction',
    'le_azimuth_offset': 'azimuth_offset',
    'le_separate_positions': 'separate_positions',
    'le_n_slice_local_bg': 'n_slice_local_bg',
    'le_binning': 'binning',

    # phase - gpu
    'rb_use_gpu': 'use_gpu',
    'le_gpu_id': 'gpu_id',

    # phase - optics
    'le_pixel_size': 'pixel_size',
    'le_magnification': 'magnification',
    'le_na_objective': 'NA_objective',
    'le_na_condensor': 'NA_condenser',
    'le_n_objective_media': 'n_objective_media',
    'le_focus_z_index': 'focus_zidx',

    # phase - 2D
    'cb_phase_denoiser_2d': 'phase_denoiser_2D',
    'le_tik_reg_abs_2d': 'Tik_reg_abs_2D',
    'le_tik_reg_ph_2d': 'Tik_reg_ph_2D',
    'le_tv_rho_2d': 'rho_2D',
    'le_tv_itr_2d': 'itr_2D',
    'le_tv_reg_abs': 'TV_reg_abs_2D',
    'le_tv_reg_ph': 'TV_reg_ph_2D',

    # phase - 3D
    'cb_phase_denoiser_3d': 'phase_denoiser_3D',
    'le_tv_rho_3d': 'rho_3D',
    'le_tv_itr_3d': 'itr_3D',
    'le_tik_reg_ph_3d': 'Tik_reg_ph_3D',
    'le_tv_reg_ph_3d': 'TV_reg_ph_3D',

    'le_pad_z': 'pad_z',

    # PLOTTING
    'le_normalize_color_images': 'normalize_color_images',
    'le_transmission_scaling': 'retardance_scaling',
    'le_retardance_scaling': 'transmission_scaling',
    'le_phase_2d_scaling': 'phase_2D_scaling',
    'le_phase_3d_scaling': 'phase_3D_scaling',
    'le_save_birefringence_fig': 'save_birefringence_fig',
    'le_save_stokes_fig': 'save_stokes_fig',
    'le_save_polarization_fig': 'save_polarization_fig',
    'le_save_micromanager_fig': 'save_micromanager_fig'
}