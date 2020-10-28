#!/usr/bin/env bash
set -eu

# Pass arguments
exec gosu ${PANUSER} /usr/bin/env zsh -ic "$@"
