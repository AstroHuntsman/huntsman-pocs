#!/bin/bash
# This script is run from the camera pi. It will start a new camera service if there is not
# already one running. This involves:
# - (re)mounting the SSHFS images directory
# - Downloading the latest docker-compose file from github
# - Updating the relevant docker images
# - Starting the docker camera service
set -eu

REMOTE_HOST=${HUNTSMAN_REMOTE_HOST:-${PANOPTES_CONFIG_HOST}}
REMOTE_IMAGES_DIR=${PANUSER}@${REMOTE_HOST}:${PANDIR}/images
LOCAL_IMAGES_DIR=${PANDIR}/images

DC_FILE_URL=https://raw.githubusercontent.com/AstroHuntsman/huntsman-pocs/develop/docker/camera/docker-compose.yaml

# First, check if the camera docker service is already running. If so, exit 0.
cd ${PANDIR}
if [ -z `docker-compose ps -q camera` ] || [ -z `docker ps -q --no-trunc | grep $(docker-compose ps -q camera)` ]; then
  echo "No running docker camera service found. Starting a new one."
else
  echo "A docker camera service is already running."
  exit 0
fi

clear
echo "############### Huntsman Camera Service ###############"
echo "Control computer hostname: ${REMOTE_HOST}"

# Mount the SSHFS images directory
echo "Mounting remote images directory ${REMOTE_IMAGES_DIR} to ${LOCAL_IMAGES_DIR}"
mkdir -p ${LOCAL_IMAGES_DIR}
sudo umount ${LOCAL_IMAGES_DIR} || true
sshfs -o allow_other,reconnect,ServerAliveInterval=20,ServerAliveCountMax=3,StrictHostKeyChecking=False ${REMOTE_IMAGES_DIR} ${LOCAL_IMAGES_DIR}

# Get the docker-compose file
DC_FILE="${PANDIR}/docker-compose.yaml"
if [ -f ${DC_FILE} ] ; then
    echo "Removing existing docker-compose file: ${DC_FILE}"
    rm ${DC_FILE}
fi
echo "Downloading latest docker-compose file from ${DC_FILE_URL} to ${DC_FILE}"
wget ${DC_FILE_URL} -O ${DC_FILE}

# Prune docker
echo "Pruning docker system..."
docker system prune -f

# Start the docker service
echo "Downloading latest docker image(s)..."
docker-compose -f ${DC_FILE} pull
echo "Starting the camera docker service..."
docker-compose -f ${DC_FILE} --compatibility run camera
