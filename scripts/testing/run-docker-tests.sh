#!/usr/bin/env bash

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

mkdir -p logs

HUNTSMAN_DIR="${HUNTSMAN_DIR:-/var/huntsman}"
HUNTSMAN_POCS="${HUNTSMAN_POCS:-${HUNTSMAN_DIR}/huntsman-pocs}"

docker run --rm -i \
  --init \
  --network "host" \
  --env-file "./tests/env" \
  -v "${PWD}":/var/huntsman/huntsman-pocs \
  -v "${PWD}/logs":/var/huntsman/logs \
  huntsman-pocs:develop \
  "${HUNTSMAN_DIR}/huntsman-pocs/scripts/testing/run-local-tests.sh"

echo "test output dir ${PANLOG}:"
ls "${PWD}/logs/huntsman-testing.log"
