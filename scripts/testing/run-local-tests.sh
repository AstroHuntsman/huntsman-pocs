#!/usr/bin/env bash
set -eu

BUILD_ONLY=false
TEST_ONLY=false
# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --build-only)
            BUILD_ONLY=true
            shift
            ;;
        --test-only)
            TEST_ONLY=true
            shift
            ;;
        -h|--help)
            echo "Utility for building and running the docker test environment"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --build-only: Only build the test image, don't run it."
            echo "  --test-only: Only run the tests. Don't build the image."
            echo "  -h, --help              Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done


if [ $TEST_ONLY == "false" ]; then
    docker build \
        --file "${HUNTSMAN_POCS}/tests/Dockerfile" \
        --build-arg image_url="${DOCKER_USER}/panoptes-pocs" \
        --build-arg image_tag=v0.7.8 \
        --tag "${DOCKER_USER}/huntsman-pocs-test:${DOCKER_TAG}" \
        "${HUNTSMAN_POCS}"
fi

if [ $BUILD_ONLY == "false" ]; then
    logs_dir="${HUNTSMAN_POCS}/tests/logs"
    build_dir="${HUNTSMAN_POCS}/tests/build"
    rm -rf "$logs_dir" "$build_dir"
    # Pyro uses a weird user, so we have to 777
    mkdir -p "$logs_dir" && chmod -R 777 "$logs_dir"
    mkdir -p "$build_dir" && chmod -R 777 "$build_dir"

    docker run --rm -it\
        --init \
        --user 1000:1000 \
        --env-file "${HUNTSMAN_POCS}/tests/huntsman.test.env" \
        -v "${HUNTSMAN_POCS}/tests/logs:/huntsman/logs" \
        -v "${HUNTSMAN_POCS}/tests/build:/huntsman/build" \
        "${DOCKER_USER}/huntsman-pocs-test:${DOCKER_TAG}" \
        pytest
fi
