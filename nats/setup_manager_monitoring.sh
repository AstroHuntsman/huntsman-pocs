#!/bin/bash

# NATS Setup Script with Byobu
# This script creates streams, then runs memory monitor and storage manager in split terminals

SCRIPT_DIR="/var/huntsman/huntsman-pocs/nats"
SESSION_NAME="nats-monitoring"

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check if byobu is installed
if ! command_exists byobu; then
    echo "Error: byobu is not installed. Please install it first:"
    echo "sudo apt-get install byobu"
    exit 1
fi

# Check if Python scripts exist
if [ ! -f "$SCRIPT_DIR/create_streams.py" ]; then
    echo "Error: create_streams.py not found in $SCRIPT_DIR"
    exit 1
fi

if [ ! -f "$SCRIPT_DIR/memory_monitor.py" ]; then
    echo "Error: memory_monitor.py not found in $SCRIPT_DIR"
    exit 1
fi

if [ ! -f "$SCRIPT_DIR/storage_manager.py" ]; then
    echo "Error: storage_manager.py not found in $SCRIPT_DIR"
    exit 1
fi

echo "Starting NATS monitoring setup..."

# Kill any existing session with the same name
byobu kill-session -t $SESSION_NAME 2>/dev/null || true

# Create new byobu session and run create_streams.py first
echo "Creating streams..."
byobu new-session -d -s $SESSION_NAME -c $SCRIPT_DIR

# Run create_streams.py and wait for it to complete
byobu send-keys -t $SESSION_NAME "python create_streams.py" Enter

# Wait a bit for streams to be created (adjust as needed)
echo "Waiting for streams to be created..."
sleep 5

# Split the window into two columns (vertical split)
byobu split-window -h -t $SESSION_NAME

# In the left pane (pane 0), run memory_monitor.py
byobu send-keys -t $SESSION_NAME:0.0 "cd $SCRIPT_DIR && python memory_monitor.py" Enter

# In the right pane (pane 1), run storage_manager.py
byobu send-keys -t $SESSION_NAME:0.1 "cd $SCRIPT_DIR && python storage_manager.py" Enter

# Optionally set pane titles for clarity
byobu send-keys -t $SESSION_NAME:0.0 C-c "printf '\033]2;Memory Monitor\033\\'" Enter "python memory_monitor.py" Enter
byobu send-keys -t $SESSION_NAME:0.1 C-c "printf '\033]2;Storage Manager\033\\'" Enter "python storage_manager.py" Enter

echo "Setup complete! Attaching to byobu session..."
echo "Use Ctrl+F6 to detach from the session"
echo "Use 'byobu attach-session -t $SESSION_NAME' to reattach later"

# Attach to the session
byobu attach-session -t $SESSION_NAME


# # Basic usage - creates streams then runs monitors
# ./setup_nats_monitoring.sh

# # Skip creating streams if they already exist
# ./setup_nats_monitoring.sh --skip-create-streams

# # Use a custom session name
# ./setup_nats_monitoring.sh --session-name my-nats-session

# # Get help
# ./setup_nats_monitoring.sh --help