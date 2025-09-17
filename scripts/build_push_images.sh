#!/bin/bash
set -eo pipefail

panoptes_utils=true
panoptes_pocs=true
huntsman_pocs=true
huntsman_camera=true
push=true
nocache=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-pan-utils)
            panoptes_utils=false
            shift
            ;;
        --no-pan-pocs)
            panoptes_pocs=false
            shift
            ;;
        --no-hun-pocs)
            huntsman_pocs=false
            shift
            ;;
        --no-hun-cam)
            huntsman_camera=false
            shift
            ;;
        --no-push)
            push=false
            shift
            ;;
        --no-cache)
            nocache="--no-cache"
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
        echo "ERROR: DOCKER_USER not set. Please source huntsman.env. See nats/README.md for details"
        CHECK_PASS=1
    fi
    if [ -z "$DOCKER_TAG" ]; then
        echo "ERROR: DOCKER_TAG not set. Please source huntsman.env. See nats/README.md for details"
        CHECK_PASS=1
    fi
    if [ -z "$HUNTSMAN_POCS" ]; then
        echo "ERROR: HUNTSMAN_POCS not set. Please source huntsman.env. See nats/README.md for details"
        CHECK_PASS=1
    fi

    # DOCKER PAT if pushing
    if [ $push == "true" ]; then
        if [ -z "$DOCKER_PAT" ]; then
            echo "ERROR: DOCKER_PAT not set. Please source huntsman.env. See nats/README.md for details"
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
set -u # Turn on unknown variable errors

# Login to docker if push is on
if [ $push == "true" ]; then
    echo "${DOCKER_PAT}" | docker login -u ${DOCKER_USER} --password-stdin
fi

echo "Proceeding with the following settings:"
echo "  Build PANOPTES-UTILS:   ${panoptes_utils}"
echo "  Build PANOPTES-POCS:    ${panoptes_pocs}"
echo "  Build HUNTSMAN-POCS:    ${huntsman_pocs}"
echo "  Build HUNTSMAN-CAMERA:  ${huntsman_camera}"
echo "  Push images to remote:  ${push}"
echo "  Cache:  ${nocache}"
echo ""

panoptes_utils_name=${DOCKER_USER}/panoptes-utils
panoptes_pocs_name=${DOCKER_USER}/panoptes-pocs
huntsman_pocs_name=${DOCKER_USER}/huntsman-pocs
huntsman_camera_name=${DOCKER_USER}/huntsman-pocs-camera

# Builds
if  [ ${panoptes_utils} == "true" ]; then
    echo "Building PANOPTES-UTILS image: ${panoptes_utils_name}"
    cd "${HUNTSMAN_POCS}/docker/panoptes-utils"
    docker build ${nocache} --tag ${panoptes_utils_name}:v0.2.35 .
    if [ ${push} == "true" ]; then
        echo "Pushing PANOPTES-UTILS image: ${panoptes_utils_name}"
        docker push ${panoptes_utils_name}:v0.2.35
    fi
    cd -
fi
if  [ ${panoptes_pocs} == "true" ]; then
    echo "Building PANOPTES-POCS image: ${panoptes_pocs_name}"
    cd "${HUNTSMAN_POCS}/docker/panoptes-pocs"
    docker build ${nocache} --tag ${panoptes_pocs_name}:v0.7.8 .
    if [ ${push} == "true" ]; then
        echo "Pushing PANOPTES-POCS image: ${panoptes_pocs_name}"
        docker push ${panoptes_pocs_name}:v0.7.8
    fi
    cd -
fi
if  [ ${huntsman_pocs} == "true" ]; then
    echo "Building HUNTSMN-POCS image: ${huntsman_pocs_name}"
    cd "${HUNTSMAN_POCS}/docker/huntsman-pocs"
    docker build ${nocache} --tag ${huntsman_pocs_name}:${DOCKER_TAG} \
        -f "${HUNTSMAN_POCS}/docker/huntsman-pocs/Dockerfile" "${HUNTSMAN_POCS}"
    if [ ${push} == "true" ]; then
        echo "Pushing HUNTSMAN-POCS image: ${huntsman_pocs_name}"
        docker push ${huntsman_pocs_name}:${DOCKER_TAG}
    fi
    cd -
fi
if  [ ${huntsman_camera} == "true" ]; then
    echo "Building HUNTSMAN-CAMERA image: ${huntsman_camera_name}"
    cd "${HUNTSMAN_POCS}/docker/camera"
    docker build ${nocache} --tag ${huntsman_camera_name}:${DOCKER_TAG} \
        --build-arg image_url=${huntsman_pocs_name} \
        --build-arg image_tag=${DOCKER_TAG} \
        -f "${HUNTSMAN_POCS}/docker/camera/Dockerfile" "${HUNTSMAN_POCS}"
    if [ ${push} == "true" ]; then
        echo "Pushing HUNTSMAN-CAMERA image: ${huntsman_camera_name}"
        docker push ${huntsman_camera_name}:${DOCKER_TAG}
    fi
    cd -
fi

echo "Done"

