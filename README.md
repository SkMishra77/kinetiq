# Kinetiq

Personal AI-trainer memory as a remote MCP server. Connect it to Claude on
claude.ai as a custom connector; Claude becomes your evidence-based trainer
with long-term memory. Everything you tell it — profile, program, every set —
lives in a local SQLite file and is retrieved via MCP tools, so no conversation
starts from zero.

**Design in one screen**

- The server holds memory, deterministic analysis, and cited exercise-science
  evidence. Claude in claude.ai is the trainer.
- Every conversation must start with the `get_briefing` tool; the server
  instructions and every tool description steer Claude to that flow.
- Workouts are logged with a single `log_workout` call that accepts the
  shorthand you naturally type (`"60kg × 8, 60kg × 7, 57.5kg × 8"`,
  `"22.5kg × 10 × 3"`, `"bw × 12"`), stores the sets, and runs the analysis in
  the same call — returning progression, PRs, plateau flags, pain flags, and
  the next-session adjustments.

## Quick start (local dev)

```bash
uv sync
uv run kinetiq gen-token          # copy into .env
cp .env.example .env               # then fill in the values, chmod 600
uv run kinetiq migrate             # apply the schema
uv run kinetiq seed                # load the exercise library + principles
uv run pytest -q -m "not network"  # smoke test
uv run kinetiq serve               # http://localhost:8765
```

`uv run kinetiq print-url` prints the exact URL to paste into claude.ai
once `.env` is populated.

## Deploy on a VPS (Docker + Caddy + DuckDNS)

1. Open inbound TCP 80 and 443 on the host.
2. Create a free DuckDNS subdomain, point it at the host's public IP, and
   copy the token from the DuckDNS account page.
3. `cp .env.example .env` and fill in `KINETIQ_MCP_PATH_TOKEN`,
   `KINETIQ_DOMAIN` (`<sub>.duckdns.org`), `KINETIQ_ACME_EMAIL`,
   `DUCKDNS_SUBDOMAIN`, `DUCKDNS_TOKEN`. `chmod 600 .env`.
4. `docker compose --profile caddy up -d --build`
5. `curl https://$KINETIQ_DOMAIN/health` → `{"status":"ok",...}`
6. In claude.ai: `+` → **Add custom connector** → paste the URL from
   `kinetiq print-url` (leave OAuth fields blank).
7. Create a Project in claude.ai and paste `docs/claude-project-instructions.md`
   into its custom instructions.

## Alternative edges

- **ngrok**: `COMPOSE_PROFILES=ngrok NGROK_AUTHTOKEN=… KINETIQ_DOMAIN=your-static.ngrok-free.app docker compose up -d`.
- **PaaS later**: the image runs standalone with `PORT` and
  `KINETIQ_DATA_DIR` pointing at a persistent volume; TLS handled by the platform.

## Tools

The connector exposes 22 tools. The most important ones:

| Tool | When Claude should call it |
|---|---|
| `get_briefing` | First tool in every conversation. |
| `save_profile`, `log_checkin`, `log_pain_or_injury` | Store user data. |
| `search_exercises`, `add_exercise`, `compare_exercises` | Library work. |
| `create_program`, `edit_session_template`, `set_program_phase`, `get_program` | Program lifecycle. |
| `plan_next_session` | "What should I do today?" |
| `log_workout`, `amend_workout`, `analyze_workout` | Post-workout. |
| `get_exercise_history`, `get_training_history`, `update_insight` | Reflection. |
| `search_knowledge`, `search_research`, `save_finding` | Evidence-based answers. |
| `export_training_data` | Portability / backup. |

Full descriptions live in the tool code and in `docs/adding-tools.md`.

## Data & backups

- SQLite file at `data/kinetiq.db`, WAL enabled, foreign keys on.
- `uv run kinetiq backup` → integrity-checked `.db.gz` under `data/backups/`,
  keeps 14 daily. `scripts/backup.sh` is a Docker Compose wrapper suitable for
  a host cron entry (`15 3 * * *`).
- `scripts/pull-backups.sh` copies snapshots out of the Docker volume to
  `~/kinetiq-backups`, so a volume loss does not lose backups.
- Restore: `scripts/restore.sh /data/backups/<file.db.gz>`.

## Security model

- No login. The MCP endpoint URL contains a random 48+ char token loaded from
  `KINETIQ_MCP_PATH_TOKEN`. Every other path returns 404 at both Caddy and the
  app. Caddy access logs are OFF so the URL never lands in logs; the app
  disables uvicorn's access log; a redaction filter scrubs any accidental
  leak.
- All destructive tool branches (`amend_workout(void_session)`,
  `edit_session_template(remove)`, `set_program_phase(archive)`) require an
  explicit `confirm=true` or are soft deletes.
- Text returned by the research tools is wrapped as `untrusted: true` — the
  server never inserts it into instructions or descriptions and Claude is told
  to treat it as data.

## Troubleshooting

- **`/health` returns 200 but claude.ai says "no tools"** → the URL is
  missing the token or Caddy is returning 404 for the token path. Double-check
  `kinetiq print-url` output.
- **Cert issuance failing** → `docker compose logs caddy`. Common causes: 80
  not open, DuckDNS record not yet propagated.
- **Rotating the token** → change `.env`, `docker compose up -d`, then remove
  the connector in claude.ai and re-add it (URL is not editable in place).

See `docs/` for more.

## Attribution

Built with Claude Code. See `.claude/agents/*.md` for the dev-side agents.
