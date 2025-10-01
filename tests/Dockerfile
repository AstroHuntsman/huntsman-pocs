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

ENV USERID 1000
ENV PANUSER=$USERID


USER root
# # Set up directories and give ownership
RUN mkdir -p ${HUNTSMAN_POCS}/{images,build,logs,archive,json_store} && \
    chmod -R 755 ${HUNTSMAN_POCS} && \
    chown -R "${PANUSER}:${PANUSER}" "${HUNTSMAN_POCS}"

# Install libraries
RUN echo "Building from ${image_url}:${image_tag}" && \
    apt-get update && \
    apt-get install -y --no-install-recommends gcc git udev nano vim-nox

WORKDIR $HUNTSMAN_POCS

# Copy files and ensure ownership
COPY --chown="${PANUSER}:${PANUSER}" . .

USER $PANUSER

COPY docker/huntsman-pocs/environment.yaml .
RUN micromamba update -n base -f environment.yaml && \
    micromamba run -n base pip uninstall -y panoptes-pocs && \
    micromamba run -n base pip install "git+${pocs_url}[focuser]" && \
    micromamba run -n base pip install -e ".[testing]" && \
    # Cleanup
    micromamba run -n base pip cache purge && \
    micromamba clean -fay 

USER root
RUN apt-get autoremove --purge --yes gcc pkg-config && \
    apt-get autoclean --yes && \
    apt-get --yes clean && \
    rm -rf /var/lib/apt/lists/*

USER $PANUSER

ENV PATH=/opt/conda/bin:$PATH
RUN source tests/huntsman.test.env
ENTRYPOINT ["pytest"]
