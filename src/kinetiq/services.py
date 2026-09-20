"""Shared service container passed to tools.

Holds the Database and settings; may hold cached seeds or research clients in
future. Lifetime is one MCP server instance.
"""
from __future__ import annotations
from dataclasses import dataclass

from .db.connection import Database
from .settings import Settings


@dataclass
class Services:
    db: Database
    settings: Settings

    @classmethod
    def build(cls, settings: Settings) -> "Services":
        db = Database(settings.resolved_db_path())
        return cls(db=db, settings=settings)

    def close(self) -> None:
        self.db.close()
