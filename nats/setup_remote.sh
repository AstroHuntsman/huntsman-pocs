# Script file to start the remote server's consumers
set -euo pipefail

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

check_pass=0
if [ -z "$NATS_SCRIPT_DIR" ]; then
    echo "ERROR: NATS_SCRIPT_DIR not set. Please source huntsman.env. See nats/README.md for details"
    check_pass=1
fi
if [ -z "$HUNTSMAN_REMOTE_KEY" ]; then
    echo "ERROR: HUNTSMAN_REMOTE_KEY not set. Please source huntsman.env. See nats/README.md for details"
    check_pass=1
fi
if [ -z "$HUNTSMAN_REMOTE_IP" ]; then
    echo "ERROR: HUNTSMAN_REMOTE_IP not set. Please source huntsman.env. See nats/README.md for details"
    check_pass=1
fi
if [ -z "$NATS_REMOTE_SCRIPT_DIR" ]; then
    echo "ERROR: NATS_REMOTE_SCRIPT_DIR not set. Please source huntsman.env. See nats/README.md for details"
    check_pass=1
fi
if [ -f "$HUNTSMAN_REMOTE_KEY" ]; then
    echo "ERROR: HUNTSMAN_REMOTE_KEY: '${HUNTSMAN_REMOTE_KEY}' does not exist on this system. Please investigate"
    check_pass=1
fi
if [ check_pass -eq 1 ]; then
    exit
fi

echo "Proceeding with the following configuration:"
echo "  NATS_SCRIPT_DIR:        ${NATS_SCRIPT_DIR}"
echo "  NATS_REMOTE_SCRIPT_DIR: ${NATS_REMOTE_SCRIPT_DIR}"
echo "  HUNTSMAN_REMOTE_KEY:    ${HUNTSMAN_REMOTE_KEY}"
echo "  HUNTSMAN_REMOTE_IP:     ${HUNTSMAN_REMOTE_IP}"
echo "  HUNTSMAN_REMOTE_KEY:    ${HUNTSMAN_REMOTE_KEY}"

# Test remote connectivity
if ssh -i ${HUNTSMAN_REMOTE_KEY} -o ConnectTimeout=10  -o BatchMode=yes "${HUNTSMAN_REMOTE_HOST}" false; then
    echo "SSH authentication to remote host failed. Please investigate."
fi

echo "Copying scripts from local NATS_SCRIPT_DIR to remote NATS_REMOTE_SCRIPT_DIR:"
scp -i $HUNTSMAN_REMOTE_KEY $NATS_SCRIPT_DIR/* huntsman@$HUNTSMAN_REMOTE_IP:$NATS_REMOTE_SCRIPT_DIR

echo "Beginning consumers on remote host..."
ssh -i $HUNTSMAN_REMOTE_KEY huntsman@$HUNTSMAN_REMOTE_IP python3 $NATS_REMOTE_SCRIPT_DIR/start_consumers.py

