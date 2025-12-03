#!/bin/bash
set -eo pipefail

PANOPTES_UTILS=true
PANOPTES_POCS=true
HUNTSMAN_POCS_IMAGE=true
HUNTSMAN_CAMERA=true
PUSH=true
USECACHE=true

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

setup_builder(){
    BUILDER=fastbuilder

    # Create builder if missing
    docker buildx inspect "$BUILDER" >/dev/null 2>&1 || \
        docker buildx create --driver docker-container --name "$BUILDER"

    # Bootstrap + select builder
    docker buildx inspect "$BUILDER" --bootstrap >/dev/null
    docker buildx use "$BUILDER"
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
echo "  Cache:  ${USECACHE}"
echo ""

PANOPTES_UTILS_NAME=${DOCKER_USER}/panoptes-utils
PANOPTES_POCS_NAME=${DOCKER_USER}/panoptes-pocs
HUNTSMAN_POCS_NAME=${DOCKER_USER}/huntsman-pocs
HUNTSMAN_CAMERA_NAME=${DOCKER_USER}/huntsman-pocs-camera

docker buildx create --use


setup_builder

# Builds
if  [ "${PANOPTES_UTILS}" == "true" ]; then
    echo "Building PANOPTES-UTILS image: ${PANOPTES_UTILS_NAME}"
    cd "${HUNTSMAN_POCS}/docker/panoptes-utils"
    docker buildx build --platform linux/arm64,linux/amd64   --builder fastbuilder  --tag "${PANOPTES_UTILS_NAME}:v0.2.35" --push .
    cd -
fi
if  [ "${PANOPTES_POCS}" == "true" ]; then
    echo "Building PANOPTES-POCS image: ${PANOPTES_POCS_NAME}"
    cd "${HUNTSMAN_POCS}/docker/panoptes-pocs"
    docker buildx build --platform linux/arm64,linux/amd64  --builder fastbuilder  --tag "${PANOPTES_POCS_NAME}:v0.7.8" --push .
    cd -
fi
if  [ "${HUNTSMAN_POCS_IMAGE}" == "true" ]; then
    echo "Building HUNTSMN-POCS image: ${HUNTSMAN_POCS_NAME}"
    cd "${HUNTSMAN_POCS}/docker/huntsman-pocs"
    docker buildx build --platform linux/arm64,linux/amd64   --builder fastbuilder  --tag "${HUNTSMAN_POCS_NAME}:${DOCKER_TAG}" --push \
        -f "${HUNTSMAN_POCS}/docker/huntsman-pocs/Dockerfile" "${HUNTSMAN_POCS}" \
        # --build-arg image_url="${PANOPTES_POCS_NAME}" \
        # --build-arg image_tag="v0.7.8"
    # TODO: Fix panoptes Dockerfiles
    cd -
fi
if  [ "${HUNTSMAN_CAMERA}" == "true" ]; then
    echo "Building HUNTSMAN-CAMERA image: ${HUNTSMAN_CAMERA_NAME}"
    cd "${HUNTSMAN_POCS}/docker/camera"
    docker buildx build --platform linux/arm64  --builder fastbuilder --tag "${HUNTSMAN_CAMERA_NAME}:${DOCKER_TAG}" --push \
        --build-arg image_url="${HUNTSMAN_POCS_NAME}" \
        --build-arg image_tag="${DOCKER_TAG}" \
        -f "${HUNTSMAN_POCS}/docker/camera/Dockerfile" "${HUNTSMAN_POCS}"
    cd -
fi

echo "Done"

