#!/usr/bin/env bash
set -e

TAG="${1:-develop}"

# Options to control build.
INCLUDE_PANOPTES="${INCLUDE_PANOPTES:-false}"
INCLUDE_CAMERA="${INCLUDE_UTILS:-false}"

# Directories to build from.
POCS="${POCS:-/var/huntsman/huntsman-pocs}"
HUNTSMAN_POCS="${HUNTSMAN_POCS:-/var/huntsman/huntsman-pocs}"

# Docker images to user.
POCS_IMAGE_URL="${POCS_IMAGE_URL:-gcr.io/panoptes-exp/panoptes-pocs:develop}"
HUNTS_POCS_IMAGE_URL="${HUNTS_POCS_IMAGE_URL:-huntsmanarray/huntsman-pocs:${TAG}}"

echo "Setting up local environment."
cd "${HUNTSMAN_POCS}"

# Builds a local image for the PANOPTES items.
build_panoptes() {
  echo "Building local ${POCS_IMAGE_URL} from ${POCS_IMAGE_URL} in ${POCS}."
  INCLUDE_BASE=true INCLUDE_UTILS=true "${POCS}/scripts/setup-local-environment.sh"
  # Use our local image for build below instead of gcr.io image.
  POCS_IMAGE_URL="panoptes-pocs:${TAG}"
  echo "Setting POCS_IMAGE_URL=${POCS_IMAGE_URL}"

}

# Builds a local image for testing, etc. Also the base of other images.
build_develop() {
  echo "Building local ${HUNTS_POCS_IMAGE_URL} from ${POCS_IMAGE_URL} in ${HUNTSMAN_POCS}."
  docker build \
    --build-arg "image_url=${POCS_IMAGE_URL}" \
    -t "huntsman-pocs:${TAG}" \
    -f "${HUNTSMAN_POCS}/docker/Dockerfile" \
    "${HUNTSMAN_POCS}"

  # Use the local image below now that we have built it.
  HUNTS_POCS_IMAGE_URL="huntsman-pocs:${TAG}"
}

build_camera() {
  echo "Building local huntsman-pocs-camera:${TAG} from ${HUNTS_POCS_IMAGE_URL} in ${HUNTSMAN_POCS}"
  docker build \
    -t "huntsman-pocs-camera:${TAG}" \
    --build-arg "image_url=${HUNTS_POCS_IMAGE_URL},arch=x86" \
    -f "${HUNTSMAN_POCS}/docker/camera/Dockerfile" \
    "${HUNTSMAN_POCS}"
}

####################################################################################
# Script logic below
####################################################################################

if [ "${INCLUDE_PANOPTES}" = true ]; then
  build_panoptes
fi

build_develop

if [ "${INCLUDE_CAMERA}" = true ]; then
  build_camera
fi

cat <<EOF
Done building the local images.

To run the tests enter:

scripts/testing/test-software.sh
EOF
