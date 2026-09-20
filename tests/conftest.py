"""Shared pytest fixtures for Kinetiq."""
from __future__ import annotations
import asyncio
import os
from pathlib import Path

import pytest

from kinetiq.settings import Settings
from kinetiq.db.connection import Database
from kinetiq.db.migrations import apply_pending
from kinetiq.knowledge.seed_loader import load_all


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    os.environ.pop("KINETIQ_DATA_DIR", None)
    return Settings(
        data_dir=tmp_path,
        mcp_path_token="x" * 64,
        timezone="Asia/Kolkata",
        domain="localhost",
        mask_error_details=False,
        allow_weak_token=True,
    )


@pytest.fixture
def fresh_db(settings: Settings) -> Database:
    db = Database(settings.resolved_db_path())
    apply_pending(db)
    return db


@pytest.fixture
def seeded_db(fresh_db: Database) -> Database:
    load_all(fresh_db)
    return fresh_db


@pytest.fixture
def server(settings: Settings):
    from kinetiq.server import create_server
    mcp, svc = create_server(settings)
    yield mcp
    svc.close()


@pytest.fixture
def client(server):
    """Async context-managed FastMCP in-memory client."""
    from fastmcp import Client
    return Client(server)
