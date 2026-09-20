"""Backup + restore round-trip."""
from kinetiq.db.backup import backup, restore, integrity_ok


def test_backup_and_restore(fresh_db, settings):
    fresh_db.close()
    gz = backup(settings.resolved_db_path(), settings.resolved_backup_dir())
    assert gz.exists()
    # Wipe the DB and restore
    settings.resolved_db_path().unlink()
    restore(gz, settings.resolved_db_path())
    assert integrity_ok(settings.resolved_db_path())
