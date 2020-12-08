ARG image_url=huntsmanarray/huntsman-pocs:develop
FROM ${image_url} AS huntsman-base

ARG arch="armv7"

LABEL description="Image for a remote device running a pyro camera service."
LABEL maintainers="developers@huntsman.space"
LABEL repo="github.com/AstroHuntsman/huntsman-pocs"

# ZWO camera & EFW libraries
COPY ./scripts/camera/install-camera-libs.sh /tmp/install-camera-libs.sh
RUN /tmp/install-camera-libs.sh && \
    # Cleanup.
    apt-get autoremove --purge --yes && \
    apt-get autoclean --yes && \
    apt-get --yes clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /var/huntsman
