ARG image_url=gcr.io/panoptes-exp/panoptes-pocs:develop
FROM ${image_url} AS pocs-base

LABEL description="Huntsman - PANOPTES Observatory Control System"
LABEL repo="github.com/AstroHuntsman/huntsman-pocs"

ARG panuser=huntsman
ARG pan_user_fullname="Huntsman Telephoto Array"
ARG userid=1000
ARG pan_dir=/var/panoptes
ARG huntsman_dir=/var/huntsman
ARG pocs_dir="${pan_dir}/POCS"
ARG conda_env_name="base"

ARG pip_extras="[testing]"

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8

ENV PANDIR=$pan_dir
ENV PANLOG="$pan_dir/logs"
ENV PANUSER=$panuser
ENV POCS=$pocs_dir

ENV HUNTSMAN_DIR "${huntsman_dir}"
ENV HUNTSMAN_POCS "${huntsman_dir}/huntsman-pocs"

# Install system dependencies.
USER root
RUN apt-get update && apt-get install --no-install-recommends --yes \
        gcc \
        ncurses-dev \
        readline-common \
        udev && \
    # Change username. We need to keep the uid=1000 but want a different name.
    usermod -l "${panuser}" panoptes && \
    # Change group. We need to keep the uid=1000 but want a different name.
    groupmod -n "${panuser}" panoptes && \
    # Change home directory.
    usermod -d "/home/${panuser}" -m "${panuser}" && \
    # Setup SSH so localhost works without password
    mkdir -p "/home/${panuser}/.ssh" && \
    echo "Host localhost\n\tStrictHostKeyChecking no\n" >> "/home/${panuser}/.ssh/config" && \
    # Make sure PANUSER has permissions to Huntsman dir.
    mkdir -p "${HUNTSMAN_DIR}/logs" && \
    mkdir -p "${HUNTSMAN_POCS}" && \
    chown -R "${panuser}":"${panuser}" "${POCS}" && \
    chown -R "${panuser}":"${panuser}" "${huntsman_dir}" && \
    echo "Linking the old panoptes dir to new home." && \
    ln -s "/home/${panuser}" "/home/panoptes" && \
    chown -R "${panuser}":"${panuser}" "/home/${panuser}" && \
    echo "export HUNTSMAN_DIR=${huntsman_dir}" >> /home/${panuser}/.zshrc && \
    echo "export HUNTSMAN_POCS=${huntsman_dir}/huntsman-pocs" >> /home/${panuser}/.zshrc && \
    # Grab the wait-for-it script
    wget -qO - https://raw.githubusercontent.com/vishnubob/wait-for-it/master/wait-for-it.sh > "/usr/local/bin/wait-for-it.sh" && \
    chmod a+x "/usr/local/bin/wait-for-it.sh"

# Install the module.
USER ${PANUSER}
WORKDIR ${HUNTSMAN_POCS}
# Can't seem to get around the hard-coding user and group here.
COPY --chown=1000:1000 . .
RUN "${PANDIR}/conda/bin/pip" install -e ".${pip_extras}" && \
    # Cleanup
    sudo apt-get autoremove --purge --yes && \
    sudo apt-get autoclean --yes && \
    sudo apt-get --yes clean && \
    sudo rm -rf /var/lib/apt/lists/* && \
    "${PANDIR}/conda/bin/conda" clean -tipy

USER root
ENTRYPOINT ["/bin/sh", "/var/huntsman/huntsman-pocs/resources/docker/entrypoint.sh"]
CMD ["echo Please specify a command."]
