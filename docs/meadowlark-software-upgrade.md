# Upgrade Meadownlark PC software version

To upgrade your "PC software version" use these steps:

- From "Add and remove programs", remove CellDrive5000 and "National Instruments Software".
- From "Device manager", open the "Meadowlark Optics" group, right click `mlousb`, click "Uninstall device", check "Delete the driver software for this device", and click "Uninstall". Uninstall `Meadowlark Optics D5020 LC Driver` following the same steps.
- Using the USB stick provided by Meadowlark, reinstall the USB drivers and CellDrive5000. 
- Confirm that "PC software version" == 1.08
- **Upgrading users:** you will need to reinstall the Meadowlark device to your micromanager configuration file, because the device driver's name has changed to `MeadowlarkLC`. 