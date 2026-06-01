"""Weekly SQLite backup with single-file rotation."""
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

BACKUP_FILENAME = "app.db.latest.bak"
META_FILENAME = ".last_backup"


def backup_interval_seconds() -> int:
    days = float(os.environ.get("BACKUP_INTERVAL_DAYS", "7"))
    return max(86400, int(days * 86400))


def backups_enabled() -> bool:
    return os.environ.get("BACKUP_ENABLED", "1").lower() not in ("0", "false", "no")


def _backup_dir(data_dir: str) -> Path:
    return Path(data_dir) / "backups"


def _last_backup_time(backup_dir: Path) -> float | None:
    meta = backup_dir / META_FILENAME
    if meta.is_file():
        try:
            return float(meta.read_text(encoding="utf-8").strip())
        except ValueError:
            pass
    dest = backup_dir / BACKUP_FILENAME
    if dest.is_file():
        return dest.stat().st_mtime
    return None


def backup_due(data_dir: str) -> bool:
    backup_dir = _backup_dir(data_dir)
    last = _last_backup_time(backup_dir)
    if last is None:
        return True
    return (time.time() - last) >= backup_interval_seconds()


def run_backup(db_path: str, data_dir: str) -> bool:
    """Create a consistent SQLite backup; keep only the latest file."""
    db_file = Path(db_path)
    if not db_file.is_file():
        log.info("backup skipped: database file does not exist yet")
        return False

    backup_dir = _backup_dir(data_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    dest = backup_dir / BACKUP_FILENAME
    tmp = backup_dir / f".{BACKUP_FILENAME}.tmp"

    try:
        if tmp.exists():
            tmp.unlink()
        src = sqlite3.connect(str(db_file))
        try:
            dst = sqlite3.connect(str(tmp))
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        tmp.replace(dest)
        (backup_dir / META_FILENAME).write_text(str(time.time()), encoding="utf-8")
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        log.info("database backup saved: %s (%s)", dest, ts)
        return True
    except Exception:
        log.exception("database backup failed")
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return False


def maybe_run_backup(db_path: str, data_dir: str) -> bool:
    if not backups_enabled():
        return False
    if not backup_due(data_dir):
        return False
    return run_backup(db_path, data_dir)


def start_backup_scheduler(db_path: str, data_dir: str) -> None:
    if not backups_enabled():
        log.info("scheduled backups disabled (BACKUP_ENABLED=0)")
        return

    def loop() -> None:
        while True:
            try:
                maybe_run_backup(db_path, data_dir)
            except Exception:
                log.exception("backup scheduler error")
            time.sleep(3600)

    threading.Thread(target=loop, name="db-backup", daemon=True).start()
    maybe_run_backup(db_path, data_dir)
