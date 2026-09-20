# Kinetiq — instructions for Claude Code

## What this is
Kinetiq is a **remote MCP server** the user connects to claude.ai as a custom
connector. Claude in claude.ai is the trainer; this server is memory,
deterministic analysis and cited exercise-science evidence.

**Non-goals**: this server does not run an LLM. FastMCP 4 removed
`ctx.sample()`, so every "decision" (progression, plateau, fatigue, pain
response) is pure Python. Claude interprets the returned data.

## Commands

```bash
uv sync                             # install (Python 3.12, uv-managed venv)
uv run pytest -q -m "not network"   # test suite (no network)
uv run ruff check . && uv run ruff format --check .
uv run mypy src

uv run kinetiq gen-token            # 48-char url-safe token
uv run kinetiq print-url            # https://$KINETIQ_DOMAIN/mcp/$TOKEN
uv run kinetiq migrate              # apply pending DB migrations
uv run kinetiq seed                 # load exercises.yaml + principles.yaml
uv run kinetiq backup               # VACUUM INTO → gz, keeps 14
uv run kinetiq verify-citations     # check every seed PMID against PubMed
uv run kinetiq serve                # dev run at http://localhost:8765

docker compose --profile caddy up -d --build
docker compose logs -f kinetiq
./scripts/backup.sh
```

## Architecture map

```
src/kinetiq/
  settings.py              pydantic-settings; KINETIQ_* env vars
  server.py                FastMCP factory + middleware wiring
  app.py                   ASGI factory used by uvicorn
  cli.py                   typer CLI
  db/
    connection.py          sqlite3 wrapper (WAL, FK, single writer)
    migrations.py + migrations/0001_init.sql
    backup.py              VACUUM INTO + gzip + integrity_check
    repos/*.py             ONLY place with SQL
  domain/                  pydantic IO models + enums, dates
  parsing/                 sets shorthand, weights, alias resolution
  engine/                  pure functions: e1RM, progression, plateau,
                           fatigue, pain, planner, warmup
  knowledge/               seed loader, sanitizer, research clients
  briefing/builder.py      shapes the mandatory-first payload
  tools/                   thin MCP adapters — one dispatcher per group
  middleware/audit.py      writes audit_log rows for every tool call
  data/*.yaml              seed exercises, principles, subs, warmup lib
```

Contract rules (enforced by the mcp-tool-reviewer subagent):

- **tools thin** — no SQL, no math; only validate → call service → shape a dict.
- **engine pure** — no DB, no I/O; deterministic; testable in isolation.
- **repos only** — every SQL statement lives under `db/repos/`.
- **research only** — every outbound HTTP call lives under
  `knowledge/research/`.
- **echoes** — every write tool returns a human-readable `echo` field Claude
  can quote.
- **annotations** — write tools set `read_only_hint=False`; only
  `amend_workout` is `destructive_hint=True`; research tools set
  `open_world_hint=True`.
- **Errors** — user-facing failures use `fastmcp.exceptions.ToolError`.
- **Prompt-injection hygiene** — text fetched from the research APIs never
  ends up in server instructions, tool descriptions or the briefing payload.

## How to add a tool

1. Add IO models to `domain/models.py` if not already there.
2. Add a repo function under `db/repos/*.py` (SQL only).
3. Add a service/engine call under `engine/*.py` (pure) if there's logic.
4. Register the tool in `tools/<group>.py` using `@mcp.tool(annotations=…)`;
   description must say **when** to call and **what** it returns.
5. Add a test in `tests/tools/` that uses the in-memory `Client(server)`.
6. Update the `EXPECTED_TOOLS` set in
   `tests/tools/test_tool_contracts.py` and re-run the suite.

## How to add exercises / principles

- Edit `src/kinetiq/data/exercises.yaml` or `principles.yaml`. The seed loader
  is idempotent and only overwrites rows with `source='seed'`.
- Every principle citation is a PMID or DOI. Run
  `uv run kinetiq verify-citations` — CI fails if a citation title does not
  fuzzy-match the corresponding PubMed record.

## Schema changes

- Add a new `db/migrations/NNNN_<name>.sql` file (never edit existing).
- Add a case to `tests/test_migrations.py`.
- Bump `engine/thresholds.ENGINE_VERSION` when the analyzer's semantics change
  (this makes older `session_analyses` visibly out-of-date and lets you
  re-run `analyze_workout` per workout).

## Deployment

- `Dockerfile` (multi-stage uv build, non-root, `read_only` rootfs).
- `compose.yaml` with `caddy` (default) and `ngrok` profiles.
- `deploy/Caddyfile` terminates TLS via Let's Encrypt for
  `$KINETIQ_DOMAIN`.
- Access logs are OFF everywhere so the URL token never lands in a log file.

## Environment notes for Claude Code

- **This Claude Code runs on AWS Bedrock**: `WebSearch` is unavailable. Use
  `WebFetch` against `https://gofastmcp.com/llms.txt` (an index of doc URLs),
  `https://eutils.ncbi.nlm.nih.gov/…`, and other public docs.
- Never commit `.env` or `data/`.
- Never print the MCP path token in log output — a `RedactingFilter`
  scrubs it, but avoid emitting it in the first place.

## Definition of done

- `uv run pytest -q -m "not network"` green.
- Tool contract snapshot updated intentionally.
- Docs updated when the trainer flow changes.
- No new dependency without a lockfile update (`uv lock`).
