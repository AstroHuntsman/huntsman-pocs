#!/bin/bash

set -eu

export CAM_LIB_VERSION=1.15.0617
export EFW_LIB_VERSION=1.5.0615

export BUILD_DIR=$HOME/ASIBuild
mkdir ${BUILD_DIR}
# ZWO camera
sudo apt-get -y install libusb-1.0-0-dev
cd ${BUILD_DIR}
mkdir BUILD_CAM
cd BUILD_CAM
export TARGET=ASI_linux_mac_SDK_V${CAM_LIB_VERSION}.tar.bz2
wget https://astronomy-imaging-camera.com/software/$TARGET
tar xvjf $TARGET
cd lib
sudo cp armv7/libASICamera2.so /usr/local/lib/
sudo chmod a+rx /usr/local/lib/libASICamera2.so
sudo install asi.rules /etc/udev/rules.d
# ZWO filterwheel
sudo apt-get -y install libudev-dev
cd ${BUILD_DIR}
mkdir BUILD_EFW
cd BUILD_EFW
export TARGET=EFW_linux_mac_SDK_V${EFW_LIB_VERSION}.tar.bz2
wget https://astronomy-imaging-camera.com/software/$TARGET
tar xvjf $TARGET
cd lib
sudo cp armv7/libEFWFilter.so /usr/local/lib/
sudo chmod a+rx /usr/local/lib/libEFWFilter.so
sudo install efw.rules /etc/udev/rules.d
# Clean up
rm -rf ${BUILD_DIR}
sudo ldconfig
