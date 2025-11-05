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
        echo "ERROR: HUNTSMAN_POCS not set. Please source huntsman.env. See nats/README.md for details"
        CHECK_PASS=1
    fi
    if [ -z "${HUNTSMAN_REMOTE_HOST}" ]; then
        echo "ERROR: HUNTSMAN_REMOTE_HOST not set. Please source huntsman.env. See nats/README.md for details"
        CHECK_PASS=1
    fi
    if [ -z "${HUNTSMAN_CONTROL_HOST}" ]; then
        echo "ERROR: HUNTSMAN_CONTROL_HOST not set. Please source huntsman.env. See nats/README.md for details"
        CHECK_PASS=1
    fi
    if [ -z "${NATS_REMOTE_SCRIPT_DIR}" ]; then
        echo "ERROR: NATS_REMOTE_SCRIPT_DIR not set. Please source huntsman.env. See nats/README.md for details"
        CHECK_PASS=1
    fi
    if [ -z "${NATS_REMOTE_PYTHON_EXECUTABLE}" ]; then
        echo "ERROR: NATS_REMOTE_PYTHON_EXECUTABLE not set. Please source huntsman.env. See nats/README.md for details"
        CHECK_PASS=1
    fi
    if [ -z "${BYOBU_SESSION}" ]; then
        echo "ERROR: BYOBU_SESSION not set. Please source huntsman.env. See nats/README.md for details"
        CHECK_PASS=1
    fi
    if [ -z "${DOCKER_USER}" ]; then
        echo "ERROR: DOCKER_USER not set. Please source huntsman.env. See nats/README.md for details"
        CHECK_PASS=1
    fi
    if [ -z "${DOCKER_TAG}" ]; then
        echo "ERROR: DOCKER_TAG not set. Please source huntsman.env. See nats/README.md for details"
        CHECK_PASS=1
    fi
    if [ -z "${MEMORY_THRESHOLD}" ]; then
        echo "ERROR: MEMORY_THRESHOLD not set. Please source huntsman.env. See nats/README.md for details"
        CHECK_PASS=1
    fi
    if [ -z "${MEMORY_STATUS_FILE}" ]; then
        echo "ERROR: MEMORY_STATUS_FILE not set. Please source huntsman.env. See nats/README.md for details"
        CHECK_PASS=1
    fi
    # Check dependencies
    if ! command_exists byobu; then
        echo "Error: byobu is not installed. Please install it first:"
        echo "sudo apt-get install byobu"
        CHECK_PASS=1
    fi

    if ! command_exists python; then
        echo "Error: python is not available"
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

    # Check if Python scripts exist
    for script in create_streams.py memory_monitor.py storage_manager.py consumer.py; do
        if [ ! -f "$HUNTSMAN_POCS/nats/$script" ]; then
            echo "Error: $script not found in $HUNTSMAN_POCS/nats"
            CHECK_PASS=1
        fi
    done

}



# Setup the monitoring window. Runs on the (local) control server. Monitors memory usage and manages it.
monitoring_setup(){
    echo "Creating NATS streams..."
    # Run create_streams.py and wait for it to complete
    # byobu send-keys -t "$BYOBU_SESSION" "echo 'Creating NATS streams...' && python create_streams.py && echo 'Streams created successfully!'" Enter
    # byobu send-keys -t "$BYOBU_SESSION" "echo 'Pulling Huntsaman-POCS container' && docker pull ${POCS_IMAGE}" Enter
    byobu send-keys -t "$BYOBU_SESSION" "echo 'Creating NATS streams...' && docker run --pull=always ${POCS_IMAGE} 'python nats/create_streams.py'" Enter
    echo "Waiting for streams to be created..."
    sleep 8

    # Start the window
    byobu rename-window -t "$BYOBU_SESSION":0 "Monitor"
    local idx=$(get_window_idx "Monitor") || exit 1 # Sanity check - should be 0

    byobu split-window -h -t "$BYOBU_SESSION":"$idx" # Split the window into two columns (vertical split)
    echo "Starting memory monitor in left pane..."
    byobu send-keys -t "$BYOBU_SESSION":"${idx}.0" "echo 'Starting Memory Monitor...' && docker run --pull=always ${POCS_IMAGE} 'python nats/memory_monitor.py -m ${MEMORY_THRESHOLD}' -f ${MEMORY_STATUS_FILE}" Enter
    echo "Starting storage manager in right pane..."
    byobu send-keys -t "$BYOBU_SESSION":"${idx}.1" "echo 'Starting Storage Manager...' && docker run --pull=always ${POCS_IMAGE} 'python nats/storage_manager.py'" Enter
}

# Setup the consumers window. Runs on the remote server
remote_host_setup(){
    # echo "Copying scripts from local HUNTSMAN_POCS/nats to remote NATS_REMOTE_SCRIPT_DIR:"
    # scp $HUNTSMAN_POCS/nats/* huntsman@$HUNTSMAN_REMOTE_HOST:$NATS_REMOTE_SCRIPT_DIR

    echo "Running consumers on remote server..."
    byobu new-window -t "$BYOBU_SESSION" -n "Remote Consumers"
    local idx=$(get_window_idx "Remote Consumers") || exit 1

    byobu send-keys -t "$BYOBU_SESSION":"$idx" "ssh -o ConnectTimeout=10 -o BatchMode=yes huntsman@$HUNTSMAN_REMOTE_HOST" Enter
    # TODO: Test with docker container to make sure the below python setup can be removed
    # byobu send-keys -t "$BYOBU_SESSION":$idx "export NATS_REMOTE_SCRIPT_DIR=$NATS_REMOTE_SCRIPT_DIR" Enter
    # byobu send-keys -t "$BYOBU_SESSION":$idx "export NATS_REMOTE_PYTHON_EXECUTABLE=$NATS_REMOTE_PYTHON_EXECUTABLE" Enter
    # byobu send-keys -t "$BYOBU_SESSION":$idx "echo 'Starting consumers..' && $NATS_REMOTE_PYTHON_EXECUTABLE $NATS_REMOTE_SCRIPT_DIR/start_consumers.py" Enter
    byobu send-keys -t "$BYOBU_SESSION":"$idx" "echo 'Starting consumers..' && docker run --pull=always ${POCS_IMAGE} 'python nats/start_consumers.py'" Enter
}


# Setup the cameras windows. Runs on each camera server.
camera_setup(){
    local hostname
    local cam_num
    # echo "Copying scripts from local HUNTSMAN_POCS/camera/scripts to remote camera /var/huntsman/scripts"
    # scp $HUNTSMAN_POCS/camera/scripts/* $hostname:/var/huntsman/scripts

    echo "Creating new window for camera ${cam_num}"
    byobu new-window -t "$BYOBU_SESSION" -n "Cam ${cam_num}"
    local idx=$(get_window_idx "Cam ${cam_num}")
    byobu split-window -h -t "$BYOBU_SESSION":"$idx" # Split the window into two columns (vertical split)
    byobu send-keys -t "$BYOBU_SESSION":"$idx.0" "ssh -o ConnectTimeout=10 -o BatchMode=yes ${hostname}" Enter
    byobu send-keys -t "$BYOBU_SESSION":"$idx.1" "ssh -o ConnectTimeout=10 -o BatchMode=yes ${hostname}" Enter

    # The docker run command to run the contianer
    local run="docker run \
        --pull=always \
        --name camera \
        -it --rm \
        --privileged \
        --network host \
        -e PANDIR=/var/huntsman \
        -e PANOPTES_CONFIG_HOST= \
        -e PANOPTES_CONFIG_PORT=6563 \
        -e TZ="Australia/Sydney" \
        -v '${PANDIR}/images:/huntsman/images' \
        -v '${PANDIR}/logs:/huntsman/logs' \
        -v /dev/bus/usb:/dev/bus/usb \
        --group-add dialout \
        --group-add sudo \
        --group-add plugdev \
        --group-add users \
        ${CAMERA_IMAGE} \
        huntsman-pyro --verbose service --service-class huntsman.pocs.camera.pyro.service.CameraService"
    # byobu send-keys -t "$BYOBU_SESSION":"$idx.0" "/bin/bash /var/huntsman/scripts/run-camera-service.sh" Enter # Run the service setup script
    byobu send-keys -t "$BYOBU_SESSION":"$idx.0" "source ~/.bash_profile && sleep 10" Enter
    byobu send-keys -t "$BYOBU_SESSION":"$idx.0" "docker ps -q --filter 'name=camera' | grep -q . && docker stop camera" # Stop any camera service if it's running
    byobu send-keys -t "$BYOBU_SESSION":"$idx.0" "docker system prune -f --volumes" Enter # Delete old volumes
    # TODO: Check if mounting network volume is necessary for moviemode
    byobu send-keys -t "$BYOBU_SESSION":"$idx.0" "mkdir -p ${PANDIR}/images && sudo unmount ${PANDIR}/images && sudo mounts -t nfs ${HUNTSMAN_CONTROL_HOST}:${PANDIR}/images ${PANDIR}/images" Enter # Mount the network volume
    byobu send-keys -t "$BYOBU_SESSION":"$idx.0" "${run}" Enter # Run the service setup script
    byobu send-keys -t "$BYOBU_SESSION":"$idx.1" "echo 'Sleeping 30 seconds...' && sleep 30 && tail -F -n 10000 /var/huntsman/logs/huntsman.log" Enter
}


## Pre-Script Assurances ##
pre_script_checks
if [ "$CHECK_PASS" -eq 1 ]; then
    echo "Checks failed with error(s). Exiting..."
    exit 1
fi


# Set undefined variable error ONLY. If something errors, we don't want to stop the whole system from proceeding.
set -u

echo "----------- Configuration -----------"
echo "  BYOBU_SESSION:                  ${BYOBU_SESSION}"
echo "  HUNTSMAN_POCS:                  ${HUNTSMAN_POCS}"
echo "  NATS_REMOTE_SCRIPT_DIR:         ${NATS_REMOTE_SCRIPT_DIR}"
echo "  NATS_REMOTE_PYTHON_EXECUTABLE:  ${NATS_REMOTE_PYTHON_EXECUTABLE}"
echo "  HUNTSMAN_REMOTE_HOST:           ${HUNTSMAN_REMOTE_HOST}"
echo "  POCS_IMAGE_NAME:                ${POCS_IMAGE}"
echo "  CAMERA_IMAGE_NAME:              ${CAMERA_IMAGE}"

if [ $SKIP_CONFIRMATION == "false" ]; then
    if ! user_confirm "Continue with this configuration? [y/n]"; then
        echo "Exiting..."
        exit 1
    else
        echo "Continuing..."
    fi
fi


# TODO: Check for the required services from the config docker compose

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
for row in $(echo "${HUNTSMAN_CAMERAS}" | jq -c '.[]'); do # All cameras as defined in huntsman.env
    hostname=$(echo "$row" | jq -r '.hostname')
    use=$(echo "$row" | jq -r '.use')
    cam_num=$(echo "$row" | jq -r '.cam_num')
    if [ "$use" == "true" ]; then
        camera_setup hostname cam_num
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
