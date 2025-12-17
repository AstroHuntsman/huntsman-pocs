# System setup

## Install Raspbian

* via MicroSD card reader, install Raspian image as described at [this link](https://www.raspberrypi.org/documentation/installation/installing-images/). Use the lite version, as we don't really need desktop functionality and this frees up a lot of space.
* Enable ssh access, put MicroSD card into reader (Sarah has one) and add a file named `ssh` with no extension to the top directory (boot)

## Configure hunstman user

* If accessing the pi locally, you can just use `ssh pi@raspberrypi.local` for the first login. Use default username and password: pi, raspberry
* Add user for huntsman: `sudo adduser huntsman`. If it asks for room number etc, just press enter until it asks if your information is correct.
* Add `huntsman` user to necessary groups for sudo and hardware access: `sudo usermod -a -G sudo,dialout,plugdev,netdev,users,input,spi,i2c,gpio huntsman`.
* Logout and login as `huntsman`.

## Set hostname

* Change hostname: `sudo nano /etc/hostname`
* Also change hostname in here: `sudo nano /etc/hosts`
* Reboot to have hostname change take effect.

## Security

* Delete default user account: `sudo deluser pi`
* Configure Fail2Ban and automatic security updates following the instructions in steps 3 & 4 in this link: http://kamilslab.com/2017/01/29/5-best-basic-security-tips-and-tricks-every-raspberry-pi-user-needs-to-take/
* To auto ssh into the Pi itself from e.g. the control computer, follow instructions at [this link](https://www.raspberrypi.org/documentation/remote-access/ssh/passwordless.md).
* Use `ssh-copy-id` to enable autologin to control computer.

## Disable LEDs, unused systems

Edit `/boot/config.txt` (using, for example, `sudo nano /boot/config.txt`) and add the following to the end of the file:
```
# Huntsman Pi customisation for Raspberry Pi 3B+

# Disable HDMI to save power
hdmi_blanking=2

# Disable WiFi to save power
dtoverlay=disable-wifi

# Disable Bluetooth to save power
dtoverlay=disable-bt

# Disable ethernet port LEDs
dtparam=eth_led0=14
dtparam=eth_led1=14

# Disable activity LED
dtoverlay=act-led
dtparam=act_led_trigger=none
dtparam=act_led_activelow=off  

# Disable power LED
dtparam=pwr_led_trigger=none
dtparam=pwr_led_activelow=off

```

_Note, some of these commands will differ for different types of Raspberry Pi (e.g. 3B+, 4B) and may require up to date firmware. The available options for the latest Raspbian firmware are documented here:_ https://github.com/raspberrypi/firmware/blob/master/boot/overlays/README

# Camera server setup

## Setting up a docker-less version

See [this link](https://github.com/panoptes/POCS/wiki/RaspPi:-POCS-and-the-Pi).

## Setting up a docker version


### Install packages
```
sudo apt-get update
sudo apt-get -y install git python3-pip byobu vim grc
```

### Install drivers for ZWO cameras and filterwheels
Download and install SDKs [here](https://astronomy-imaging-camera.com/software-drivers).

### Set-up environment variables
```
echo -e "\n#HUNTSMAN-POCS" >> ~/.bashrc
echo "export PANDIR=/var/huntsman" >> ~/.bashrc
echo 'export HUNTSMAN_POCS=$PANDIR/huntsman-pocs' >> ~/.bashrc
source ~/.bashrc
```

### Install minimal Huntsman-POCS
```
sudo mkdir -p $PANDIR
sudo chown -R huntsman $PANDIR
cd $PANDIR
git clone https://github.com/AstroHuntsman/huntsman-pocs.git
```

### Install and set-up docker
```
sudo apt-get install apt-transport-https ca-certificates software-properties-common -y
curl -fsSL get.docker.com -o get-docker.sh && sh get-docker.sh
sudo usermod -aG docker huntsman
sudo pip3 install docker-compose
```

### Pull the camera docker image
```
docker pull huntsmanarray/camera:latest
```
