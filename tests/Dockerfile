ARG image_url=docker.io/huntsmanarray/panoptes-pocs
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
ENV USERID $userid

USER "${userid}"

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
    sudo chown -R "${userid}:${userid}" "${HUNTSMAN_POCS}"

COPY docker/environment.yaml .
RUN conda env update -n base -f environment.yaml && \
    # POCS from github.
    pip install "git+https://github.com/panoptes/POCS.git@v0.7.8#egg=panoptes-pocs[focuser]"

ARG pip_install_extras="[testing]"

WORKDIR "${HUNTSMAN_POCS}"
COPY --chown="${userid}:${userid}" . .
RUN pip install -e ".${pip_install_extras}"

ENTRYPOINT [ "/usr/bin/env", "bash", "-ic" ]
CMD [ "pytest" ]
