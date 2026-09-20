"""SQLite backup + restore using VACUUM INTO (sqlite3 CLI not required)."""
from __future__ import annotations
import gzip
import logging
import shutil
import sqlite3
import time
from pathlib import Path

log = logging.getLogger(__name__)


def _snapshot_name(prefix: str = "kinetiq") -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    return f"{prefix}-{stamp}.db"


def vacuum_into(db_path: Path, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        raise FileExistsError(str(out_path))
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("VACUUM INTO ?", (str(out_path),))
    finally:
        conn.close()
    return out_path


def integrity_ok(db_path: Path) -> bool:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
        return row is not None and row[0] == "ok"
    finally:
        conn.close()


def gzip_file(src: Path) -> Path:
    dst = src.with_suffix(src.suffix + ".gz")
    with open(src, "rb") as fin, gzip.open(dst, "wb", compresslevel=6) as fout:
        shutil.copyfileobj(fin, fout)
    src.unlink(missing_ok=True)
    return dst


def rotate(backup_dir: Path, keep_daily: int = 14) -> list[Path]:
    """Delete oldest .db.gz snapshots beyond ``keep_daily``.

    Files whose name begins with ``pre-migrate-`` are never rotated.
    Returns the list of files removed.
    """
    snapshots = sorted(
        (p for p in backup_dir.glob("*.db.gz") if not p.name.startswith("pre-migrate-")),
        key=lambda p: p.name,
        reverse=True,
    )
    removed: list[Path] = []
    for p in snapshots[keep_daily:]:
        p.unlink()
        removed.append(p)
    return removed


def backup(db_path: Path, backup_dir: Path, prefix: str = "kinetiq", keep_daily: int = 14) -> Path:
    """Create a compressed, integrity-checked snapshot; rotate old ones.

    Returns the final ``.db.gz`` path.
    """
    backup_dir.mkdir(parents=True, exist_ok=True)
    raw = backup_dir / _snapshot_name(prefix)
    vacuum_into(db_path, raw)
    if not integrity_ok(raw):
        raw.unlink(missing_ok=True)
        raise RuntimeError(f"integrity check failed on {raw}")
    gz = gzip_file(raw)
    rotate(backup_dir, keep_daily=keep_daily)
    log.info("backup created", extra={"event": "backup", "path": str(gz)})
    return gz


def restore(snapshot: Path, target: Path) -> None:
    """Replace ``target`` with a decompressed copy of ``snapshot`` (.db or .db.gz)."""
    if snapshot.suffixes[-2:] == [".db", ".gz"]:
        tmp = target.with_suffix(".restore.db")
        with gzip.open(snapshot, "rb") as fin, open(tmp, "wb") as fout:
            shutil.copyfileobj(fin, fout)
        if not integrity_ok(tmp):
            tmp.unlink(missing_ok=True)
            raise RuntimeError("restored snapshot failed integrity_check")
    else:
        tmp = snapshot
        if not integrity_ok(tmp):
            raise RuntimeError("snapshot failed integrity_check")
    if target.exists():
        replaced = target.with_name(target.name + f".replaced-{time.strftime('%Y%m%d-%H%M%S')}")
        target.rename(replaced)
    shutil.copyfile(tmp, target)
    if tmp != snapshot:
        tmp.unlink(missing_ok=True)
