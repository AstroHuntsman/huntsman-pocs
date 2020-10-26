#!/usr/bin/env bash
set -eu

# chown huntsman-pocs
# sudo chown -R ${PANUSER} ${HUNTSMAN_POCS}

# Pass arguments
exec gosu ${PANUSER} /usr/bin/env zsh -ic "$@"
