#!/usr/bin/env bash
# Prints the 8-char recipe hash for one row of variants.json, as used in the
# immutable tag <comfyui>-<variant>-r<hash>. Shared by the build and promote
# workflows so both always hash the same files.
#
#   scripts/recipe_hash.sh cu130
set -euo pipefail
cd "$(dirname "$0")/.."

RECIPE_FILES=(Dockerfile nodes.lock.yaml models.lock.yaml required_nodes.txt scripts/install_nodes.py
              scripts/models.py scripts/smoke.py docker/start.sh)

row=$(jq -c --arg v "$1" '.[] | select(.variant == $v)' variants.json)
[[ -n "$row" ]] || { echo "unknown variant: $1" >&2; exit 1; }
{ cat "${RECIPE_FILES[@]}"; echo "$row"; } | sha256sum | cut -c1-8
