"""SQLite connection helper with WAL, foreign keys, single-writer lock."""
from __future__ import annotations
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator


class Database:
    """A thin sqlite3 wrapper.

    Notes:
        * WAL + ``synchronous=NORMAL`` gives good throughput while remaining crash-safe.
        * ``check_same_thread=False`` allows the ASGI executor to hand connections
          across threads; the module-level lock serialises writes.
        * ``foreign_keys=ON`` must be set per-connection (SQLite default is OFF).
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None

    def _new_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self.path),
            check_same_thread=False,
            isolation_level=None,      # autocommit; we explicitly BEGIN
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA temp_store=MEMORY")
        return conn

    @property
    def conn(self) -> sqlite3.Connection:
        with self._lock:
            if self._conn is None:
                self._conn = self._new_conn()
            return self._conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    @contextmanager
    def write(self) -> Iterator[sqlite3.Connection]:
        """Serialised write transaction (BEGIN IMMEDIATE)."""
        with self._lock:
            c = self.conn
            c.execute("BEGIN IMMEDIATE")
            try:
                yield c
                c.execute("COMMIT")
            except Exception:
                c.execute("ROLLBACK")
                raise

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        """Read-only usage (no BEGIN, still ok under WAL)."""
        with self._lock:
            yield self.conn

    def execute(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        with self._lock:
            return self.conn.execute(sql, params)

    def executescript(self, script: str) -> None:
        with self._lock:
            self.conn.executescript(script)

    def integrity_ok(self) -> bool:
        row = self.conn.execute("PRAGMA integrity_check").fetchone()
        return row is not None and row[0] == "ok"
