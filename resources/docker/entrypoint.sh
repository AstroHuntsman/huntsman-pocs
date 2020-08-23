#!/usr/bin/env bash
set -e

# Pass arguments
exec gosu huntsman /usr/bin/env zsh -ic "$@"
