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

sleep "${SLEEP_TIME:-5}"

mkdir -p logs

HUNTSMAN_DIR="${HUNTSMAN_DIR:-/var/huntsman}"
HUNTSMAN_POCS="${HUNTSMAN_POCS:-${HUNTSMAN_DIR}/huntsman-pocs}"

docker run --rm -i \
  --init \
  --network "host" \
  -e "PANOPTES_CONFIG_FILE=${HUNTSMAN_DIR}/huntsman-pocs/tests/testing.yaml" \
  -e "PANOPTES_CONFIG_HOST=0.0.0.0" \
  -e "PANOPTES_CONFIG_PORT=8765" \
  -v "${PWD}":/var/huntsman/huntsman-pocs \
  -v "${PWD}/logs":/var/huntsman/logs \
  huntsman-pocs:develop \
  "${HUNTSMAN_DIR}/huntsman-pocs/scripts/testing/run-tests.sh"

echo "test output dir ${HUNTSMAN_DIR}/logs:"
ls "${HUNTSMAN_DIR}/logs/huntsman-testing.log"