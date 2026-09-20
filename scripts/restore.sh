#!/usr/bin/env bash
# Restore Kinetiq from a snapshot. Stops the server, restores, then starts.
set -euo pipefail
if [[ $# -lt 1 ]]; then
  echo "usage: $0 <path-inside-/data/backups>" >&2
  exit 2
fi
snap="$1"
cd "$(dirname "$0")/.."
docker compose stop kinetiq
docker compose run --rm --no-deps kinetiq kinetiq restore "$snap"
docker compose start kinetiq
