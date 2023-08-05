# Microscope Installation Guide

This guide will walk through a complete recOrder installation consisting of:
1. Checking pre-requisites for compatibility. 
2. Installing Meadowlark DS5020 and liquid crystals.
3. Installing and launching the latest stable version of `recOrder` via `pip`. 
4. Installing a compatible version of `MicroManager` and LC device drivers.
5. Connecting `recOrder` to `MicroManager` via a `pycromanager` connection.

## Compatibility Summary 
Before you start you will need to confirm that your system is compatible with the following software:

| Software | Version |  
| :--- | :--- |
| `recOrder` | 0.3.x |
| OS | Windows 10 | 
| Micromanager version | [2022-09-20 (160 MB)](https://download.micro-manager.org/nightly/2.0/Windows/MMSetup_64bit_2.0.1_20220920.exe) | 
| Meadowlark drivers | [recOrder-0.3.0-device-drivers.zip (112 kB)](https://github.com/mehta-lab/recOrder/releases/download/0.3.0/recOrder-0.3.0-device-drivers.zip) | 
| Meadowlark PC software version | 1.04 | 
| Meadowlark controller firmware version | >=1.04 | 

## Install Meadowlark DS5020 and liquid crystals

Start by installing the Meadowlark DS5020 and liquid crystals using the software on the USB stick provided by Meadowlark. You will need to install the USB drivers and CellDrive5000.

**Check your installation's versions** by opening CellDrive5000 and double clicking the Meadowlark Optics logo. Confirm that **"PC software version = 1.04" and "Controller firmware version >= 1.04".** 

If you need to change your PC software version, follow these steps:
- From "Add and remove programs", remove CellDrive5000 and "National Instruments Software".
- From "Device manager", open the "Meadowlark Optics" group, right click `mlousb`, click "Uninstall device", check "Delete the driver software for this device", and click "Uninstall". Uninstall `Meadowlark Optics D5020 LC Driver` following the same steps.
- Using the USB stick provided by Meadowlark, reinstall the USB drivers and CellDrive5000. 

## Install recOrder software

(Optional but recommended) install [anaconda](https://www.anaconda.com/products/distribution) and create a virtual environment  
```
conda create -y -n recOrder python=3.9
conda activate recOrder
```

Install `recOrder`:
```
pip install recOrder-napari
```
Check your installation:
```
napari -w recOrder-napari
```
should launch napari (may take 15 seconds on a fresh installation) with the recOrder plugin in "Offline" mode. 
 
## Install and configure `Micromanager`

Install `Micromanager 2.0` nightly build `20220920` (https://micro-manager.org/Micro-Manager_Nightly_Builds). 

**Note:** We have tested recOrder with `20220920`, but most features will work with newer builds. We recommend testing a minimal installation with `20220920` before testing with a different nightly build or additional device drivers. 

Before launching `Micromanager`, [download the Meadowlark device adapters and calibration files](https://github.com/mehta-lab/recOrder/releases/download/0.3.0/recOrder-0.3.0-device-drivers.zip) and place these three unzipped files into your `Micromanager` folder (likely `C:\Program Files\Micro-Manager` or similar). 

Launch `Micromanager`, open `Devices > Hardware Configuration Wizard...`, and add the `MeadowlarkLcOpenSource` device to your configuration. Confirm your installation by opening `Devices > Device Property Browser...` and confirming that `MeadowlarkLCOpenSource` properties appear. 

### Option 1 (recommended): Voltage-mode calibration installation
 Create a new channel group and add the `MeadowlarkLcOpenSource-Voltage (V) LC-A` and `MeadowlarkLcOpenSource-Voltage (V) LC-B` properties. 

![](https://github.com/mehta-lab/recOrder/blob/main/docs/images/create_group_voltage.png)

Add 5 presets to this group named `State0`, `State1`, `State2`, `State3`, and `State4`. You can set random voltages to add these presets, and `recOrder` will calibrate and set these voltages later.

![](https://github.com/mehta-lab/recOrder/blob/main/docs/images/create_preset_voltage.png)

### Option 2 (soon deprecated): retardance mode calibration installation

Create a new channel group and add the property `MeadowlarkLcOpenSource-String send to -`. 

![](https://github.com/mehta-lab/recOrder/blob/main/docs/images/create_group.png)

Add 5 presets to this group named `State0`, `State1`, `State2`, `State3`, and `State4` and set the corresponding preset values to `state0`, `state1`, `state2`, `state3`, `state4` in the `MeadowlarkLcOpenSource-String send to –`* property. 

![](https://github.com/mehta-lab/recOrder/blob/main/docs/images/create_preset.png)

### (Optional) Enable "Phase From BF" acquisition

If you would like to reconstruct phase from brightfield, add a `Micromanager` preset with brightfield properties (e.g. moving the polarization analyzer out the light path) and give the preset a name that contains one of the following case-insensitive keywords:

`["bf", "brightfield", "bright", "labelfree", "label-free", "lf", "label", "phase, "ph"]`

In `recOrder` you can select this preset using the `Acquisition Settings > BF Channel` dropdown menu. 

### Enable port access

Finally, enable port access so that `Micromanager` can communicate with recOrder through the `pycromanager` bridge. To do so open `Micromanager` and navigate to `Tools > Options` and check the box that says `Run server on port 4827`

![](https://github.com/mehta-lab/recOrder/blob/main/docs/images/run_port.png)

## Connect `recOrder` to `Micromanager`

From the `recOrder` window, click `Switch to Online`. If you see `Success`, your installation is complete and you can [proceed to the napari plugin guide](./napari-plugin-guide.md). 

If you you see `Failed`, check that `Micromanager` is open, check that you've enabled `Run server on port 4827`. If the connection continues to fail, report an issue with your stack trace for support. 
