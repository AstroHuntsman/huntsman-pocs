#!/usr/bin/env bash
set -e

# Pass arguments
echo "Using huntsman user."
exec gosu huntsman /usr/bin/env zsh -ic "$@"
