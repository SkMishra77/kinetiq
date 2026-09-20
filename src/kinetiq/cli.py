"""Typer CLI: serve, migrate, seed, backup, restore, gen-token, print-url, verify-citations, export."""
from __future__ import annotations
import asyncio
import json
import logging
import secrets
import sys
from pathlib import Path

import typer

from . import __version__
from .db.connection import Database
from .db.migrations import apply_pending, current_version
from .db.backup import backup as run_backup, restore as run_restore
from .knowledge.seed_loader import load_all
from .logging_config import setup_logging
from .settings import Settings

app = typer.Typer(add_completion=False, help="Kinetiq: personal-trainer MCP server.")


def _load_settings() -> Settings:
    return Settings()


@app.command()
def gen_token() -> None:
    """Print a fresh 64-char url-safe MCP path token."""
    typer.echo(secrets.token_urlsafe(48))


@app.command("print-url")
def print_url() -> None:
    """Print the full connector URL (https://$KINETIQ_DOMAIN/mcp/$KINETIQ_MCP_PATH_TOKEN)."""
    s = _load_settings()
    if not s.mcp_path_token:
        typer.secho("KINETIQ_MCP_PATH_TOKEN is not set.", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)
    scheme = "https" if s.domain not in ("localhost", "127.0.0.1") else "http"
    port = "" if s.domain not in ("localhost", "127.0.0.1") else f":{s.port}"
    typer.echo(f"{scheme}://{s.domain}{port}{s.mcp_url_path()}")


@app.command()
def migrate() -> None:
    """Apply pending migrations."""
    s = _load_settings()
    setup_logging(s.log_level, s.log_format, s.sensitive_values())
    db = Database(s.resolved_db_path())
    applied = apply_pending(db)
    typer.echo(f"applied: {applied}, current: {current_version(db)}")


@app.command()
def seed(force: bool = typer.Option(False, "--force", help="Re-seed even if hash unchanged.")) -> None:
    """Load / refresh seed exercises + principles."""
    s = _load_settings()
    setup_logging(s.log_level, s.log_format, s.sensitive_values())
    db = Database(s.resolved_db_path())
    apply_pending(db)
    report = load_all(db, force=force)
    typer.echo(json.dumps(report, indent=2))


@app.command()
def backup(keep_daily: int = 14) -> None:
    """Create a compressed integrity-checked backup and rotate old ones."""
    s = _load_settings()
    setup_logging(s.log_level, s.log_format, s.sensitive_values())
    gz = run_backup(s.resolved_db_path(), s.resolved_backup_dir(), keep_daily=keep_daily)
    typer.echo(str(gz))


@app.command()
def restore(snapshot: Path) -> None:
    """Restore the DB from a snapshot (.db.gz)."""
    s = _load_settings()
    setup_logging(s.log_level, s.log_format, s.sensitive_values())
    if not snapshot.exists():
        typer.secho(f"missing: {snapshot}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)
    run_restore(snapshot, s.resolved_db_path())
    typer.echo(f"restored → {s.resolved_db_path()}")


@app.command("verify-citations")
def verify_citations(fail_on_error: bool = True) -> None:
    """Check every seed knowledge_citation's PMID against PubMed esummary."""
    from .knowledge.research.client import verify_pmid
    from rapidfuzz import fuzz
    s = _load_settings()
    setup_logging(s.log_level, s.log_format, s.sensitive_values())
    db = Database(s.resolved_db_path())
    apply_pending(db)
    load_all(db)
    rows = db.execute(
        "SELECT c.id, c.pmid, c.title FROM knowledge_citations c "
        "WHERE c.pmid IS NOT NULL AND c.verification_status<>'verified'"
    ).fetchall()
    typer.echo(f"verifying {len(rows)} citations...")
    failures = 0
    for r in rows:
        try:
            meta = asyncio.run(verify_pmid(r["pmid"], s.ncbi_api_key))
            ratio = fuzz.token_set_ratio(meta.get("title") or "", r["title"] or "")
            if ratio >= 80:
                with db.write() as c:
                    c.execute("UPDATE knowledge_citations SET verification_status='verified', "
                              "verified_at=datetime('now') WHERE id=?", (r["id"],))
                typer.echo(f"  OK  PMID {r['pmid']}: {(meta.get('title') or '')[:80]}")
            else:
                failures += 1
                with db.write() as c:
                    c.execute("UPDATE knowledge_citations SET verification_status='failed', "
                              "verified_at=datetime('now') WHERE id=?", (r["id"],))
                typer.echo(f"  FAIL PMID {r['pmid']}: ratio={ratio}, stored={r['title'][:60]!r}, remote={(meta.get('title') or '')[:60]!r}")
        except Exception as e:  # noqa: BLE001
            failures += 1
            typer.secho(f"  ERR  PMID {r['pmid']}: {e}", fg=typer.colors.YELLOW)
    if failures and fail_on_error:
        typer.secho(f"{failures} citations failed verification", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)


@app.command()
def serve(reload: bool = False) -> None:
    """Run the MCP server via uvicorn."""
    import uvicorn
    s = _load_settings()
    setup_logging(s.log_level, s.log_format, s.sensitive_values())
    if not s.mcp_path_token and not s.allow_weak_token:
        typer.secho("KINETIQ_MCP_PATH_TOKEN is required (48+ url-safe chars). "
                    "Generate one with `kinetiq gen-token`.",
                    fg=typer.colors.RED, err=True)
        raise typer.Exit(2)
    from .app import build_asgi_app
    asgi_app = build_asgi_app(s)
    logging.info("starting kinetiq %s on %s:%d path=%s",
                  __version__, s.host, s.port, s.mcp_url_path())
    uvicorn.run(asgi_app, host=s.host, port=s.port, log_config=None,
                access_log=False, proxy_headers=True, forwarded_allow_ips="*")


if __name__ == "__main__":  # pragma: no cover
    app()
