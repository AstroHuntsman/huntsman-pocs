#!/usr/bin/env bash
set -eu

# Run tests inside docker container
docker-compose -f ${HUNTSMAN_POCS}/docker/testing/docker-compose.yml run --rm \
  python_tests /var/huntsman/huntsman-pocs/scripts/testing/run_local_tests.sh
