#!/usr/bin/env bash
set -euo pipefail

help(){
    echo "Usage: setup-local-environment [OPTIONS]"
    echo "Ensure that the DOCKER_BUILD_TAG and HUNTSMAN_POCS environment variables are set"
    echo ""
    echo "Options:"
    echo "  --skip-panoptes     Skip building of panoptes-pocs image"
    echo "  --skip-huntsman     Skip building of huntsman-pocs image"
    echo "  --skip-camera       Skip building of huntsman-pocs-camera image"
    echo "  -h, --help              Show this help message"
    echo ""
}

check=0
if [ -z $DOCKER_BUILD_TAG ]; then
    echo "DOCKER_BUILD_TAG is not assigned"
    check=1
fi
if [ -z $HUNTSMAN_POCS ]; then
    echo "HUNTSMAN_POCS is not assigned"
    check=1
fi
if [ "${check}" -eq 1 ]; then
    echo "Cannot continue. Please address the above issues and rerun"
    exit
fi

# Parse command line arguments
skip_panoptes=false
skip_huntsman=false
skip_camera=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-panoptes)
            skip_panoptes=true
            shift
            ;;
        --skip-huntsman)
            skip_huntsman=true
            shift
            ;;
        --skip-camera)
            skip_camera=true
            shift
            ;;
        -h|--help)
            help
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            help
            exit 1
            ;;
    esac
done

echo "Setting up local environment."

# Builds a local image for the PANOPTES items.
# build_panoptes_utils(){
#     echo "Building local panoptes utils image"
#     cd "${HUNTSMAN_POCS}/docker/panoptes-utils"
#     docker build -t "panoptes-utils:${DOCKER_BUILD_TAG}" .
# }

build_panoptes_pocs() {
    echo "Building local panoptes pocs image"
    docker build -t "panoptes-pocs:${DOCKER_BUILD_TAG}" \
        --build-arg "image_url=docker.io/huntsmanarray/panoptes-utils" \
        --build-arg "image_tag=v0.2.35" \
        -f "${HUNTSMAN_POCS}/docker/panoptes-pocs/Dockerfile" "${HUNTSMAN_POCS}/docker/panoptes-pocs"

}

# Builds a local image for testing, etc. Also the base of other images.
build_huntsman_pocs() {
    echo "Building local huntsman pocs image"
    docker build -t "huntsman-pocs:${DOCKER_BUILD_TAG}" \
        --build-arg "image_url=panoptes-pocs" \
        --build-arg "image_tag=${DOCKER_BUILD_TAG}" \
        -f "${HUNTSMAN_POCS}/docker/huntsman-pocs/Dockerfile" "${HUNTSMAN_POCS}"
}

build_huntsman_camera() {
    echo "Building local huntsman camera image"
    docker build -t "huntsman-pocs-camera:${DOCKER_BUILD_TAG}" \
        --build-arg "image_url=huntsman-pocs" \
        --build-arg "image_tag=${DOCKER_BUILD_TAG}" \
        -f "${HUNTSMAN_POCS}/docker/camera/Dockerfile" "${HUNTSMAN_POCS}"
}

####################################################################################
# Script logic below
####################################################################################

if [ $skip_panoptes == "false" ]; then
    build_panoptes_pocs
else
    echo "Skipping PANOPTES-POCS image build"
fi
if [ $skip_huntsman == "false" ]; then
    build_huntsman_pocs
else
    echo "Skipping Huntsman-POCS image build"
fi
if [ $skip_camera == "false" ]; then
    build_huntsman_camera
else
    echo "Skipping Huntsman-POCS-camera image build"
fi

cat <<EOF
Done building the local images.

To run the tests enter:

scripts/testing/run-local-tests.sh
EOF
