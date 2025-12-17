### Step 1: Install Ubuntu
Install **Ubuntu Server 20.04 LTS (64-bit)** on to a new (or erased) SD card. If the SD card has not new and has not been erased, you will need to erase it first, e.g. with the `Disk Utility` application on Mac. After that, follow the [official instructions](https://www.raspberrypi.org/documentation/installation/installing-images/) to install Ubuntu, making sure to select the correct version.

### Step 2: Transfer cloud-init files
After installing Ubuntu, you will need to copy all the files in `${HUNTSMAN_POCS}/resources/rpi` (make sure you have the latest version from the `develop` branch) onto the top directory on the SD card. **Modify the instance-specific data at the top of the `user-data` file for your specific pi.**

### Step 3: Boot the pi
Put the SD card into the pi and power it on. `cloud-init` will run automatically - it takes around half an hour and does not require supervision. Once it finishes, you will automatically be logged in as the `huntsman` user. It is normal for the pi to reboot itself once or twice during this process.

**Note: the pi must have an ethernet connection during boot.**

### Step 4: Finalise installation
To finalise the installation, you will need to do two things:
- Append the public key of the control computer to the `/home/huntsman/.ssh/authorized_keys ` directory on the pi. If unsure, [these instructions](http://www.linuxproblem.org/art_9.html) may help.
- Export the `PANOPTES_CONFIG_HOST` environment variable in `/home/huntsman/.bashrc`.

### Step 5: Start the camera service
The simplest way to start the camera service is to reboot the pi. **The latest docker images will be pulled automatically after reboot**. If all has gone well, the camera service will start automatically in the `camera-service` window of the `huntsman` `byobu` session.
