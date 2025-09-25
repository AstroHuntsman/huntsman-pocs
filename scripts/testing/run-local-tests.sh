#!/usr/bin/env bash
set -e

# Run tests inside docker container
docker-compose -f tests/docker-compose.yml build --no-rm
mkdir -p logs && chmod -R 666 logs
mkdir -p build && chmod -R 666 build
docker-compose -f tests/docker-compose.yml run --rm python_tests
