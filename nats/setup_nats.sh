#!/bin/bash
set -u
# set -euo pipefail NOTE: we don't want to fail because we might make a running session and then die without closing it.

# Enhanced NATS Setup Script with Byobu
# Usage: ./setup_manager_monitoring.sh [--skip-create-streams] [--session-name NAME]

SKIP_CREATE_STREAMS=false
BYOBU_SESSION="huntsman-nats"

# Parse command line arguments
# TODO: Decide how to do the session naming
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-create-streams)
            SKIP_CREATE_STREAMS=true
            shift
            ;;
        --session-name)
            BYOBU_SESSION="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --skip-create-streams    Skip running create_streams.py"
            echo "  --session-name NAME      Use custom session name (default: ${BYOBU_SESSION})"
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

# Look for a byobu window and return its index
# e.g. idx=$(get_window_idx "Window Name") || exit 1
get_window_idx() {
    local window_name="$1"
    local idx
    idx=$(byobu list-windows -t "$BYOBU_SESSION" | grep -F "$window_name" | cut -d: -f1)
    if [ -z "$idx" ]; then
        echo "Window '$window_name' not found" >&2
        return 1
    fi
    echo "$idx"
}

# Make any necessary checks before proceesing
pre_script_checks(){
    # Environment variables
    CHECK_PASS=0
    if [ -z "$NATS_SCRIPT_DIR" ]; then
        echo "ERROR: NATS_SCRIPT_DIR not set. Please source huntsman.env. See nats/README.md for details"
        CHECK_PASS=1
    fi
    if [ -z "${HUNTSMAN_REMOTE_HOST}" ]; then
        echo "ERROR: HUNTSMAN_REMOTE_HOST not set. Please source huntsman.env. See nats/README.md for details"
        CHECK_PASS=1
    fi
    if [ -z "${NATS_REMOTE_SCRIPT_DIR}" ]; then
        echo "ERROR: NATS_REMOTE_SCRIPT_DIR not set. Please source huntsman.env. See nats/README.md for details"
        CHECK_PASS=1
    fi
    if [ -z "${BYOBU_SESSION}" ]; then
        echo "ERROR: BYOBU_SESSION not set. Please source huntsman.env. See nats/README.md for details"
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
    if ! ssh -o ConnectTimeout=10 -o BatchMode=yes "${HUNTSMAN_REMOTE_HOST}" true; then
        echo "ERROR: SSH authentication to remote host failed: '${HUNTSMAN_REMOTE_HOST}'. Please investigate."
        CHECK_PASS=1
    fi

    # Check if Python scripts exist
    for script in create_streams.py memory_monitor.py storage_manager.py consumer.py; do
        if [ ! -f "$NATS_SCRIPT_DIR/$script" ]; then
            echo "Error: $script not found in $NATS_SCRIPT_DIR"
            CHECK_PASS=1
        fi
    done
}

# Setup the monitoring window. Runs on the (local) control server
monitoring_setup(){
    if [ "$SKIP_CREATE_STREAMS" = false ]; then
        echo "Creating NATS streams..."
        # Run create_streams.py and wait for it to complete
        byobu send-keys -t $BYOBU_SESSION "echo 'Creating NATS streams...' && python create_streams.py && echo 'Streams created successfully!'" Enter
        echo "Waiting for streams to be created..."
        sleep 8
    else
        echo "Skipping stream creation..."
    fi

    # Start the window
    byobu rename-window -t $BYOBU_SESSION:0 "Monitor"
    local idx=$(get_window_idx "Monitor") || exit 1 # Sanity check - should be 0

    byobu split-window -h -t $BYOBU_SESSION:$idx # Split the window into two columns (vertical split)
    echo "Starting memory monitor in left pane..."
    byobu send-keys -t $BYOBU_SESSION:"${idx}.0" "echo 'Starting Memory Monitor...' && python $NATS_SCRIPT_DIR/memory_monitor.py" Enter
    echo "Starting storage manager in right pane..."
    byobu send-keys -t $BYOBU_SESSION:"${idx}.1" "echo 'Starting Storage Manager...' && python $NATS_SCRIPT_DIR/storage_manager.py" Enter
}

# Setup the consumers window. Runs on the remote server
remote_host_setup(){
    echo "Copying scripts from local NATS_SCRIPT_DIR to remote NATS_REMOTE_SCRIPT_DIR:"
    scp $NATS_SCRIPT_DIR/* huntsman@$HUNTSMAN_REMOTE_HOST:$NATS_REMOTE_SCRIPT_DIR

    echo "Running consumers on remote server..."
    byobu new-window -t $BYOBU_SESSION -n "Remote Consumers"
    local idx=$(get_window_idx "Remote Consumers") || exit 1

    byobu send-keys -t $BYOBU_SESSION:$idx "ssh -o ConnectTimeout=10 -o BatchMode=yes huntsman@$HUNTSMAN_REMOTE_HOST" Enter
    byobu send-keys -t $BYOBU_SESSION:$idx "export NATS_REMOTE_SCRIPT_DIR=$NATS_REMOTE_SCRIPT_DIR" Enter
    byobu send-keys -t $BYOBU_SESSION:$idx "echo 'Starting consumers..' && python3 $NATS_REMOTE_SCRIPT_DIR/start_consumers.py" Enter
}

pre_script_checks
if [ "$CHECK_PASS" -eq 1 ]; then
    echo "Checks failed with error(s). Exiting..."
    exit 1
fi

echo "Proceeding with the following configuration:"
echo "  NATS_SCRIPT_DIR:        ${NATS_SCRIPT_DIR}"
echo "  NATS_REMOTE_SCRIPT_DIR: ${NATS_REMOTE_SCRIPT_DIR}"
echo "  HUNTSMAN_REMOTE_HOST:   ${HUNTSMAN_REMOTE_HOST}"
echo "  BYOBU_SESSION:     ${BYOBU_SESSION}"

# Kill any existing session with the same name and start a new one
byobu kill-session -t $BYOBU_SESSION 2>/dev/null || true
byobu new-session -d -s $BYOBU_SESSION -c $NATS_SCRIPT_DIR

monitoring_setup
remote_host_setup



echo ""
echo "Setup complete! Byobu session '$BYOBU_SESSION' is ready."
echo ""
echo "Useful byobu commands:"
echo "  F6 or Ctrl+A+D     - Detach from session"
echo "  byobu attach -t $BYOBU_SESSION - (Re)attach to session"
echo "  byobu list-sessions - List all sessions"
echo "  Alt+Left/Right     - Switch between panes"
echo "  F2                 - Create new window"
echo "  F3/F4              - Previous/Next window"
echo ""
# echo "Attaching to session..."
# sleep 2

# Attach to the session
# byobu attach-session -t $BYOBU_SESSION
