#!/usr/bin/env bash
set -eu

# Run tests inside docker container
docker-compose -f ${HUNTSMAN_POCS}/docker/testing/docker-compose.yml run --rm \
  -v ${HUNTSMAN_POCS}:/var/huntsman/huntsman-pocs python_tests
