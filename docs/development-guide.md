# `recOrder` development guide

## Install `recOrder` for development
Install [anaconda](https://www.anaconda.com/products/distribution) and create a virtual environment  
```
conda create -y -n recOrder python=3.9
conda activate recOrder
```

Clone `recOrder`:
```
git clone https://github.com/mehta-lab/recOrder.git
```

Install `recOrder` in editable mode with development dependencies
```
cd recOrder
pip install -e ".[dev]"
```

## Set up your development environment

* TODO formatting/linting/precommit hooks/list of VScode plugins

## Run automated tests
From within the `recOrder` directory run:
```
pytest
```
Running `pytest` for the first time will download ~50 MB of test data from Zenodo, and subsequent runs will reuse the downloaded data.

## Run manual tests
Although many of `recOrder`'s tests are automated, many features require manual testing. The following is a summary of features that need to be tested manually before release:

* Install a compatible version of micromanager and check that `recOrder` can connect.
* Perform calibrations with and without an ROI; with and without a shutter configured in micromanager, in 4- and 5-state modes; and in MM-Voltage, MM-Retardance, and DAC modes (if the TriggerScope is available).  
* Test "Load Calibration" and "Calculate Extinction" buttons. 
* Test "Capture Background" button. 
* Test the "Acquire Birefringence" button on a background FOV. Does a background-corrected background acquisition give random orientations?
* Test the four "Acquire" buttons with varied combinations of 2D/3D, background correction settings, "Phase from BF" checkbox, and regularization parameters. 
* Use the data you collected to test "Offline" mode reconstructions with varied combinations of parameters.  

## Release checklist

TODO