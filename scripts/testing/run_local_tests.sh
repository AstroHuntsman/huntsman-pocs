#!/usr/bin/env bash
set -e

# Run tests inside docker container
docker-compose -f tests/docker-compose.yml build --no-rm
docker-compose -f tests/docker-compose.yml run --rm python_tests
