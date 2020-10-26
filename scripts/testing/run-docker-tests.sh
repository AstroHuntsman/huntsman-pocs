#!/usr/bin/env bash
set -eu

clear

cat <<EOF
Beginning test of huntsman-pocs software. This software is run inside a virtualized docker
container that has all of the required dependencies installed.

This will start a single docker container, mapping the host HUNTSMAN_DIR=${HUNTSMAN_DIR} into the running docker
container, which allows for testing of any local changes.

You can view the output for the tests in a separate terminal:

tail -F ${PWD}/logs/huntsman-testing.log

Tests will begin in 5 seconds. Press Ctrl-c to cancel.
EOF

sleep "${SLEEP_TIME:-5}"

# Specify directories inside the docker container
HUNTSMAN_DIR_DOCKER="${HUNTSMAN_DIR_DOCKER:-/var/huntsman}"
HUNTSMAN_POCS_DOCKER="${HUNTSMAN_POCS_DOCKER:-${HUNTSMAN_DIR_DOCKER}/huntsman-pocs}"
HUNTSMAN_COVDIR_DOCKER="${HUNTSMAN_COVDIR_DOCKER}:-${HUNTSMAN_DIR_DOCKER}/coverage"

# Run tests inside docker container
docker-compose -f ${HUNTSMAN_POCS}/docker/testing/docker-compose.yml run --rm \
  -e "HUNTSMAN_COVDIR=${HUNTSMAN_DIR_DOCKER}" \
  -e "HUNTSMAN_POCS=${HUNTSMAN_POCS_DOCKER}" \
  -v "${HUNTSMAN_COVDIR}:${HUNTSMAN_COVDIR_DOCKER}" \
  python_tests /var/huntsman/huntsman-pocs/scripts/testing/run_local_tests.sh
