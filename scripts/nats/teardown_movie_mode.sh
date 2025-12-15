#!/bin/bash

BYOBU_SESSION="huntsman-nats"
SKIP_CONFIRMATION=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --session-name)
            BYOBU_SESSION="$2"
            shift 2
            ;;
        --skip-confirmation)
            SKIP_CONFIRMATION=true
            shift
            ;;
        -h|--help)
            echo "Tears down the movie mode environment and cleans up after itself"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --session-name NAME                 The session name to tear down (default: ${BYOBU_SESSION})"
            echo "  --skip-confirmation                 Don't ask for confirmation before proceeding"
            echo "  -h, --help                          Show this help message"
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


# Look for a byobu window and return its index
# e.g. idx=$(get_window_idx "Window Name") || exit 1
get_window_idx() {
    local window_name="$1"
    local idx=$(byobu list-windows -t "$BYOBU_SESSION" | grep -F "$window_name" | cut -d: -f1)
    if [ -z "$idx" ]; then
        echo "Window '$window_name' not found" >&2
        return 1
    fi
    echo "$idx"
}

# Ask for Yes/No confirmation
user_confirm() {
    local prompt="$1"
    local response

    while true; do
        read -r -p "$prompt [y/n]: " response
        case "$response" in
            [Yy]|[Yy][Ee][Ss])
                return 0  # yes
                ;;
            [Nn]|[Nn][Oo])
                return 1  # no
                ;;
            *)
                echo "Please enter y (yes) or n (no)."
                ;;
        esac
    done
}

# Make any necessary checks before proceesing
pre_script_checks(){
    # Environment variables
    CHECK_PASS=0
    if [ -z "${HUNTSMAN_POCS}" ]; then
        echo "ERROR: HUNTSMAN_POCS not set. Please source huntsman.env. See wiki for details"
        CHECK_PASS=1
    fi
    if [ -z "${HUNTSMAN_REMOTE_HOST}" ]; then
        echo "ERROR: HUNTSMAN_REMOTE_HOST not set. Please source huntsman.env. See wiki for details"
        CHECK_PASS=1
    fi
    if [ -z "${BYOBU_SESSION}" ]; then
        echo "ERROR: BYOBU_SESSION not set. Please source huntsman.env. See wiki for details"
        CHECK_PASS=1
    fi
    if [ -z "${DOCKER_USER}" ]; then
        echo "ERROR: DOCKER_USER not set. Please source huntsman.env. See wiki for details"
        CHECK_PASS=1
    fi
    if [ -z "${DOCKER_TAG}" ]; then
        echo "ERROR: DOCKER_TAG not set. Please source huntsman.env. See wiki for details"
        CHECK_PASS=1
    fi
    if [ -z "${MEMORY_THRESHOLD}" ]; then
        echo "ERROR: MEMORY_THRESHOLD not set. Please source huntsman.env. See wiki for details"
        CHECK_PASS=1
    fi
    if [ -z "${MEMORY_STATUS_FILE}" ]; then
        echo "ERROR: MEMORY_STATUS_FILE not set. Please source huntsman.env. See wiki for details"
        CHECK_PASS=1
    fi
    if [ -z "${NATS_NUM_STREAMS}" ]; then
        echo "ERROR: NATS_NUM_STREAMS not set. Please source huntsman.env. See wiki for details"
        CHECK_PASS=1
    fi
    if [ -z "${NATS_NUM_WRITER_THREADS}" ]; then
        echo "ERROR: NATS_NUM_WRITER_THREADS not set. Please source huntsman.env. See wiki for details"
        CHECK_PASS=1
    fi
    if [ -z "${NATS_NUM_CONSUMERS}" ]; then
        echo "ERROR: NATS_NUM_CONSUMERS not set. Please source huntsman.env. See wiki for details"
        CHECK_PASS=1
    fi

    # Check dependencies
    if ! command_exists byobu; then
        echo "Error: byobu is not installed. Please install it first:"
        echo "sudo apt-get install byobu"
        CHECK_PASS=1
    fi

}

# Generates the commands to clean up the docker containers/images
# Stops all containers partially matching (with grep) the input image name. Then deletes the container
cleanup_containers_command(){
    local image=$1
    # The first set of docker commands lists all containers, then matches these to the $image string, selects the container ID and executes the stop/rm command
    # The second set of docker commands lists all images, then matches these to the $image string, selects the image ID and executes the rmi command
    cat <<EOF
echo 'Cleaning containers matching: $image'
docker ps -a --format '{{.ID}} {{.Image}}' | grep '$image' | awk '{print \$1}' | xargs -r docker stop >/dev/null 2>&1 || true
docker ps -a --format '{{.ID}} {{.Image}}' | grep '$image' | awk '{print \$1}' | xargs -r docker rm -f >/dev/null 2>&1 || true

echo 'Cleaned containers on' \$(hostname)
EOF
}

cleanup_images_command(){
    local image=$1
    cat <<EOF
echo 'Cleaning images matching: $image'
docker images --format '{{.ID}} {{.Repository}}:{{.Tag}}' | grep '$image' | awk '{print \$1}' | sort -u | xargs -r docker rmi -f >/dev/null 2>&1 || true

echo 'Cleaned images on' \$(hostname)
EOF

}

pre_script_checks

# Set undefined variable error ONLY. If something errors, we don't want to stop the whole system from proceeding.
set -u

echo "----------- Configuration -----------"
echo "  BYOBU_SESSION:                  ${BYOBU_SESSION}"
echo "  HUNTSMAN_POCS:                  ${HUNTSMAN_POCS}"
echo "  HUNTSMAN_REMOTE_HOST:           ${HUNTSMAN_REMOTE_HOST}"

if [ $SKIP_CONFIRMATION == "false" ]; then
    if ! user_confirm "Continue with this configuration?"; then
        echo "Exiting..."
        exit 1
    else
        echo "Continuing..."
    fi
fi


pkill -f "ssh -.*R.*4222" # Kill any exisitng tunnel
ssh -f -N -R 4222:localhost:4222 "$HUNTSMAN_REMOTE_HOST"
# Check if SSH tunnel is active
if ! ssh "${HUNTSMAN_REMOTE_HOST}" "nc -z localhost 4222"; then
    echo "ERROR: SSH tunnel test failed"
    exit 1
fi


echo "Tearing down byobu session: $BYOBU_SESSION"
byobu kill-session -t "$BYOBU_SESSION" 2>/dev/null || true

# Assuming this is being run on the control host
echo "Removing images and containers for ${HUNTSMAN_CONTROL_HOST}"
bash -c "$(cleanup_containers_command ${DOCKER_USER}/huntsman-pocs:${DOCKER_TAG})"

# Remote host cleanup
echo "Removing images and containers for ${HUNTSMAN_REMOTE_HOST}"
ssh ${HUNTSMAN_REMOTE_HOST} bash -c "$(cleanup_containers_command ${DOCKER_USER}/huntsman-pocs:${DOCKER_TAG})"

# Camera cleanup
for row in $(echo "${HUNTSMAN_CAMERAS}" | jq -c '.[]'); do # All cameras as defined in huntsman.env
    hostname=$(echo "$row" | jq -r '.hostname')
    use=$(echo "$row" | jq -r '.use')
    cam_num=$(echo "$row" | jq -r '.num')
    if [ "$use" == "true" ]; then
        echo "Removing images and containers for ${hostname}"
        ssh ${hostname} bash -c "$(cleanup_containers_command ${DOCKER_USER}/huntsman-pocs-camera:${DOCKER_TAG})"
        ssh ${hostname} bash -c "$(cleanup_images_command ${DOCKER_USER}/huntsman-pocs-camera:${DOCKER_TAG})"
        echo "Cleaning up Docker artifacts"
        ssh ${hostname} bash -c \"docker system prune --all -f\"
    else
        echo "Skipping camera teardown: Camera ${cam_num}"
    fi

done



echo ""
echo "Teardown complete!"
