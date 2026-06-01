"""Shared SQLite connection settings for app + backup."""
import os
import sqlite3

SQLITE_TIMEOUT = float(os.environ.get("SQLITE_TIMEOUT", "30"))
SQLITE_BUSY_MS = int(os.environ.get("SQLITE_BUSY_MS", "30000"))
_JOURNAL = os.environ.get("SQLITE_JOURNAL_MODE", "WAL").upper()
JOURNAL_MODE = _JOURNAL if _JOURNAL in ("WAL", "DELETE", "TRUNCATE") else "WAL"


def connect_sqlite(path: str, *, row_factory=sqlite3.Row):
    conn = sqlite3.connect(path, timeout=SQLITE_TIMEOUT)
    if row_factory is not None:
        conn.row_factory = row_factory
    conn.execute(f"PRAGMA journal_mode={JOURNAL_MODE}")
    conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_MS}")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
