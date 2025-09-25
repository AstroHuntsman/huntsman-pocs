#!/usr/bin/env bash
set -e

# Run tests inside docker container
docker compose -f docker-compose.yml build --no-rm
# mkdir -p logs && chmod -R 777 logs
# mkdir -p build && chmod -R 777 build
docker compose -f docker-compose.yml run --rm python_tests
