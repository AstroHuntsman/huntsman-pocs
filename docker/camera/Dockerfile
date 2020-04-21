#==============================================================================
# Dockerfile for a distributed Huntsman camera.
#==============================================================================

FROM huntsmanarray/arm_device:latest

# ZWO camera & EFW libraries
RUN export BUILD_DIR=$(pwd)/ASIBuild && \
    mkdir $BUILD_DIR && \
    # ZWO camera
    apt-get -y install libusb-1.0-0-dev && \
    cd $BUILD_DIR && \
    mkdir BUILD_CAM && \
    cd BUILD_CAM && \
    export TARGET=ASI_linux_mac_SDK_V1.14.1119.tar.bz2 && \
    wget https://astronomy-imaging-camera.com/software/$TARGET && \
    tar xvjf $TARGET && \
    cd lib && \
    cp armv7/libASICamera2.so /usr/local/lib/ && \
    chmod a+rx /usr/local/lib/libASICamera2.so && \
    install asi.rules /etc/udev/rules.d && \
    # ZWO filterwheel
    apt-get -y install libudev-dev && \
    cd $BUILD_DIR && \
    mkdir BUILD_EFW && \
    cd BUILD_EFW && \
    export TARGET=EFW_linux_mac_SDK_V0.4.1022.tar.bz2 && \
    wget https://astronomy-imaging-camera.com/software/$TARGET && \
    tar xvjf $TARGET && \
    cd lib && \
    cp armv7/libEFWFilter.so /usr/local/lib/ && \
    chmod a+rx /usr/local/lib/libEFWFilter.so && \
    install efw.rules /etc/udev/rules.d && \
    # Clean up
    rm -rf $BUILD_DIR && \
    ldconfig
