# Device Mode

Below are the steps to put a camera jetson into device mode to be able to re-image it. There are photos accompanying these instructions on the huntsman important docs google drive under `/huntsman_important_documents/subsystems/nvidia/Jetson Setup Accompanying Notes`.

 _**Please carefully review the photos before starting.**_

1) You will need:
- a phillips head screwdriver
- a pair of long nose tweezers (long nose pliers are too big) 

**Ensure that none of your tools are magnetised before starting**

2) Unscrew the heat sink - some of the screws might be different sizes but there is no rhyme or reason to the positioning - for some jetsons the screws are all the same. 

3) Push the excessive cabling aside to see the H D pin next to the usb 2 ports 

4) With the tweezers carefully remove the cap on the pin. It is secured tightly, so just gently encourage it up and off. 

5) Once off, move the pin from H for host, to D for device. Push it down firmly. Orientation of the pin is given on the google docs images.  

6) Replace cabling. Orientate the heat sink so the heat sink markers on the base of it are over the grey contact points. Replace screws. The USB port 1 will now be in device mode. 

# Re-Imaging 

The jetson's can't be re-imaged like the pi's because they don't have removable memory. They must be put into device mode, and then re-imaged using usb port 1, and a female to female usb cable. 

### 1) Download the software
The OS or "BSP" as it is called, is a combination of the usual nvidia jetpack OS, plus some extra features to make the hardware on the floyd carried box work. The version we are using with the jetsons can be found in the `Backup version BSP` in the huntsman important documents directory `huntsman_important_documents/subsystems/camera computers/floyd-jetbox info`

### 2) Start the Jetson up in recovery mode
Look for the hole with 'rec' on the front of the jetson. Using a small tool or paperclip hold the button down, and connect the jetson to power. Keep the button held down until you can see a green light on through the DC power port inside the floyd case. 

### 3) Connect to host computer 
Using either a mac or linux machine, connect usb type 2 port 1 on the jetson to a usb port on your computer. You will need a female to female cable to do this. To check if a connection has been made, on mac in a terminal type 

```
system_profiler SPUSBDataType
```

Or if you are using a linux machine type

``` 
lsusb
```

### 4) Prepare the image (Diamond Systems)
The folder dowloaded from the link in the important docs page will be named `Floyd NX BSP v2.0 20201022`. Navigate to where you are storing it. 

```
cd /Desktop/Floyd NX BSP v2.0 20201022
```
Extract the contents of the tar file with the OS - this may take some time 

```
sudo tar -pxvzf dsc-floyd-nx-release-2.0-20201022.tar.gz
```

### Alternative: Prepare the image (NVIDIA)

Download the required files (BSP and sample root filesystem) from the [NVIDIA L4T archive](https://developer.nvidia.com/embedded/linux-tegra-archive). e.g.:
```
mkdir ~/nvidia-jetpack && cd ~/nvidia-jetpack
wget https://developer.nvidia.com/embedded/l4t/r32_release_v5.1/r32_release_v5.1/t186/tegra186_linux_r32.5.1_aarch64.tbz2
wget https://developer.nvidia.com/embedded/l4t/r32_release_v5.1/r32_release_v5.1/t186/tegra_linux_sample-root-filesystem_r32.5.1_aarch64.tbz2
```
Extract the BSP, then extract the sample root filesystem into the `rootfs` directory inside the extracted BSP:
```
tar -jxvf tegra186_linux_r32.5.1_aarch64.tbz2
sudo tar -jxvf tegra_linux_sample-root-filesystem_r32.5.1_aarch64.tbz2 -C Linux_for_Tegra/rootfs
```
Finalise the setup of the root filesystem:
```
cd Linux_for_Tegra && sudo ./apply_binaries.sh
```

### 5) Flash the images 

Navigate to the extracted directory 

```
cd Linux_for_Tegra
```

And flash the image onto the nvidia device 

```
sudo ./flash.sh jetson-xavier-nx-devkit-emmc mmcblk0p1
```

All avaible USB devices should be listed. If the connection has been made, one of them will be `Manufacturer: NVIDIA Corp.`

# Installing the M.2 Memory

The instructions to install the hardware with pics is under `/huntsman_important_documents/subsystems/nvidia/Jetson Installing M.2 Memory`.

# Set Up Software + OS NVIDIA Version

Below are the steps to create a camera jetson for Huntsman from scratch, and without cloud init using the Nvidia provided OS + Jetpack. 

### 1) Initial boot 

Plug it in to a monitor, with keyboard, mouse, and an ethernet connection and let it do its first boot. You will be asked to setup through where you are located (Sydney) keyboard preference (US) and a few other house keeping things.

When you get to the user set up screen, `username: huntsman` and `computer name: jetsonXXX` should be the settings. Replace XXX with the jetson number based on its serial number. The password will be in the hardware info docs. The jetson will now reboot itself when it logs in. Move through to the desktop. 

### 2) Setting up boot from M.2 

Now we will set up the jetson so it will automatically boot from the M.2 card that is installed. First install `nvme-cli` 

```
sudo apt-get install -y nvme-cli
```

Now reboot, and test if the card can be read 

```
lsblk -f
```

If you want to check if you can read and write to it, you can mount it:

```
sudo mount /dev/nvme0n1p1 /media

```
But if you can see it after doing `lsblk -f` you're ready to move to the next step. 

Now follow [these instructions](https://www.seeedstudio.com/blog/2020/06/22/boot-jetson-xavier-from-m-2-ssd/) to boot from the M.2
In order to prepare the SSD for booting. We want 16GB of swap space, and a partition called SAM512SSD. 

When you get to step 2, create a folder called `Development` in the home directory, to clone git repos that are stored locally to this folder 

```
cd 
mkdir Development
```

And clone the repo mentioned in the instructions 

```
cd ~/Development 
git clone https://github.com/jetsonhacks/rootOnNVMe.git
cd rootOnNVMe
```
**Remove the Ethernet cable **

It is very important that this next step completes in it's entirety or the jetson will be bricked and you will need to start again with a fresh install.  

Copy the rootfs file to your SSD

## VERY IMPORTANT: READ THIS 

This command must run properly or the Jetson will be bricked. The Jetsons do not like this command! 

**If the jetson reboots during this process, it's not happy. When it reboots, check `lsblk -f`. If the nvme is not there, `sudo reboot` again. If it does not turn on again after this, power cycle it. Power cycle or reboot until `lsblk -f` shows the nvme device again. Then, try the command again. Repeat this process until the command has completed in its entirety and the jetson does not reboot. Then, run the command 2 more times. Each time you should see 0% in the progress bar, meaning that all files have been copied over. Only then is it safe to continue.** 

```
./copy-rootfs-ssd.sh
```

And finally run 

```
./setup-service.sh
```

And then sudo reboot. Reboot about 2-3 times, checking `lsblk -f` each time to make sure the changes have sticked. 

### 3) Installation time!

The rest can be done headless, so grab the ip address to ssh in 

```
hostname -I
```

To find the MAC address of the two ethernet ports 

```
ip addr show eth0
```

```
ip addr show eth1
```

Get ready to start installing 

```
sudo apt-get update
sudo apt-get install nano 
```

To ensure the jetson remains in sync with a correct time, point it to the google time servers 

```
sudo apt-get install ntp 
sudo nano /etc/ntp.conf
```
Inside `ntp.conf` you should add the lines: 

```
server time1.google.com iburst
server time2.google.com iburst
server time3.google.com iburst
server time4.google.com iburst 
```
Comment out any lines starting with server if this is not a fresh jetson. 

Restart the NTP daemon using:

```
sudo service ntp reload
```

Make a panoptes group and huntsman to all the needed groups 

```
sudo addgroup panoptes
sudo usermod -a -G users,sudo,dialout,plugdev,docker,i2c,input,gpio,panoptes huntsman
```

Note: docker-compose, python3 and pip are installed later 

```
sudo apt-get install byobu apt-transport-https ca-certificates git htop httpie jq neovim software-properties-common speedometer vim-nox watchdog sshfs 
```

Allow huntsman user to mount via sshfs by editing `fuse.conf`. Uncomment the line `user_allow_other`

```
sudo nano /etc/fuse.conf 
```

Add something (read ALL lines below) to the sudoers file

```
sudo nano /etc/sudoers
```
And add the line:
```
%huntsman  ALL=(ALL) NOPASSWD:ALL
```
Install ALL the camera stuff! 

This can be done in the one big chunk below 

```
sudo mkdir -p /var/huntsman/scripts
sudo chown -R huntsman:huntsman /var/huntsman
cd /var/huntsman/scripts
wget https://raw.githubusercontent.com/AstroHuntsman/huntsman-pocs/develop/scripts/camera/install-camera-pi.sh -O /var/huntsman/scripts/install-camera-pi.sh
sudo bash /var/huntsman/scripts/install-camera-pi.sh
```

If there is a problem on reboot, power cycle it 

Add the env variables panoptes needs to the `./bachrc` file 

```
nano /home/huntsman/.bashrc
```
Change XX.XX.XX.XX to the IP of the control computer, and add the lines:

```
export PANUSER=huntsman
export PANOPTES_CONFIG_HOST=XX.XX.XX.XX
```

Now we need to force python 3 as the default - you don't need conda etc as everything will be in docker for now. Go to:

```
nano ~/.bashrc
```

Add the line:

```
alias python=python3 
```

And finally:

```
source ~/.bashrc
```

Installing pip3 and docker-compose

These can be tricky to install on the jetson because of `cryptography`. To force the install, use the temporary flag:  `$ export CRYPTOGRAPHY_DONT_BUILD_RUST=1`. This could take up to 10-15 minutes to install. 

```
sudo apt-get -y install python3-pip
pip3 install setuptools_rust
sudo apt-get install build-essential libssl-dev libffi-dev python-dev
pip3 install cryptography
pip3 install docker-compose
```

You will need to sudo reboot before the changes take effect. Now, the camera server should start in a byobu by itself. To check, just type `$ byobu` 

### Further Notes 

I've often found after a first attempt at running the camera script results in a failure to get into the logs file. To prevent this, you can change the permissions (not recommended) 

```
chmod 777 /var/huntsman/logs
chmod 777 /var/huntsman/images
```

If there is an error in doing so, maybe check if it is mounted or not, and unmount 

```
sudo umount /var/huntsman/images 
```

### UDEV rules for astromechanics

You will also need to add some rules to the jetson to be able to use the astromechanics focuser. 

```
cd /etc/udev/rules.d
nano astromech.rules
```
In the new file place:

```
#ASTROMECHANICS
SUBSYSTEMS=="usb",  ATTRS{id_vendor}=="0403", ATTRS{id_product}=="6001", ATTRS{serial}=="AG0JKSV1", ATTRS{manufacturer}=="FTDI", GROUP="plugdev", MODE="0664"
```

And save! 

### When you are in the mountain, and the jetson has been assigned it's ip address from the control computer 

After another reboot, get the public key for control computer. To do so, log onto the control computer, and from here:

```
sudo chown -R huntsman ~/.ssh/

ssh huntsman@XX.XX.XX.XX mkdir -p .ssh
cat .ssh/id_rsa.pub | ssh huntsman@XX.XX.XX.XX 'cat >> .ssh/authorized_keys'
```

Where huntsman@XX.XX.XX.XX is the address of the jetson (change as needed)

Now copy the jetson public key over to the control computer (change control comp ip as necessary). You will also need to ensure a new ssh key has been generated for the huntsman user. To check if this has been done check the output of `cat ~/.ssh/id_rsa.pub` which should contain a comment of the form `username@hostname` at the end of the file. The username should be `huntsman` (not `root`) and the hostname should match the hostname set for the jetson earlier.

```
ssh-copy-id -i ~/.ssh/id_rsa.pub huntsman@XX.XX.XX.XXX
```

# Set Up Software + OS Diamond Systems Version

Below are the steps to create a camera jetson for Huntsman from scratch, and without cloud init using the diamond systems BSP. 

### 1) Initial boot

Plug it in to a monitor, with keyboard, mouse, and an ethernet connection and let it do its first boot. The default password and username for any jetson on first boot should be nvidia, but it should log you in automatically. Once at the desktop, open a terminal and find the IP address. 

`$ hostname -I`

Now you can log in remotely, and you can unplug the monitor if you like 

### 2) Change the hostname 

Follow the huntsman naming convention of jetsXXX

```
sudo apt-get update
sudo apt-get install nano 
sudo nano /etc/hostname
sudo reboot
```
### 3) Update the time 

To ensure the jetson remains in sync with a correct time, point it to the google time servers 

```
sudo apt-get install ntp 
sudo nano /etc/ntp.conf
```
Inside `ntp.conf` you should add the lines: 

```
server time1.google.com iburst
server time2.google.com iburst
server time3.google.com iburst
server time4.google.com iburst 
```
Comment out any lines starting with server if this is not a fresh jetson. 

Restart the NTP daemon using:

```
sudo service ntp reload
```
### 4) Set up the Huntsman user 

The following will create the huntsman user, the needed groups, and add huntsman to them. All up-to-date jetpacks will have docker preinstalled, so the group should already exist. 

```
sudo adduser huntsman
sudo addgroup panoptes
sudo usermod -a -G users,sudo,dialout,plugdev,docker,i2c,input,gpio,panoptes huntsman
```
**Important:** Switch users to the `huntsman` user: 
```
sudo su huntsman
```

### 5) Permissions 

Add "ALL=(ALL) NOPASSWD:ALL" to sudoers file

```
sudo nano /etc/sudoers
```
And add the line:

```
%huntsman  ALL=(ALL) NOPASSWD:ALL
```

### 6) Install everything that is needed 

Note: docker-compose, python3 and pip are installed later 

```
sudo apt-get install byobu apt-transport-https ca-certificates git htop httpie jq neovim software-properties-common speedometer vim-nox watchdog sshfs 
```
### 7) Setting up sshfs

Allow huntsman user to mount via sshfs by editing `fuse.conf`. Uncomment the line `user_allow_other`

```
sudo nano /etc/fuse.conf 
```

### 8) Install ALL the camera stuff! 

This can be done in the one big chunk below 

```
sudo mkdir -p /var/huntsman/scripts
sudo chown -R huntsman:huntsman /var/huntsman
cd /var/huntsman/scripts
wget https://raw.githubusercontent.com/AstroHuntsman/huntsman-pocs/develop/scripts/camera/install-camera-pi.sh -O /var/huntsman/scripts/install-camera-pi.sh
sudo bash /var/huntsman/scripts/install-camera-pi.sh
```
### 9) Public keys 

After another reboot, get the public key for control computer. To do so, log onto the control computer, and from here:

```
ssh huntsman@XX.XX.XX.XX mkdir -p .ssh
cat .ssh/id_rsa.pub | ssh huntsman@XX.XX.XX.XX 'cat >> .ssh/authorized_keys'
```

Where huntsman@XX.XX.XX.XX is the address of the jetson (change as needed)

Now copy the jetson public key over to the control computer (change control comp ip as necessary). You will also need to ensure a new ssh key has been generated for the huntsman user. To check if this has been done check the output of `cat ~/.ssh/id_rsa.pub` which should contain a comment of the form `username@hostname` at the end of the file. The username should be `huntsman` (not `root`) and the hostname should match the hostname set for the jetson earlier.

```
ssh-copy-id -i ~/.ssh/id_rsa.pub huntsman@XX.XX.XX.XXX
```

### 10) Environment variables 

Add the env variables panoptes needs to the `./bachrc` file 

```
nano /home/huntsman/.bashrc
```
Change XX.XX.XX.XX to the IP of the control computer, and add the lines:

```
export PANUSER=huntsman
export PANOPTES_CONFIG_HOST=XX.XX.XX.XX
```
### 11) Installing python 3

Unfortunately this doesn't come preinstall on older jetson jetbacks. 

```
sudo apt-get install python3.6
```
Now we need to force python 3 as the default - you don't need conda etc as everything will be in docker for now. Go to:

```
nano ~/.bashrc
```

Add the line:

```
alias python=python3 
```
And finally:

```
source ~/.bashrc
sudo update-alternatives --install /usr/bin/python python /usr/bin/python3 10
```

### 12) Installing pip and docker-compose 

These can be tricky to install on the jetson because of `cryptography`. To force the install, use the temporary flag:  `$ export CRYPTOGRAPHY_DONT_BUILD_RUST=1`. This could take up to 10-15 minutes to install. 

```
sudo apt-get -y install python3-pip
pip3 install setuptools_rust
sudo apt-get install build-essential libssl-dev libffi-dev python-dev
pip3 install cryptography
pip3 install docker-compose
```

If there are problems using docker-compose afterwards, do a reboot. Now, the camera server should start in a byobu by itself. To check, just type `$ byobu` 

### 13) Logs permissions 

I've often found after a first attempt at running the camera script results in a failure to get into the logs file. To prevent this, you can change the permissions (not recommended) 

```
chmod 777 /var/huntsman/logs
```

If there is an error in doing so, maybe check if it is mounted or not, and unmount 

```
umount /var/huntsman/images 
```

### 14) UDEV rules

You will also need to add some rules to the jetson to be able to use the astromechanics focuser. 

```
cd /etc/udev/rules.d
nano astromech.rules
```
In the new file place:

```
#ASTROMECHANICS
SUBSYSTEMS=="usb",  ATTRS{id_vendor}=="0403", ATTRS{id_product}=="6001", ATTRS{serial}=="AG0JKSV1", ATTRS{manufacturer}=="FTDI", GROUP="plugdev", MODE="0664"
```

And save! 

# Tips and Tricks 

If the `/.bashrc` is not being sourced, add this to a `~/.bash_profile`

```
# include .bashrc if it exists
if [ -f "$HOME/.bashrc" ]; then
    . "$HOME/.bashrc"
fi
```

If you are dealing with a Jetson that is fitted with an AstroMechanics focuser, you should also add this to the volumes section of `docker-compose.yaml` file on in the jetson - if this has not been updated yet - you will need to disable docker-compose file pulling on the jetson as well or this change will be written over on camera service restart:

```
      - /dev/serial/by-id:/dev/serial/by-id
```

# IMPORTANT

To get the nvme M.2 card to be recognised to you need to install `nvme-cli` and reboot the jetson before trying 

```
sudo apt-get install -y nvme-cli
```

Now reboot, and test if the card can be read 

```
lsblk -f
```

Now lets check we can read and write to it. To do so:

```
sudo mount /dev/nvme0n1p1 /media

```

# To disable NVME booting:

Wait for the jetson to boot to MMC - then look for this file - (make a copy of it first somewhere else like Desktop)

```
cd /etc 
rm setssdroot.conf

cd /etc/systemd/system
sudo rm setssdroot.service 

cd /sbin
rm setssdroot.sh
```
