#!/usr/bin/env bash
set -eu

# chown volumes
sudo chown -R huntsman ${HUNTSMAN_POCS}

# Pass arguments
exec gosu huntsman /usr/bin/env zsh -ic "$@"
