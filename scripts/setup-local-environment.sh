#!/usr/bin/env bash
set -e

POCS_TAG="${1:-latest}"

HUNTSMAN_POCS=${HUNTSMAN_POCS:-/var/huntsman/huntsman-pocs}
_POCS_IMAGE_URL="gcr.io/panoptes-exp/panoptes-pocs:${POCS_TAG}"

echo "Setting up local environment."
cd "${HUNTSMAN_POCS}"

build_develop() {
  echo "Building local huntsman-pocs:develop from ${_POCS_IMAGE_URL} in ${HUNTSMAN_POCS}"
  docker build \
    -t "huntsman-pocs:develop" \
    -f "${HUNTSMAN_POCS}/docker/Dockerfile" \
    "${HUNTSMAN_POCS}"
}

####################################################################################
# Script logic below
####################################################################################

build_develop

cat <<EOF
Done building the local images.

To run the tests enter:

scripts/testing/test-software.sh
EOF
