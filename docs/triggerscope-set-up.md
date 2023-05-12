# Setting up the Triggerscope

This guide will walk through setting up the triggerscope (DAC device) to externally drive the LC's for hardware sequencing.

---
## Table of Contents
- [Setting up the Triggerscope](#setting-up-the-triggerscope)
  - [Table of Contents](#table-of-contents)
  - [Triggerscope](#triggerscope)
  - [Setup the Triggerscope with micromanager](#setup-the-triggerscope-with-micromanager)
    - [Plugin the triggerscope](#plugin-the-triggerscope)
    - [Remove/Check the Meadolwark device is not in config file](#removecheck-the-meadolwark-device-is-not-in-config-file)
  - [Connect the Meadowlark LC control box to the Triggerscope](#connect-the-meadowlark-lc-control-box-to-the-triggerscope)
  - [Set the LC's to `external mode`](#set-the-lcs-to-external-mode)
  - [Launch micromanager with the new config file](#launch-micromanager-with-the-new-config-file)
  - [FAQ / Troubleshooting](#faq--troubleshooting)

---
## Triggerscope
The Triggerscope is ...
The triggerscope replaces the Meadowlark control box and allows one to drive the LC's through external analog inputs. 

Check the Triggerscope Firmware
** references to triggescope setup

## Setup the Triggerscope with micromanager
** Confirm instructions on setup.

Launch Micromanager, open `Devices > Hardware Configuration Wizard...`, and add the `Triggerscope  Hub` device to your configuration.

Confirm your installation by opening Devices > Device Property Browser... and confirming that `Triggerscope DAC` properties appear.


### Plugin the triggerscope
- Connect the triggerscope via USB
- Connect the external power supply to the triggerscope
- Flip on the switch

### Remove/Check the Meadolwark device is not in config file


## Connect the Meadowlark LC control box to the Triggerscope
Using the connectors on the LC control box, connect the LC to
Make sure to note which LC (i.e LCA and LCB) is connected to Triggerscope DAC ##.

** missing pictures for the connectors

## Set the LC's to `external mode`


## Launch micromanager with the new config file


## FAQ / Troubleshooting
- The LC's are not changing even if I sweep the voltages on the micromanager properties. 
  - Make sure the LC controller box is connected to the computer via USB
  - Open CellDrive and set the LCs in ["external mode"](#set-the-lcs-to-external-mode)
- When I change the triggerscope voltages from the MM device property manager, MM crashes
  - [Check](#plugin-the-triggerscope) that the Triggerscope is connected via USB and connected to it's power supply through the barrel connector. 
  

