ARG image_url=bsreddragon/panoptes-pocs
ARG image_tag=v0.7.8

# FROM ${image_url}:${image_tag} AS pocs-base
FROM bsreddragon/panoptes-pocs:v0.7.8 AS pocs-base

ARG pocs_tag="v0.7.8"
ARG pocs_url="https://github.com/panoptes/POCS.git@${pocs_tag}#egg=panoptes-pocs"

LABEL description="Huntsman POCS Service"
LABEL maintainers="developers@huntsman.space"
LABEL repo="github.com/AstroHuntsman/huntsman-pocs"

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8
ENV POCS="/huntsman"

ARG panuser=pocs-user
ARG userid=1000
ENV USERID $userid
ENV PANUSER $panuser


#USER "${userid}"
USER "${panuser}"
# Set up some common directories
RUN echo "Building from ${image_url}:${image_tag}" && \
    sudo apt-get update && \
    sudo apt-get install -y --no-install-recommends \
    gcc git udev nano vim-nox && \
    sudo mkdir -p "${POCS}/images"  && \
    sudo mkdir -p "${POCS}/logs"  && \
    sudo mkdir -p "${POCS}/archive"  && \
    sudo mkdir -p "${POCS}/json_store"  && \
    sudo chown -R "${PANUSER}:${MAMBA_USER}" "${POCS}"

ARG pip_install_name="."
ARG pip_install_extras=""

WORKDIR "${POCS}"
COPY --chown="${PANUSER}:${MAMBA_USER}" . .

RUN echo "Installing ${pip_install_name} module with ${pip_install_extras}" && \
    /usr/bin/env bash -ic 'pip install "${pip_install_name}${pip_install_extras}"'

COPY docker/environment.yaml .
RUN micromamba update -n base -f environment.yaml && \
    # Make sure we are using the intended version of POCS
    micromamba run -n base pip uninstall -y panoptes-pocs && \
    micromamba run -n base pip install "git+${pocs_url}[focuser]" && \
    micromamba run -n base pip install "flask<2.3" && \
    micromamba run -n base pip install "nats-py==2.10.0" && \
    # Cleanup
    micromamba run -n base pip cache purge && \
    micromamba clean -fay && \
    sudo apt-get autoremove --purge --yes \
    gcc pkg-config && \
    sudo apt-get autoclean --yes && \
    sudo apt-get --yes clean && \
    sudo rm -rf /var/lib/apt/lists/*

COPY --chown="${PANUSER}:${MAMBA_USER}" resources resources
COPY --chown="${PANUSER}:${MAMBA_USER}" scripts scripts

ENTRYPOINT [ "/usr/bin/env", "bash", "-ic" ]
CMD [ "ipython" ]
