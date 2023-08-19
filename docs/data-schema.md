# Data schema

This document defines the standard for data acquired with `recOrder`.

## Raw directory organization

Currently, we structure raw data in the following hierarchy:

```text
working_directory/                      # commonly YYYY_MM_DD_exp_name, but not enforced
├── calibration_metadata.txt        
│   ...
├── calibration_metadata<i>.txt         # i calibration repeats
│
├── BG
│   ...
├── BG_<j>                              # j background repeats
│   ├── background.zarr             
│   ├── calibration_metadata.txt        # duplicated for each BG
│   ├── gui_state.yml               
│   ├── reconstruction.zarr
│   ├── reconstruction_settings.yml     # for use with `recorder reconstruct`
│   └── transfer_function.zarr          # for use with `recorder apply-inv-tf`
│
├── <acq_name_0>_recOrderPluginSnap_0   
├── <acq_name_0>_recOrderPluginSnap_1 
│   ├── <acq_name_0>_RawPolDataSnap.zarr
│   ├── gui_state.yml
│   ├── reconstruction.zarr
│   ├── reconstruction_settings.yml
│   └── transfer_function.zarr
│   ...
├── <acq_name_0>_recOrderPluginSnap_<k> # k repeats with the first acquisition name
│   ├── <acq_name_0>_RawBFDataSnap.zarr # note mixed Pol and BF data with same acquisition name
│   ├── gui_state.yml
│   ├── reconstruction.zarr
│   ├── reconstruction_settings.yml
│   └── transfer_function.zarr
│   ...
│
├── <acq_name_l>_recOrderPluginSnap_0   # l different acquisition names
│   ...
├── <acq_name_l>_recOrderPluginSnap_<m> $ m repeats for this acquisition name
    ├── <acq_name_l>_RawBFDataSnap.zarr 
    ├── gui_state.yml
    ├── reconstruction.zarr
    ├── reconstruction_settings.yml
    └── transfer_function.zarr
```