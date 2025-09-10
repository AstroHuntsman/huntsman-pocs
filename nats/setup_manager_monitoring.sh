#!/bin/bash

# Enhanced NATS Setup Script with Byobu
# Usage: ./setup_manager_monitoring.sh [--skip-create-streams] [--session-name NAME]

SESSION_NAME="Huntsman-Nats"
SKIP_CREATE_STREAMS=false

if [ -z "$NATS_SCRIPT_DIR" ]; then
    echo "NATS_SCRIPT_DIR not set. Please source huntsman.env. See nats/README.md for details"
fi

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-create-streams)
            SKIP_CREATE_STREAMS=true
            shift
            ;;
        --session-name)
            SESSION_NAME="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --skip-create-streams    Skip running create_streams.py"
            echo "  --session-name NAME      Use custom session name (default: nats-monitoring)"
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

# Check dependencies
if ! command_exists byobu; then
    echo "Error: byobu is not installed. Please install it first:"
    echo "sudo apt-get install byobu"
    exit 1
fi

if ! command_exists python; then
    echo "Error: python is not available"
    exit 1
fi

# Check if Python scripts exist
for script in create_streams.py memory_monitor.py storage_manager.py; do
    if [ ! -f "$NATS_SCRIPT_DIR/$script" ]; then
        echo "Error: $script not found in $NATS_SCRIPT_DIR"
        exit 1
    fi
done

echo "Starting NATS monitoring setup..."
echo "Script directory: $NATS_SCRIPT_DIR"
echo "Session name: $SESSION_NAME"

# Kill any existing session with the same name
byobu kill-session -t $SESSION_NAME 2>/dev/null || true

# Create new byobu session
byobu new-session -d -s $SESSION_NAME -c $NATS_SCRIPT_DIR

if [ "$SKIP_CREATE_STREAMS" = false ]; then
    echo "Creating NATS streams..."
    # Run create_streams.py and wait for it to complete
    byobu send-keys -t $SESSION_NAME "echo 'Creating NATS streams...' && python create_streams.py && echo 'Streams created successfully!'" Enter

    # Wait for the command to complete
    echo "Waiting for streams to be created..."
    sleep 8

    # Clear the terminal
    byobu send-keys -t $SESSION_NAME "clear" Enter
else
    echo "Skipping stream creation..."
fi


# Control Monitoring
byobu rename-window -t $SESSION:0 "Monitor"
byobu split-window -h -t $SESSION_NAME:0 # Split the window into two columns (vertical split)
echo "Starting memory monitor in left pane..."
# byobu send-keys -t $SESSION_NAME:0.0 C-c
byobu send-keys -t $SESSION_NAME:0.0 "echo 'Starting Memory Monitor...' && python $NATS_SCRIPT_DIR/memory_monitor.py" Enter
echo "Starting storage manager in right pane..."
# byobu send-keys -t $SESSION_NAME:0.1 C-c
byobu send-keys -t $SESSION_NAME:0.1 "echo 'Starting Storage Manager...' && python $NATS_SCRIPT_DIR/storage_manager.py" Enter


echo ""
echo "Setup complete! Byobu session '$SESSION_NAME' is ready."
echo ""
echo "Useful byobu commands:"
echo "  F6 or Ctrl+A+D     - Detach from session"
echo "  byobu attach -t $SESSION_NAME - Reattach to session"
echo "  byobu list-sessions - List all sessions"
echo "  Alt+Left/Right     - Switch between panes"
echo "  F2                 - Create new window"
echo "  F3/F4              - Previous/Next window"
echo ""
echo "Attaching to session..."
sleep 2

# Attach to the session
byobu attach-session -t $SESSION_NAME
