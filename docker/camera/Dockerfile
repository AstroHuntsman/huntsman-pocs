ARG image_url=batbold/huntsman-pocs
ARG image_tag=develop
FROM ${image_url}:${image_tag} AS pocs-base

ARG arch="armv7"

LABEL description="Image for a remote device running a pyro camera service."
LABEL maintainers="developers@huntsman.space"
LABEL repo="github.com/AstroHuntsman/huntsman-pocs"

# ZWO camera & EFW libraries
RUN cp /huntsman/scripts/camera/install-camera-libs.sh /tmp/install-camera-libs.sh
RUN sudo /tmp/install-camera-libs.sh && \
    # Cleanup.
    sudo apt-get autoremove --purge --yes && \
    sudo apt-get autoclean --yes && \
    sudo apt-get --yes clean && \
    sudo rm -rf /var/lib/apt/lists/*

WORKDIR /huntsman
