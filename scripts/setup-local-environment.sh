#!/usr/bin/env bash
set -e

TAG="${1:-latest}"
POCS_TAG="${1:-latest}"

INCLUDE_CAMERA=${INCLUDE_UTILS:-false}
INCLUDE_DEVELOPER=${INCLUDE_DEVELOPER:-false}

HUNTSMAN_POCS=${HUNTSMAN_POCS:-/var/huntsman/huntsman-pocs}
_POCS_IMAGE_URL="gcr.io/panoptes-exp/panoptes-pocs:${POCS_TAG}"
_HUNTS_POCS_IMAGE_URL="huntsmanarray/huntsman-pocs:${TAG}"

echo "Setting up local environment."
cd "${HUNTSMAN_POCS}"

# Builds a local image for testing, etc. Also the base of other images.
build_develop() {
  echo "Building local ${_HUNTS_POCS_IMAGE_URL} from ${_POCS_IMAGE_URL} in ${HUNTSMAN_POCS}."
  docker build \
    -t "huntsman-pocs:${TAG}" \
    -f "${HUNTSMAN_POCS}/docker/Dockerfile" \
    "${HUNTSMAN_POCS}"

  # Use the local image below now that we have built it.
  _HUNTS_POCS_IMAGE_URL="huntsman-pocs:${TAG}"
}

build_camera() {
  echo "Building local huntsman-pocs-camera:${TAG} from ${_HUNTS_POCS_IMAGE_URL} in ${HUNTSMAN_POCS}"
  docker build \
    -t "huntsman-pocs-camera:${TAG}" \
    --build-arg "image_url=${_HUNTS_POCS_IMAGE_URL}" \
    --build-arg "arch=x86" \
    -f "${HUNTSMAN_POCS}/docker/camera/Dockerfile" \
    "${HUNTSMAN_POCS}"
}

build_developer() {
  echo "Building local huntsman-pocs:${TAG} from ${_HUNTS_POCS_IMAGE_URL} in ${HUNTSMAN_POCS}"
  docker build \
    -t "huntsman-pocs:${TAG}" \
    -f "${HUNTSMAN_POCS}/docker/developer/Dockerfile" \
    "${HUNTSMAN_POCS}"
}

####################################################################################
# Script logic below
####################################################################################

build_develop

if [ "${INCLUDE_CAMERA}" = true ]; then
  build_camera
fi

if [ "${INCLUDE_DEVELOPER}" = true ]; then
  build_developer
fi

cat <<EOF
Done building the local images.

To run the tests enter:

scripts/testing/test-software.sh
EOF
