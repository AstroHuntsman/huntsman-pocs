#==============================================================================
# Dockerfile for a distributed Huntsman camera.
#==============================================================================
ARG image_url=huntsmanarray/huntsman-pocs:latest
FROM ${image_url} AS huntsman-base

ARG arch="armv7"

LABEL description="Image for a remote device running a pyro camera service."
LABEL maintainers="developers@huntsman.space"
LABEL repo="github.com/AstroHuntsman/huntsman-pocs"

# ZWO camera & EFW libraries
RUN apt-get update && \
    export BUILD_DIR=$(pwd)/ASIBuild && \
    mkdir $BUILD_DIR && \
    # ZWO camera
    apt-get -y install libusb-1.0-0-dev && \
    cd $BUILD_DIR && \
    mkdir BUILD_CAM && \
    cd BUILD_CAM && \
    export TARGET=ASI_linux_mac_SDK_V1.15.0617.tar.bz2 && \
    wget https://astronomy-imaging-camera.com/software/$TARGET && \
    tar xvjf $TARGET && \
    cd lib && \
    cp "${arch}/libASICamera2.so" /usr/local/lib/ && \
    chmod a+rx /usr/local/lib/libASICamera2.so && \
    install asi.rules /etc/udev/rules.d && \
    # ZWO filterwheel
    apt-get -y install libudev-dev && \
    cd $BUILD_DIR && \
    mkdir BUILD_EFW && \
    cd BUILD_EFW && \
    export TARGET=EFW_linux_mac_SDK_V1.5.0615.tar.bz2 && \
    wget https://astronomy-imaging-camera.com/software/$TARGET && \
    tar xvjf $TARGET && \
    cd lib && \
    cp "${arch}/libEFWFilter.so" /usr/local/lib/ && \
    chmod a+rx /usr/local/lib/libEFWFilter.so && \
    install efw.rules /etc/udev/rules.d && \
    # Clean up
    cd "$HOME" && \
    rm -rf $BUILD_DIR && \
    ldconfig

WORKDIR /var/huntsman
