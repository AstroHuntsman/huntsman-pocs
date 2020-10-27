#!/usr/bin/env bash
set -eu

# Run tests inside docker container
docker-compose -f ${HUNTSMAN_POCS}/docker/testing/docker-compose.yml run --rm \
  -v ${HUNTSMAN_POCS}:/var/huntsman_pocs \
  python_tests /var/huntsman/huntsman-pocs/scripts/testing/run_local_tests.sh
