#!/usr/bin/env bash

set -e
set -u

BUILD_DIR=${1:-./ASIBuild}

# Current lib versions.
CAM_LIB_VERSION=1.15.0617
EFW_LIB_VERSION=1.5.0615
# Get the arch -> x86_64 == x86
ARCH=${ARCH:-$(uname -m | cut -d'_' -f1)}

# ZWO camera
function install_zwo() {
  # Install dependencies.
  apt-get update && apt-get --yes install libusb-1.0-0-dev libudev-dev

  mkdir -p "${BUILD_DIR}/zwo" && cd "${BUILD_DIR}/zwo"
  INSTALL_FILE=ASI_linux_mac_SDK_V${CAM_LIB_VERSION}.tar.bz2
  wget "https://astronomy-imaging-camera.com/software/${INSTALL_FILE}"
  tar xvjf "${INSTALL_FILE}" && cd lib
  # Move the library file.
  cp "${ARCH}/libASICamera2.so" /usr/local/lib/
  chmod a+rx /usr/local/lib/libASICamera2.so
  install asi.rules /etc/udev/rules.d

  # ZWO filterwheel
  mkdir -p "${BUILD_DIR}/zwo-filterwheel" && cd "${BUILD_DIR}/zwo-filterwheel"
  INSTALL_FILE=EFW_linux_mac_SDK_V${EFW_LIB_VERSION}.tar.bz2
  wget "https://astronomy-imaging-camera.com/software/${INSTALL_FILE}"
  tar xvjf "${INSTALL_FILE}" && cd lib
  # Move the library file.
  cp "${ARCH}/libEFWFilter.so" /usr/local/lib/
  chmod a+rx /usr/local/lib/libEFWFilter.so
  install efw.rules /etc/udev/rules.d
}

# Make the build dir.
mkdir -p "${BUILD_DIR}"

# Call the function.
install_zwo

# Clean up
rm -rf ${BUILD_DIR}
ldconfig
