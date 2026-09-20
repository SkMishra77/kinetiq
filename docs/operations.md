# Kinetiq operations guide

## First-time deploy on this EC2 box

1. Open inbound TCP 80 and 443 on the security group. Keep 22.
2. Create a DuckDNS subdomain, point it at the public IP, copy the token.
3. `cp .env.example .env`; fill in `KINETIQ_MCP_PATH_TOKEN`, `KINETIQ_DOMAIN`,
   `KINETIQ_ACME_EMAIL`, `DUCKDNS_SUBDOMAIN`, `DUCKDNS_TOKEN`. `chmod 600 .env`.
4. `docker compose --profile caddy up -d --build`.
5. `curl -sS https://$KINETIQ_DOMAIN/health` → `{"status":"ok",...}`.
6. `uv run kinetiq print-url` — paste into claude.ai `+` → **Add custom connector**.

## Rotating the URL token

1. `uv run kinetiq gen-token` — copy the new value.
2. Edit `.env` (keep `chmod 600`).
3. `docker compose up -d`.
4. In claude.ai, remove the connector and re-add it with the new URL. The
   connector URL is not editable in place.

## Backups

- Daily: `scripts/backup.sh` (calls `kinetiq backup` inside the container).
  Suggested crontab line:

  ```cron
  15 3 * * * cd /home/ubuntu/Kinetiq && ./scripts/backup.sh >> /home/ubuntu/kinetiq-backup.log 2>&1
  ```

- Off-box sync: `scripts/pull-backups.sh` copies `/data/backups/*` out of the
  Docker volume to `~/kinetiq-backups/`. Point `rclone` or `aws s3 sync` at
  that directory if you want off-box copies.

- Pre-migration backups are automatic (the lifespan creates one before
  applying any pending migration).

## Restore drill

```bash
docker compose stop kinetiq
docker compose run --rm --no-deps kinetiq \
  kinetiq restore /data/backups/kinetiq-YYYYmmdd-HHMMSS.db.gz
docker compose start kinetiq
```

Kinetiq refuses to overwrite the live DB without integrity-checking the
snapshot first; the old DB is renamed `kinetiq.db.replaced-<ts>` beside the
current one.

## Upgrade path

- `git pull && docker compose up -d --build` — migrations and seeds run at
  startup and record a pre-migration snapshot automatically.
- If a schema change is unhappy, restore the pre-migration snapshot with the
  drill above and roll the code back.

## PaaS portability

The image runs standalone with only these env vars:

| Var | Default | Notes |
|---|---|---|
| `KINETIQ_MCP_PATH_TOKEN` | required | 48+ url-safe chars |
| `PORT` | 8765 | change if the platform needs a different one |
| `KINETIQ_DATA_DIR` | `/data` | mount a persistent volume there |
| `KINETIQ_DOMAIN` | `localhost` | set to the platform-supplied hostname |
| `KINETIQ_HOST` | `0.0.0.0` | leave as-is |

TLS is handled by the platform. SQLite requires a single instance and a
persistent disk; horizontal scaling is out of scope.
