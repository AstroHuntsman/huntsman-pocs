#!/usr/bin/env bash
set -eu

BUILD=true
TEST=true
PYTEST_ARGS=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-build)
            BUILD=false
            shift
            ;;
        --no-test)
            TEST=false
            shift
            ;;
        -h|--help)
            echo "Utility for building and running the docker test environment."
            echo "Accepts arbitrary pytest arguments. Prefix test filenames with 'tests/'"
            echo "e.g -s tests/test_camera.py"
            echo ""
            echo "Usage: $0 [OPTIONS] [PYTEST_ARGS]"
            echo "Options:"
            echo "  --no-build: Don't build the test image."
            echo "  --no-test: Don't run the tests."
            echo "  -h, --help              Show this help message"
            echo "PYTEST_ARGS: Arbitrary arguments to pass to pytest."
            exit 0
            ;;
        *)
            PYTEST_ARGS+=("$1")
            shift
            ;;
    esac
done

echo "Proceeding with the following configuration:"
echo "  Build Image: ${BUILD}"
echo "  Run Test: ${TEST}"
if [ "${TEST}" == "true" ]; then
    echo "PYTEST_ARGS: ${PYTEST_ARGS[*]}"
fi
echo ""

if [ $BUILD == "true" ]; then
    echo "Building Image..."
    docker build \
        --file "${HUNTSMAN_POCS}/tests/Dockerfile" \
        --build-arg image_url="${DOCKER_USER}/panoptes-pocs" \
        --build-arg image_tag=v0.7.8 \
        --tag "${DOCKER_USER}/huntsman-pocs-test:${DOCKER_TAG}" \
        --progress=plain \
        "${HUNTSMAN_POCS}"
fi

echo ""
if [ $TEST == "true" ]; then
    echo "Creating necessary directories for tests"
    logs_dir="${HUNTSMAN_POCS}/tests/logs"
    build_dir="${HUNTSMAN_POCS}/tests/build"
    rm -rf "$logs_dir" "$build_dir"
    # Pyro uses a weird user, so we have to 777
    mkdir -p "$logs_dir" && chmod -R 777 "$logs_dir"
    mkdir -p "$build_dir" && chmod -R 777 "$build_dir"


    docker rm huntsman-pocs-test
    echo "Running tests..."
    docker run -it \
        --name huntsman-pocs-test \
        -v "$logs_dir:/huntsman/logs" \
        -v "$build_dir:/huntsman/build" \
        --env-file "${HUNTSMAN_POCS}/tests/huntsman.test.env" \
        "${DOCKER_USER}/huntsman-pocs-test:${DOCKER_TAG}" \
        "/bin/bash -c 'pytest ${PYTEST_ARGS[*]}'"

fi
