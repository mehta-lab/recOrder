# Setting up the Triggerscope

This guide will walk through setting up the triggerscope (DAC device) to externally drive the LCs for hardware sequencing.

---
## Table of Contents
- [Setting up the Triggerscope](#setting-up-the-triggerscope)
  - [Table of Contents](#table-of-contents)
  - [Triggerscope](#triggerscope)
  - [Setup the Triggerscope with micromanager](#setup-the-triggerscope-with-micromanager)
    - [Plugin the triggerscope](#plugin-the-triggerscope)
    - [Remove/Check the Meadowlark device is not in config file](#removecheck-the-meadolwark-device-is-not-in-config-file)
  - [Connect the Meadowlark LC control box to the Triggerscope](#connect-the-meadowlark-lc-control-box-to-the-triggerscope)
  - [Set the LCs to `external mode`](#set-the-lcs-to-external-mode)
  - [Launch micromanager with the new config file](#launch-micromanager-with-the-new-config-file)
  - [FAQ / Troubleshooting](#faq--troubleshooting)

---
## Triggerscope
The Triggerscope is a device for hardware control and synchronization of cameras, lasers, shutters, galvos, stages and other optoelectronic equipment used popularily used home-built microscopes. 

** triggerscope image

In this case, the triggerscope is used to send 0-5V signal to the Meadowlark DS5020 controlbox to drive the LCs through external analog inputs. 
*Note: the Meadowlark DS5020 is required as it converts the signals 

**  Check the Triggerscope Firmware

Additionally, the triggerscope can be used as a device that can be sequenced to trigger fast and precisely the optoelectronic hardware in the microscope. In Micromanager, sequencing referes to the pre-computed train of events that will trigger the different pieces of hardware fast and precisly. To create fast and precise triggering sequences, Micromanager needs to know what devices will be `sequenced` and in what order, typically predetermined by the MDA. The devices that can be sequenced include lightsources, laser combiners, stages, and DACs. Refer to the individual device adapater to check if this devices supports `hardware sequencing`.

## Setup the Triggerscope with Micromanager

Launch Micromanager, open `Devices > Hardware Configuration Wizard...`, and add the `Triggerscope  Hub` device to your configuration.

Confirm your installation by opening Devices > Device Property Browser... and confirming that `Triggerscope DAC` properties appear.
### Plugin the triggerscope
- Connect the triggerscope via USB
- Connect the external power supply to the triggerscope
- Flip on the switch

### Remove/Check the Meadowlark device is not in config file


## Connect the Meadowlark LC control box to the Triggerscope
Using the connectors on the LC control box, connect the LC to
Make sure to note which LC (i.e LCA and LCB) is connected to Triggerscope DAC ##.

** missing pictures for the connectors

## Set the LCs to `external mode`


## Launch micromanager with the new config file


## FAQ / Troubleshooting
- The LCs are not changing even if I sweep the voltages on the micromanager properties. 
  - Make sure the LC controller box is connected to the computer via USB
  - Open CellDrive and set the LCs in ["external mode"](#set-the-lcs-to-external-mode)
- When I change the triggerscope voltages from the MM device property manager, MM crashes
  - [Check](#plugin-the-triggerscope) that the Triggerscope is connected via USB and connected to its power supply through the barrel connector. 
- What is sequencing?

