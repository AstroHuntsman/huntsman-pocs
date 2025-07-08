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

ARG userid=1000
ARG panuser=pocs-user
ENV USERID $userid

USER "${panuser}"

# Set up some common directories
RUN echo "Building from ${image_name}:${image_tag}" && \
    sudo apt-get update && \
    sudo apt-get install -y --no-install-recommends \
    git \
    gcc \
    udev && \
    sudo mkdir -p "${HUNTSMAN_POCS}/images"  && \
    sudo mkdir -p "${HUNTSMAN_POCS}/logs"  && \
    sudo mkdir -p "${HUNTSMAN_POCS}/json_store"  && \
    sudo chown -R "${panuser}:${MAMBA_USER}" "${HUNTSMAN_POCS}"

COPY docker/environment.yaml .
RUN micromamba update -n base -f environment.yaml && \
    # Install specific Flask version before POCS
    micromamba run -n base pip install "flask<2.0" && \
    # Install compatible versions of jinja2 and markupsafe
    micromamba run -n base pip install "jinja2<3.0" "markupsafe<2.1.0" && \
    # POCS from github.
    micromamba run -n base pip install "git+https://github.com/panoptes/POCS.git@v0.7.8#egg=panoptes-pocs[focuser]"

ARG pip_install_extras="[testing]"

WORKDIR "${HUNTSMAN_POCS}"
COPY --chown="${panuser}:${MAMBA_USER}" . .
RUN /usr/bin/env bash -ic 'micromamba run -n base pip install -e ".${pip_install_extras}"'

ENTRYPOINT [ "/usr/bin/env", "bash", "-ic" ]
CMD [ "pytest", "-v", "-s" ]
