#!/bin/bash
set -eo pipefail

PANOPTES_UTILS=true
PANOPTES_POCS=true
HUNTSMAN_POCS_IMAGE=true
HUNTSMAN_CAMERA=true
PUSH=true
NOCACHE=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-pan-utils)
            PANOPTES_UTILS=false
            shift
            ;;
        --no-pan-pocs)
            PANOPTES_POCS=false
            shift
            ;;
        --no-hun-pocs)
            HUNTSMAN_POCS_IMAGE=false
            shift
            ;;
        --no-hun-cam)
            HUNTSMAN_CAMERA=false
            shift
            ;;
        --no-push)
            PUSH=false
            shift
            ;;
        --no-cache)
            NOCACHE="--no-cache"
            shift
            ;;
        -h|--help)
            echo "Utility for building and pushing Huntsman essential Docker images"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --no-pan-utils: Don't build or push the panoptes-utils image"
            echo "  --no-pan-pocs: Don't build or push the panoptes-pocs image"
            echo "  --no-hun-pocs: Don't build or push the huntsman-pocs image"
            echo "  --no-hun-cam: Don't build or push the huntsman-camera image"
            echo "  --no-push: Build but don't push any of the images created"
            echo "  --no-cache: Use the --no-cache option when building images"
            echo "  -h, --help              Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Make any necessary checks before proceesing
pre_script_checks(){
    CHECK_PASS=0
    # Environment variables
    if [ -z "$DOCKER_USER" ]; then
        echo "ERROR: DOCKER_USER not set. Please source huntsman.env. See wiki/Environment-and-Configuration for details"
        CHECK_PASS=1
    fi
    if [ -z "$DOCKER_TAG" ]; then
        echo "ERROR: DOCKER_TAG not set. Please source huntsman.env. See wiki/Environment-and-Configuration for details"
        CHECK_PASS=1
    fi
    if [ -z "$HUNTSMAN_POCS" ]; then
        echo "ERROR: HUNTSMAN_POCS not set. Please source huntsman.env. See wiki/Environment-and-Configuration for details"
        CHECK_PASS=1
    fi

    # DOCKER PAT if pushing
    if [ "$PUSH" == "true" ]; then
        if [ -z "$DOCKER_PAT" ]; then
            echo "ERROR: DOCKER_PAT not set. Please source huntsman.env. See wiki/Environment-and-Configuration for details"
            CHECK_PASS=1
        fi
    fi

    # Check dependencies
    if ! command_exists docker; then
        echo "Error: docker is not installed. Please install it first:"
        CHECK_PASS=1
    fi


}

pre_script_checks
if [ "$CHECK_PASS" -eq 1 ]; then
    echo "Checks failed with error(s). Exiting..."
    exit 1
fi
set -u # Turn on unknown variable errors

# Login to docker if push is on
if [ "$PUSH" == "true" ]; then
    echo "${DOCKER_PAT}" | docker login -u "${DOCKER_USER}" --password-stdin
fi

echo "Proceeding with the following settings:"
echo "  Build PANOPTES-UTILS:   ${PANOPTES_UTILS}"
echo "  Build PANOPTES-POCS:    ${PANOPTES_POCS}"
echo "  Build HUNTSMAN-POCS:    ${HUNTSMAN_POCS_IMAGE}"
echo "  Build HUNTSMAN-CAMERA:  ${HUNTSMAN_CAMERA}"
echo "  Push images to remote:  ${PUSH}"
echo "  Cache:  ${NOCACHE}"
echo ""

PANOPTES_UTILS_NAME=${DOCKER_USER}/panoptes-utils
PANOPTES_POCS_NAME=${DOCKER_USER}/panoptes-pocs
HUNTSMAN_POCS_NAME=${DOCKER_USER}/huntsman-pocs
HUNTSMAN_CAMERA_NAME=${DOCKER_USER}/huntsman-pocs-camera

# Builds
if  [ "${PANOPTES_UTILS}" == "true" ]; then
    echo "Building PANOPTES-UTILS image: ${PANOPTES_UTILS_NAME}"
    cd "${HUNTSMAN_POCS}/docker/panoptes-utils"
    docker build "${NOCACHE}" --tag "${PANOPTES_UTILS_NAME}:v0.2.35" .
    if [ "${PUSH}" == "true" ]; then
        echo "Pushing PANOPTES-UTILS image: ${PANOPTES_UTILS_NAME}"
        docker push "${PANOPTES_UTILS_NAME}:v0.2.35"
    fi
    cd -
fi
if  [ "${PANOPTES_POCS}" == "true" ]; then
    echo "Building PANOPTES-POCS image: ${PANOPTES_POCS_NAME}"
    cd "${HUNTSMAN_POCS}/docker/panoptes-pocs"
    docker build "${NOCACHE}" --tag "${PANOPTES_POCS_NAME}:v0.7.8" .
    if [ "${PUSH}" == "true" ]; then
        echo "Pushing PANOPTES-POCS image: ${PANOPTES_POCS_NAME}"
        docker push "${PANOPTES_POCS_NAME}:v0.7.8"
    fi
    cd -
fi
if  [ "${HUNTSMAN_POCS_IMAGE}" == "true" ]; then
    echo "Building HUNTSMN-POCS image: ${HUNTSMAN_POCS_NAME}"
    cd "${HUNTSMAN_POCS}/docker/huntsman-pocs"
    docker build "${NOCACHE}" --tag "${HUNTSMAN_POCS_NAME}:${DOCKER_TAG}" \
        -f "${HUNTSMAN_POCS}/docker/huntsman-pocs/Dockerfile" "${HUNTSMAN_POCS}"
    if [ "${PUSH}" == "true" ]; then
        echo "Pushing HUNTSMAN-POCS image: ${HUNTSMAN_POCS_NAME}"
        docker push "${HUNTSMAN_POCS_NAME}:${DOCKER_TAG}"
    fi
    cd -
fi
if  [ "${HUNTSMAN_CAMERA}" == "true" ]; then
    echo "Building HUNTSMAN-CAMERA image: ${HUNTSMAN_CAMERA_NAME}"
    cd "${HUNTSMAN_POCS}/docker/camera"
    docker build "${NOCACHE}" --tag "${HUNTSMAN_CAMERA_NAME}:${DOCKER_TAG}" \
        --build-arg image_url="${HUNTSMAN_POCS_NAME}" \
        --build-arg image_tag="${DOCKER_TAG}" \
        -f "${HUNTSMAN_POCS}/docker/camera/Dockerfile" "${HUNTSMAN_POCS}"
    if [ "${PUSH}" == "true" ]; then
        echo "Pushing HUNTSMAN-CAMERA image: ${HUNTSMAN_CAMERA_NAME}"
        docker push "${HUNTSMAN_CAMERA_NAME}:${DOCKER_TAG}"
    fi
    cd -
fi

echo "Done"

