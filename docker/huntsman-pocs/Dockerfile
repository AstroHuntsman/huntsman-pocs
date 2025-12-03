ARG image_url=huntsmanarray/panoptes-pocs
ARG image_tag=v0.7.8

FROM ${image_url}:${image_tag} AS pocs-base

ARG pocs_tag="v0.7.8"
ARG pocs_url="https://github.com/panoptes/POCS.git@${pocs_tag}#egg=panoptes-pocs"
ARG nats_server_version="v2.11.6"
ARG pip_install_name="."
ARG pip_install_extras=""

LABEL description="Huntsman POCS Service"
LABEL maintainers="developers@huntsman.space"
LABEL repo="github.com/AstroHuntsman/huntsman-pocs"

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8
ENV POCS="/panoptes-pocs"
ENV HUNTSMAN_POCS="/huntsman"

# ARG panuser=pocs-user
ENV USERID=1000
ENV PANUSER=$USERID


USER root

# Set up directories and give ownership
RUN mkdir -p ${HUNTSMAN_POCS}/{images,build,logs,archive,json_store} && \
    chmod -R 755 ${HUNTSMAN_POCS} && \
    chown -R "${PANUSER}:${PANUSER}" "${HUNTSMAN_POCS}"

# Install libraries
RUN echo "Building from ${image_url}:${image_tag}" && \
    apt-get update && \
    apt-get install -y --no-install-recommends gcc git udev nano

WORKDIR $HUNTSMAN_POCS

# Copy files and ensure ownership
COPY --chown="${PANUSER}:${PANUSER}" . .

USER root
RUN wget -qO- "https://binaries.nats.dev/nats-io/nats-server/v2@${nats_server_version}" | sh && \
    mv nats-server /usr/bin/nats-server

USER $PANUSER

COPY docker/huntsman-pocs/environment.yaml .
RUN micromamba update -n base -f environment.yaml && \
    # Make sure we are using the intended version of POCS
    micromamba run -n base pip uninstall -y panoptes-pocs && \
    micromamba run -n base pip install "git+${pocs_url}[focuser]" && \
    micromamba run -n base pip install -e "${pip_install_name}${pip_install_extras}" && \
    # Cleanup
    micromamba run -n base pip cache purge && \
    micromamba clean -fay && \
    sudo apt-get autoremove --purge --yes \
    gcc pkg-config && \
    sudo apt-get autoclean --yes && \
    sudo apt-get --yes clean && \
    sudo rm -rf /var/lib/apt/lists/*

# RUN micromamba update -y --verbose --debug -n base -f environment.yaml && \
#     micromamba run -n base pip uninstall -y panoptes-pocs && \
#     micromamba run -n base pip install "git+${pocs_url}[focuser]" && \
#     micromamba run -n base pip install -e "${pip_install_name}[testing]" && \
#     # Cleanup
#     micromamba run -n base pip cache purge && \
#     micromamba clean -fay
#


# RUN apt-get autoremove --purge --yes && \
#     apt-get autoclean --yes && \
#     apt-get --yes clean && \
#     rm -rf /var/lib/apt/lists/*
#
# USER $PANUSER

ENV PATH=/opt/conda/bin:$PATH
# ENTRYPOINT [ "/usr/bin/env", "bash", "-ic" ]
CMD [ "ipython" ]
