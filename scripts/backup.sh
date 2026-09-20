#!/usr/bin/env bash
# Kinetiq backup wrapper.
# Runs `kinetiq backup` inside the running container so it uses the same DB.
# Suggested host cron:
#   15 3 * * * cd /home/ubuntu/Kinetiq && ./scripts/backup.sh >> /home/ubuntu/kinetiq-backup.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose exec -T kinetiq kinetiq backup
