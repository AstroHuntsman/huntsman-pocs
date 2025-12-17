#!/usr/bin/env bash
set -euo pipefail

BUILD_DIR="${1:-./ASIBuild}"

# Current lib versions.
# CAM_LIB_VERSION=1.16
# EFW_LIB_VERSION=1.5.0615  # This has a bug when rotating forwards >one full rotation

# Get the arch -> x86_64 == x86
ARCH="${ARCH:-$(uname -m | cut -d'_' -f1)}"
# Change aarch64 to armv8
ARCH="${ARCH/aarch64/armv8}"

if [ "$EUID" -ne 0 ]; then
    echo "Please run as root"
    exit
fi

echo "BUILD_DIR: ${BUILD_DIR}"
echo "ARCH=${ARCH}"

ASI_SDK_URI="https://dl.zwoastro.com/software?app=DeveloperCameraSdk&platform=windows86&region=Overseas"
EFW_SDK_URI="https://dl.zwoastro.com/software?app=DeveloperEfwSdk&platform=windows86&region=Overseas"

# ZWO camera
function install_zwo() {
    # Install dependencies.
    apt-get update && apt-get --yes install libusb-1.0-0-dev libudev-dev

    echo "Downloading ASI SDK"
    mkdir -p "${BUILD_DIR}/zwo" && cd "${BUILD_DIR}/zwo"
    INSTALL_FILE="ASI_SDK"
    wget --output-document "${INSTALL_FILE}.zip" "${ASI_SDK_URI}"
    unzip "${INSTALL_FILE}.zip"
    tar xvjf ASI_Camera_SDK/ASI_linux_mac_SDK_V*.tar.bz2 && cd ASI_linux_mac_SDK_V*/lib
    # Move the library file.
    echo "Installing ASI libraries"
    cp "${ARCH}/libASICamera2.so" /usr/local/lib/
    chmod a+rx /usr/local/lib/libASICamera2.so
    install asi.rules /etc/udev/rules.d

    # ZWO filterwheel
    echo "Downloading ZWO EFW SDK"
    mkdir -p "${BUILD_DIR}/zwo-filterwheel" && cd "${BUILD_DIR}/zwo-filterwheel"
    INSTALL_FILE="EFW_SDK"
    wget --output-document "${INSTALL_FILE}.zip" "${EFW_SDK_URI}"
    unzip "${INSTALL_FILE}.zip"
    tar xvjf ${INSTALL_FILE}/EFW_Linux_macOS_SDK_V*.tar.bz2
    # cd EFW_linux_mac_SDK_V*/lib
    # Move the library file.
    echo "Installing ZWO EFW libraries"
    libname=$(find -name "libEFWFilter.so" | grep ${ARCH})
    # cp "ASIBuild/zwo/ASI_linux_mac_SDK_V*/lib/ASIBuild/zwo-filterwheel/efw/lib/${ARCH}/libEFW"
    cp $libname /usr/local/lib
    # cp "${ARCH}/libEFWFilter.so" /usr/local/lib/
    chmod a+rx /usr/local/lib/libEFWFilter.so
    rules=$(find -name "efw.rules")
    install $rules /etc/udev/rules.d
}

# Make the build dir.
mkdir -p "${BUILD_DIR}"

# Call the function.
install_zwo

# Clean up
rm -rf ${BUILD_DIR}
ldconfig
