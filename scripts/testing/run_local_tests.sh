#!/usr/bin/env bash
set -e

# Run tests inside docker container
docker-compose -f docker/testing/docker-compose.yml run --rm python_tests
