ARG image_url=huntsmanarray/panoptes-pocs
ARG image_tag=v0.7.8
FROM ${image_url}:${image_tag} AS pocs-base

LABEL description="Huntsman POCS Testing Service"
LABEL maintainers="developers@huntsman.space"
LABEL repo="github.com/AstroHuntsman/huntsman-pocs"

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8
ENV POCS "/panoptes-pocs"
ENV HUNTSMAN_POCS "/huntsman"
ARG pocs_tag="v0.7.8"
ARG pocs_url="https://github.com/panoptes/POCS.git@${pocs_tag}#egg=panoptes-pocs"

ARG userid=1000
ENV USERID $userid
ARG PANUSER=$userid


# Set up some common directories
RUN echo "Building from ${image_url}:${image_tag}" && \
    sudo apt-get update && \
    sudo apt-get install -y --no-install-recommends \
    gcc git udev nano vim-nox && \
    sudo mkdir -p "${HUNTSMAN_POCS}/images"  && \
    sudo mkdir -p "${HUNTSMAN_POCS}/build"  && \
    sudo mkdir -p "${HUNTSMAN_POCS}/logs"  && \
    sudo mkdir -p "${HUNTSMAN_POCS}/archive"  && \
    sudo mkdir -p "${HUNTSMAN_POCS}/json_store"  && \
    sudo chown -R "${PANUSER}:${MAMBA_USER}" "${HUNTSMAN_POCS}"

USER $PANUSER
WORKDIR $HUNTSMAN_POCS

# Copy files and ensure ownership
COPY --chown="${PANUSER}:${MAMBA_USER}" resources resources
COPY --chown="${PANUSER}:${MAMBA_USER}" scripts scripts
COPY --chown="${PANUSER}:${MAMBA_USER}" tests tests
COPY --chown="${PANUSER}:${MAMBA_USER}" . .

RUN echo "Installing ${pip_install_name} module with ${pip_install_extras}" && \
    # The --user flag ensures pip installs to the user's home directory,
    # avoiding permission issues in system-wide directories.
    # Alternatively, ensure the WORKDIR is writable by the user.
    # We will ensure the WORKDIR is writable by the user below.
    # The following commands should work fine as long as the WORKDIR
    # is properly owned by the user.
    echo "Installing with micromamba and pip"

COPY docker/huntsman-pocs/environment.yaml .
RUN micromamba update -n base -f environment.yaml && \
    # First, uninstall any existing panoptes-pocs to avoid conflicts
    micromamba run -n base pip uninstall -y panoptes-pocs && \
    # Now, install the remote panoptes-pocs library
    micromamba run -n base pip install "git+${pocs_url}[focuser]" && \
    # Next, install the local huntsman-pocs package in editable mode
    micromamba run -n base pip install -e ".[testing]" && \
    # Cleanup
    micromamba run -n base pip cache purge && \
    micromamba clean -fay && \
    sudo apt-get autoremove --purge --yes gcc pkg-config && \
    sudo apt-get autoclean --yes && \
    sudo apt-get --yes clean && \
    sudo rm -rf /var/lib/apt/lists/*

ENTRYPOINT [ "/usr/bin/env", "bash", "-ic" ]
CMD [ "pytest", "-v", "-s" ]
# # Set up some common directories
# RUN echo "Building from ${image_name}:${image_tag}" && \
#     sudo apt-get update && \
#     sudo apt-get install -y --no-install-recommends \
#     git \
#     gcc \
#     udev && \
#     sudo mkdir -p "${HUNTSMAN_POCS}/images"  && \
#     sudo mkdir -p "${HUNTSMAN_POCS}/logs"  && \
#     sudo mkdir -p "${HUNTSMAN_POCS}/json_store"  && \
#     sudo chown -R "${panuser}:${MAMBA_USER}" "${HUNTSMAN_POCS}"
#
# COPY docker/huntsman-pocs/environment.yaml .
# RUN micromamba update -n base -f environment.yaml && \
#     micromamba run -n base pip install "git+https://github.com/panoptes/POCS.git@v0.7.8#egg=panoptes-pocs[focuser]"
# #     # Install specific Flask version before POCS
# #     micromamba run -n base pip install "flask\<2.0" && \
# #     # Install compatible versions of jinja2 and markupsafe
# #     micromamba run -n base pip install "jinja2\<3.0" "markupsafe\<2.1.0" && \
# #     # POCS from github.
#
# ARG pip_install_extras="[testing]"
#
# WORKDIR "${HUNTSMAN_POCS}"
# COPY --chown="${panuser}:${MAMBA_USER}" . .
# RUN /usr/bin/env bash -ic 'micromamba run -n base pip install -e ".${pip_install_extras}"'
#
# ENTRYPOINT [ "/usr/bin/env", "bash", "-ic" ]
# CMD [ "pytest", "-v", "-s" ]
