#!/usr/bin/env bash
set -eu

# Specify directories inside the docker container
HUNTSMAN_DIR_DOCKER="${HUNTSMAN_DIR_DOCKER:-/var/huntsman}"
HUNTSMAN_POCS_DOCKER="${HUNTSMAN_POCS_DOCKER:-${HUNTSMAN_DIR_DOCKER}/huntsman-pocs}"
HUNTSMAN_COVDIR_DOCKER="${HUNTSMAN_COVDIR_DOCKER:-${HUNTSMAN_DIR_DOCKER}/coverage}"

# Run tests inside docker container
docker-compose -f ${HUNTSMAN_POCS}/docker/testing/docker-compose.yml run --rm \
  -e "HUNTSMAN_COVDIR=${HUNTSMAN_DIR_DOCKER}" \
  -e "HUNTSMAN_POCS=${HUNTSMAN_POCS_DOCKER}" \
  -v "${HUNTSMAN_COVDIR}:${HUNTSMAN_COVDIR_DOCKER}" \
  python_tests /var/huntsman/huntsman-pocs/scripts/testing/run_local_tests.sh
