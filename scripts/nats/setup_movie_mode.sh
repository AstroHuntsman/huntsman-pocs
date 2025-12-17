#!/bin/bash

BYOBU_SESSION="huntsman-nats"
SKIP_CONFIRMATION=false
# Generate Image names from env variables
POCS_IMAGE=${DOCKER_USER}/huntsman-pocs:${DOCKER_TAG}
CAMERA_IMAGE=${DOCKER_USER}/huntsman-pocs-camera:${DOCKER_TAG}

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
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --session-name NAME                 Use custom session name (default: ${BYOBU_SESSION})"
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


# Test remote to a host using hostname set in ~/.ssh/config
test_ssh_connectivity(){
    local hostname="$1"

    if ! ssh -o ConnectTimeout=10 -o BatchMode=yes "${hostname}" true; then
        return 1
    fi
    return 0
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
    if [ -z "${HUNTSMAN_CONTROL_HOST}" ]; then
        echo "ERROR: HUNTSMAN_CONTROL_HOST not set. Please source huntsman.env. See wiki for details"
        CHECK_PASS=1
    fi
    if [ -z "${HUNTSMAN_CONTROL_IP}" ]; then
        echo "ERROR: HUNTSMAN_CONTROL_IP not set. Please source huntsman.env. See wiki for details"
        CHECK_PASS=1
    fi
    if [ -z "${BYOBU_SESSION}" ]; then
        echo "ERROR: BYOBU_SESSION not set. Please source huntsman.env. See wiki for details"
        CHECK_PASS=1
    fi
    if [ -z "${IMAGES_SHARE_DIR}" ]; then
        echo "ERROR: IMAGES_SHARE_DIR not set. Please source huntsman.env. See wiki for details"
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

    # Test remote connectivity
    if ! test_ssh_connectivity "${HUNTSMAN_REMOTE_HOST}"; then
        echo "ERROR: SSH authentication to remote host failed: '${HUNTSMAN_REMOTE_HOST}'. Please investigate."
        CHECK_PASS=1
    fi

    # Test connectivity of selected cameras
    for row in $(echo "${HUNTSMAN_CAMERAS}" | jq -c '.[]'); do
        local hostname=$(echo "$row" | jq -r '.hostname')
        local use=$(echo "$row" | jq -r '.use')
        if [ "$use" == "true" ] && ! test_ssh_connectivity "${hostname}"; then
            echo "ERROR: SSH authentication to camera host failed: '${hostname}'. Please investigate."
            CHECK_PASS=1
        fi
    done

}

check_containers_running(){
    # Names of required containers
    # These can be changed when their names don't make sense anymore
    containers=(
        "pyro-name-server-mm"
        "pocs-control-mm"
        "pocs-config-server-mm"
        "nats-jetstream-mm"
    )
    echo "Checking required containers..."

    all_ok=true
    for c in "${containers[@]}"; do
        if docker ps --format '{{.Names}}' | grep -q "^${c}$"; then
            echo "${c} is running"
        else
            echo "${c} is NOT running"
            all_ok=false
        fi
    done

    if [ "$all_ok" = true ]; then
        echo "All containers are running."
        CHECK_PASS=0
    else
        echo "One or more containers are NOT running."
        CHECK_PASS=1
    fi
}


# Setup the monitoring window. Runs on the (local) control server. Monitors memory usage and manages it.
monitoring_setup(){
    local monitor_output="/huntsman/images" # Location inside the docker contianer to write to
    echo "Creating NATS streams..."

    # Start the window
    byobu rename-window -t "$BYOBU_SESSION":0 "Monitor"
    local idx=$(get_window_idx "Monitor") || exit 1 # Sanity check - should be 0
    local bind_mounts="-v '${IMAGES_SHARE_DIR}:${monitor_output}'"
    local docker_args="--network host --pull=always -it --rm"

    byobu split-window -h -t "$BYOBU_SESSION":"$idx" # Split the window into two columns (vertical split)
    create_streams="echo 'Creating NATS streams...' &&  docker run ${docker_args} --name streams-mm ${POCS_IMAGE} 'python scripts/nats/manage_streams.py -n ${NATS_NUM_STREAMS}' -m 10_000_000_000"
    memory_monitor="echo 'Starting Memory Monitor...' &&  docker run ${docker_args} ${bind_mounts} --name monitor-mm ${POCS_IMAGE} 'python scripts/nats/start_monitor.py -f ${monitor_output}/memory_status.json -o ${monitor_output}/monitor_stats.json'"
    byobu send-keys -t "$BYOBU_SESSION":"$idx.0" "${create_streams} && ${memory_monitor}" Enter
    sleep 8
    echo "Waiting for streams to be created..."
    echo "Starting memory monitor in left pane..."

    echo "Starting storage manager in right pane..."
    byobu send-keys -t "$BYOBU_SESSION":"${idx}.1" "sleep 10" Enter # Sleep to wait for stream setup
    byobu send-keys -t "$BYOBU_SESSION":"${idx}.1" "echo 'Starting Storage Manager...' &&  docker run ${docker_args} ${bind_mounts} --name storage-manager-mm ${POCS_IMAGE} 'python scripts/nats/start_storage_manager.py' -f ${monitor_output}/memory_status.json -m ${MEMORY_THRESHOLD} -i 10" Enter
}

# Setup the consumers window. Runs on the remote server
remote_host_setup(){
    local consumer_output="/huntsman/Projects/huntsman/images" # Location inside the docker contianer to write to
    local remote_images="/var/huntsman/images" # Location on the remote server to write to
    echo "Running consumers on remote server..."

    byobu new-window -t "$BYOBU_SESSION" -n "Remote Consumers"
    local idx=$(get_window_idx "Remote Consumers") || exit 1

    local run="docker run \
        --network host \
        --pull=always  \
        -it --rm  \
        --name consumers-mm \
        -v '${remote_images}:${consumer_output}' \
        ${POCS_IMAGE} \
        'python scripts/nats/start_consumers.py -w ${NATS_NUM_WRITER_THREADS} -n ${NATS_NUM_CONSUMERS}' -o ${consumer_output}"
    byobu send-keys -t "$BYOBU_SESSION":"$idx" "ssh -o ConnectTimeout=10 -o BatchMode=yes huntsman@$HUNTSMAN_REMOTE_HOST" Enter
    byobu send-keys -t "$BYOBU_SESSION":"$idx" "sudo mount -t nfs ${HUNTSMAN_CONTROL_IP}:${IMAGES_SHARE_DIR} ${remote_images}" Enter # Mount the network volume
    byobu send-keys -t "$BYOBU_SESSION":"$idx" "sleep 10" Enter # Sleep to make sure the streams have been initialised
    byobu send-keys -t "$BYOBU_SESSION":"$idx" "echo 'Starting consumers..' && ${run}" Enter
}


# Setup the cameras windows. Runs on each camera server.
camera_setup(){
    # Where images are written to inside the container
    local container_images="/huntsman/images"
    # Where images are written to on the camera server. Image writing isn't done here when using movie mode, but this is needed for access to the memory status.
    local camera_images="/var/huntsman/images"
    local hostname="$1"
    local cam_num="$2"

    echo "Creating new window for camera ${cam_num}"
    byobu new-window -t "$BYOBU_SESSION" -n "Cam ${cam_num}"
    local idx=$(get_window_idx "Cam ${cam_num}")
    byobu split-window -h -t "$BYOBU_SESSION":"$idx" # Split the window into two columns (vertical split)
    byobu send-keys -t "$BYOBU_SESSION":"$idx.0" "ssh -o ConnectTimeout=10 -o BatchMode=yes ${hostname}" Enter
    byobu send-keys -t "$BYOBU_SESSION":"$idx.1" "ssh -o ConnectTimeout=10 -o BatchMode=yes ${hostname}" Enter

    # The docker run command to run the contianer
    local run="docker run \
        --name camera \
        -it --rm \
        --privileged \
        --network host \
        --pull=always \
        -e PANDIR=/var/huntsman \
        -e MEMORY_STATUS_FILE=${container_images}/memory_status.json \
        -e PANOPTES_CONFIG_HOST=${HUNTSMAN_CONTROL_IP} \
        -e PANOPTES_CONFIG_PORT=6563 \
        -e TZ=\"Australia/Sydney\" \
        -v '${camera_images}:${container_images}' \
        -v '/var/huntsman/logs:/huntsman/logs' \
        -v /dev:/dev \
        --group-add dialout \
        --group-add sudo \
        --group-add plugdev \
        --group-add users \
        ${CAMERA_IMAGE} \
        'huntsman-pyro --verbose service --service-class huntsman.pocs.camera.pyro.service.CameraService'"
    byobu send-keys -t "$BYOBU_SESSION":"$idx.0" "source ~/.bash_profile && sleep 10" Enter
    byobu send-keys -t "$BYOBU_SESSION":"$idx.0" "docker ps -q --filter 'name=camera' | grep -q . && docker stop camera" # Stop any camera service if it's running
    byobu send-keys -t "$BYOBU_SESSION":"$idx.0" "docker system prune -f --volumes" Enter # Delete old volumes
    byobu send-keys -t "$BYOBU_SESSION":"$idx.0" "sudo chmod 777 -R /var/huntsman/logs" Enter # Allow log writing
    byobu send-keys -t "$BYOBU_SESSION":"$idx.0" "mkdir -p ${camera_images} && sudo umount ${camera_images}" Enter # Ensure the mount directory exists. Unmount anything on there.
    byobu send-keys -t "$BYOBU_SESSION":"$idx.0" "sudo mount -t nfs ${HUNTSMAN_CONTROL_IP}:${IMAGES_SHARE_DIR} ${camera_images}" Enter # Mount the network volume
    byobu send-keys -t "$BYOBU_SESSION":"$idx.0" "${run}" Enter # Run the service setup script
    byobu send-keys -t "$BYOBU_SESSION":"$idx.1" "echo 'Sleeping 30 seconds...' && sleep 30 && tail -F -n 10000 /var/huntsman/logs/panoptes.log" Enter
}


## Pre-Script Assurances ##
pre_script_checks
if [ "$CHECK_PASS" -eq 1 ]; then
    echo "Checks failed with error(s). Exiting..."
    exit 1
fi
check_containers_running
if [ "$CHECK_PASS" -eq 1 ]; then
    echo "Container checks failed with error(s). Exiting..."
    exit 1
fi


# Set undefined variable error ONLY. If something errors, we don't want to stop the whole system from proceeding.
set -u

echo "----------- Configuration -----------"
echo "  BYOBU_SESSION:                  ${BYOBU_SESSION}"
echo "  HUNTSMAN_POCS:                  ${HUNTSMAN_POCS}"
echo "  HUNTSMAN_REMOTE_HOST:           ${HUNTSMAN_REMOTE_HOST}"
echo "  POCS_IMAGE_NAME:                ${POCS_IMAGE}"
echo "  CAMERA_IMAGE_NAME:              ${CAMERA_IMAGE}"

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


## Main system setup ##
# Kill any existing byobu session with the same name and start a new one
byobu kill-session -t "$BYOBU_SESSION" 2>/dev/null || true
byobu new-session -d -s "$BYOBU_SESSION" -c "$HUNTSMAN_POCS/nats"
monitoring_setup
remote_host_setup

# Set up all cameras that are enabled (set to 'true' in the huntsman.env)
for row in $(echo "${HUNTSMAN_CAMERAS}" | jq -c '.[]'); do # All cameras as defined in huntsman.env
    hostname=$(echo "$row" | jq -r '.hostname')
    use=$(echo "$row" | jq -r '.use')
    cam_num=$(echo "$row" | jq -r '.num')
    if [ "$use" == "true" ]; then
        camera_setup $hostname $cam_num
    else
        echo "Skipping camera setup: Camera ${cam_num}"
    fi
done


echo ""
echo "Setup complete! Byobu session '${BYOBU_SESSION}' is ready."
echo ""
echo "Useful byobu commands:"
echo "  F6 or Ctrl+A+D     - Detach from session"
echo "  byobu attach -t ${BYOBU_SESSION} - (Re)attach to session"
echo "  byobu list-sessions - List all sessions"
echo "  Alt+Left/Right     - Switch between panes"
echo "  F2                 - Create new window"
echo "  F3/F4              - Previous/Next window"
echo ""
