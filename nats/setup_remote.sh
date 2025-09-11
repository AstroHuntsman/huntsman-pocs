# Script file to start the remote server's consumers
# set -euo pipefail NOTE: we don't want to fail because we might make a running session and then die without closing it.

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

check_pass=0
if [ -z "${NATS_SCRIPT_DIR}" ]; then
    echo "ERROR: NATS_SCRIPT_DIR not set. Please source huntsman.env. See nats/README.md for details"
    check_pass=1
fi
if [ -z "${HUNTSMAN_REMOTE_HOST}" ]; then
    echo "ERROR: HUNTSMAN_REMOTE_HOST not set. Please source huntsman.env. See nats/README.md for details"
    check_pass=1
fi
if [ -z "${NATS_REMOTE_SCRIPT_DIR}" ]; then
    echo "ERROR: NATS_REMOTE_SCRIPT_DIR not set. Please source huntsman.env. See nats/README.md for details"
    check_pass=1
fi
if [ "$check_pass" -eq 1 ]; then
    exit
fi

echo "Proceeding with the following configuration:"
echo "  NATS_SCRIPT_DIR:        ${NATS_SCRIPT_DIR}"
echo "  NATS_REMOTE_SCRIPT_DIR: ${NATS_REMOTE_SCRIPT_DIR}"
echo "  HUNTSMAN_REMOTE_HOST:    ${HUNTSMAN_REMOTE_HOST}"

# Test remote connectivity
if ssh -o ConnectTimeout=10 -o BatchMode=yes "${HUNTSMAN_REMOTE_HOST}" false; then
    echo "SSH authentication to remote host failed. Please investigate."
fi

echo "Copying scripts from local NATS_SCRIPT_DIR to remote NATS_REMOTE_SCRIPT_DIR:"
scp $NATS_SCRIPT_DIR/* huntsman@$HUNTSMAN_REMOTE_HOST:$NATS_REMOTE_SCRIPT_DIR

SESSION_NAME="Remote-Consumers"
byobu kill-session -t $SESSION_NAME 2>/dev/null || true # Kill any existing session with the same name
byobu new-session -d -s $SESSION_NAME -c $NATS_SCRIPT_DIR # Create new byobu session

echo "Running consumers on remote server"
byobu send-keys -t $SESSION_NAME "ssh -o ConnectTimeout=10 -o BatchMode=yes huntsman@$HUNTSMAN_REMOTE_HOST" Enter
byobu send-keys -t $SESSION_NAME "export NATS_REMOTE_SCRIPT_DIR=$NATS_REMOTE_SCRIPT_DIR" Enter
byobu send-keys -t $SESSION_NAME "echo 'Starting consumers..' && python3 $NATS_REMOTE_SCRIPT_DIR/start_consumers.py" Enter


# echo "Beginning consumers on remote host..."
# ssh -i $HUNTSMAN_REMOTE_KEY huntsman@$HUNTSMAN_REMOTE_IP python3 $NATS_REMOTE_SCRIPT_DIR/start_consumers.py

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
