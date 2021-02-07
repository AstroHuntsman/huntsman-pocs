ARG image_url=gcr.io/panoptes-exp/panoptes-pocs
ARG image_tag=develop
FROM ${image_url}:${image_tag} AS pocs-base

LABEL description="Huntsman POCS Service"
LABEL maintainers="developers@huntsman.space"
LABEL repo="github.com/AstroHuntsman/huntsman-pocs"

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8
ENV POCS "/huntsman"

ARG userid=1000
ENV USERID $userid

USER "${userid}"

# Set up some common directories
RUN echo "Building from ${image_name}:${image_tag}" && \
    sudo apt-get update && \
    sudo apt-get install -y --no-install-recommends \
        gcc git udev && \
    sudo mkdir -p "${POCS}/images"  && \
    sudo mkdir -p "${POCS}/logs"  && \
    sudo mkdir -p "${POCS}/archive"  && \
    sudo mkdir -p "${POCS}/json_store"  && \
    sudo chown -R "${userid}:${userid}" "${POCS}"

COPY docker/environment.yaml .
RUN /conda/bin/conda env update -n base -f environment.yaml && \
    # POCS from github.
    /conda/bin/pip install "git+https://github.com/panoptes/POCS.git@develop#egg=panoptes-pocs[focuser]"

ARG pip_install_name="."
ARG pip_install_extras=""

COPY --chown="${userid}:${userid}" . .
RUN echo "Installing ${pip_install_name} module with ${pip_install_extras}" && \
    /conda/bin/pip install "${pip_install_name}${pip_install_extras}" && \
    # Cleanup
    /conda/bin/pip cache purge && \
    /conda/bin/conda clean -fay && \
    sudo apt-get autoremove --purge --yes \
        gcc pkg-config git && \
    sudo apt-get autoclean --yes && \
    sudo apt-get --yes clean && \
    sudo rm -rf /var/lib/apt/lists/*

WORKDIR "${POCS}"
COPY --chown="${userid}:${userid}" docker/docker-compose.yaml .
COPY --chown="${userid}:${userid}" resources resources
COPY --chown="${userid}:${userid}" scripts scripts

ENTRYPOINT [ "/usr/bin/env", "bash", "-ic" ]
CMD [ "ipython" ]
