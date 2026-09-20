#!/usr/bin/env bash
# Copy backups out of the docker volume to ~/kinetiq-backups so a volume loss
# does not lose the snapshots.
set -euo pipefail
dest="${1:-$HOME/kinetiq-backups}"
mkdir -p "$dest"
cid=$(docker compose ps -q kinetiq)
if [[ -z "$cid" ]]; then
  echo "kinetiq container not running" >&2
  exit 2
fi
docker cp "$cid:/data/backups/." "$dest/"
echo "backups synced → $dest"
