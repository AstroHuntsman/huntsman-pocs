#!/bin/bash
set -eu

REMOTE_HOST=${HUNTSMAN_REMOTE_HOST:-${PANOPTES_CONFIG_HOST}}
REMOTE_IMAGES_DIR=${PANUSER}@${REMOTE_HOST}:${PANDIR}/images
LOCAL_IMAGES_DIR=${PANDIR}/images

GITHUB_USER=${GITHUB_USER:-"AstroHuntsman"}
GITHUB_BRANCH=${GITHUB_BRANCH:-"develop"}

clear
echo "############### Huntsman Camera Service ###############"
echo "Control computer hostname: ${REMOTE_HOST}"

# Mount the SSHFS images directory
echo "Mounting remote images directory ${REMOTE_IMAGES_DIR} to ${LOCAL_IMAGES_DIR}"
mkdir -p ${LOCAL_IMAGES_DIR}
sudo umount ${LOCAL_IMAGES_DIR} || true
sshfs -o allow_other ${REMOTE_IMAGES_DIR} ${LOCAL_IMAGES_DIR}

# Get the docker-compose file
DC_FILE_URL=https://raw.githubusercontent.com/${GITHUB_USER}/huntsman-pocs/${GITHUB_BRANCH}/docker/camera/docker-compose.yaml
DC_FILE="${PANDIR}/docker-compose.yaml"
if [ -f ${DC_FILE} ] ; then
    echo "Removing existing docker-compose file: ${DC_FILE}"
    rm ${DC_FILE}
fi
echo "Downloading latest docker-compose file from ${DC_FILE_URL} to ${DC_FILE}"
wget ${DC_FILE_URL} -O ${DC_FILE}

# Start the docker service
echo "Downloading latest docker image(s)..."
docker-compose -f ${DC_FILE} pull
echo "Starting the camera docker service..."
docker-compose -f ${DC_FILE} run camera
