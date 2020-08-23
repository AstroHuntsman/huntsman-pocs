#!/usr/bin/env bash

clear

cat <<EOF
Beginning test of huntsman-pocs software. This software is run inside a virtualized docker
container that has all of the required dependencies installed.

This will start a single docker container, mapping the host HUNTSMAN_DIR=${HUNTSMAN_DIR} into the running docker
container, which allows for testing of any local changes.

You can view the output for the tests in a separate terminal:

tail -F ${HUNTSMAN_DIR}/logs/huntsman-testing.log

Tests will begin in 5 seconds. Press Ctrl-c to cancel.
EOF

SLEEP_TIME=${1:-5}

sleep "${SLEEP_TIME}"

HUNTSMAN_DIR="${HUNTSMAN_DIR:-/var/huntsman}"
HUNTSMAN_POCS="${HUNTSMAN_POCS:-/var/huntsman/huntsman-pocs}"

docker run --rm -it \
  --init \
  -v "${HUNTSMAN_POCS}":/var/huntsman/huntsman-pocs \
  -v "${HUNTSMAN_DIR}/logs":/var/huntsman/logs \
  huntsman-pocs:develop \
  "/var/huntsman/huntsman-pocs/scripts/testing/run-tests.sh"
