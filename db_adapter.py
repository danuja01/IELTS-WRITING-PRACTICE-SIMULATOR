"""Database adapter: SQLite (default) or optional PostgreSQL."""
from __future__ import annotations

import os
import re
from contextlib import closing

from db_util import connect_sqlite

DB_TYPE = os.environ.get("DB_TYPE", "sqlite").strip().lower()
IS_POSTGRES = DB_TYPE == "postgres"


def is_sqlite() -> bool:
    return not IS_POSTGRES


def is_postgres() -> bool:
    return IS_POSTGRES


def _sqlite_to_pg(sql: str) -> str:
    sql = sql.replace("?", "%s")
    sql = re.sub(r"\bIFNULL\s*\(", "COALESCE(", sql, flags=re.IGNORECASE)
    return sql


def _insert_returning(sql: str) -> str:
    stripped = sql.strip()
    if not stripped.upper().startswith("INSERT"):
        return sql
    if re.search(r"\bRETURNING\b", stripped, re.I):
        return sql
    return sql.rstrip().rstrip(";") + " RETURNING id"


class _PgCursor:
    def __init__(self, cursor, lastrowid: int | None = None):
        self._cursor = cursor
        self.lastrowid = lastrowid

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


class _PgConnection:
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql: str, params=()):
        import psycopg2.extras

        pg_sql = _sqlite_to_pg(sql)
        returning = pg_sql.strip().upper().startswith("INSERT")
        if returning:
            pg_sql = _insert_returning(pg_sql)
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(pg_sql, params)
        lastrowid = None
        if returning:
            row = cur.fetchone()
            if row:
                lastrowid = row["id"]
        return _PgCursor(cur, lastrowid)

    def executescript(self, script: str):
        cur = self._conn.cursor()
        try:
            cur.execute(script)
        finally:
            cur.close()

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def connect_db(db_path: str | None = None, *, row_factory=None):
    """Return a DB connection compatible with app.py's SQLite usage."""
    if IS_POSTGRES:
        return _connect_postgres()
    path = db_path or os.environ.get(
        "IELTS_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "app.db")
    )
    if row_factory is not None:
        return connect_sqlite(path, row_factory=row_factory)
    return connect_sqlite(path)


def _connect_postgres() -> _PgConnection:
    import psycopg2

    host = os.environ.get("POSTGRES_HOST", "postgres")
    port = int(os.environ.get("POSTGRES_PORT", "5432"))
    dbname = os.environ.get("POSTGRES_DB", "ielts_writing")
    user = os.environ.get("POSTGRES_USER", "ielts")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    conn = psycopg2.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
    )
    conn.autocommit = False
    return _PgConnection(conn)


def _migrate_sqlite(db):
    def add_col(table, col, typedef):
        cols = {r[1] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}
        if col not in cols:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")

    add_col("users", "email", "TEXT")
    add_col("users", "is_admin", "INTEGER NOT NULL DEFAULT 0")
    add_col("users", "must_change_password", "INTEGER NOT NULL DEFAULT 0")
    add_col("questions", "image_path", "TEXT")
    add_col("questions", "category_id", "INTEGER REFERENCES categories(id)")
    add_col("questions", "prompt_highlights", "TEXT")
    add_col("questions", "copied_from_id", "INTEGER REFERENCES questions(id) ON DELETE SET NULL")
    add_col("questions", "is_private", "INTEGER NOT NULL DEFAULT 0")
    db.execute("UPDATE questions SET is_private = 1 WHERE copied_from_id IS NOT NULL")
    db.commit()
    add_col("writings", "paragraph_stats", "TEXT")
    db.commit()

    db.execute(
        """CREATE TABLE IF NOT EXISTS user_api_keys (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            openrouter_api_key_enc TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS writing_evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            writing_id INTEGER NOT NULL UNIQUE REFERENCES writings(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            band_score REAL NOT NULL,
            criterion_scores_json TEXT NOT NULL,
            overall_feedback TEXT NOT NULL,
            mistakes_json TEXT NOT NULL,
            areas_for_improvement_json TEXT NOT NULL,
            rewritten_essay TEXT NOT NULL,
            model TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    db.commit()

    db.execute(
        """CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            code_hash TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            used_at TEXT
        )"""
    )
    db.commit()


def _migrate_postgres(db):
    def has_col(table, col):
        row = db.execute(
            """SELECT 1 FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = %s AND column_name = %s""",
            (table, col),
        ).fetchone()
        return row is not None

    def add_col(table, col, typedef):
        if not has_col(table, col):
            db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")

    add_col("users", "email", "TEXT")
    add_col("users", "is_admin", "INTEGER NOT NULL DEFAULT 0")
    add_col("users", "must_change_password", "INTEGER NOT NULL DEFAULT 0")
    add_col("questions", "image_path", "TEXT")
    add_col("questions", "category_id", "INTEGER REFERENCES categories(id)")
    add_col("questions", "prompt_highlights", "TEXT")
    add_col("questions", "copied_from_id", "INTEGER REFERENCES questions(id) ON DELETE SET NULL")
    add_col("questions", "is_private", "INTEGER NOT NULL DEFAULT 0")
    db.execute("UPDATE questions SET is_private = 1 WHERE copied_from_id IS NOT NULL")
    db.commit()
    add_col("writings", "paragraph_stats", "TEXT")
    db.commit()

    db.execute(
        """CREATE TABLE IF NOT EXISTS user_api_keys (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            openrouter_api_key_enc TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS writing_evaluations (
            id SERIAL PRIMARY KEY,
            writing_id INTEGER NOT NULL UNIQUE REFERENCES writings(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            band_score REAL NOT NULL,
            criterion_scores_json TEXT NOT NULL,
            overall_feedback TEXT NOT NULL,
            mistakes_json TEXT NOT NULL,
            areas_for_improvement_json TEXT NOT NULL,
            rewritten_essay TEXT NOT NULL,
            model TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    db.commit()


_SQLITE_INIT = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    email TEXT,
    is_admin INTEGER NOT NULL DEFAULT 0,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    prompt TEXT NOT NULL,
    task_type TEXT DEFAULT 'task2',
    image_path TEXT,
    prompt_highlights TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS writings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    question_id INTEGER REFERENCES questions(id) ON DELETE SET NULL,
    content TEXT NOT NULL DEFAULT '',
    started_at TEXT,
    finished_at TEXT,
    elapsed_ms INTEGER,
    at_40min_ms INTEGER,
    words_at_40min INTEGER,
    final_words INTEGER,
    paragraph_stats TEXT,
    updated_at TEXT NOT NULL
);
"""

_POSTGRES_INIT = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    email TEXT,
    is_admin INTEGER NOT NULL DEFAULT 0,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS categories (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS questions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    prompt TEXT NOT NULL,
    task_type TEXT DEFAULT 'task2',
    image_path TEXT,
    prompt_highlights TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS writings (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    question_id INTEGER REFERENCES questions(id) ON DELETE SET NULL,
    content TEXT NOT NULL DEFAULT '',
    started_at TEXT,
    finished_at TEXT,
    elapsed_ms INTEGER,
    at_40min_ms INTEGER,
    words_at_40min INTEGER,
    final_words INTEGER,
    paragraph_stats TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    used_at TEXT
);
"""


_INIT_LOCK_ID = 915034521


def _run_postgres_init(db) -> None:
    for stmt in _POSTGRES_INIT.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            db.execute(stmt)
    db.commit()
    _migrate_postgres(db)


def init_database(db_path: str):
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    with closing(connect_db(db_path)) as db:
        if IS_POSTGRES:
            db.execute("SELECT pg_advisory_lock(%s)", (_INIT_LOCK_ID,))
            try:
                _run_postgres_init(db)
            finally:
                db.execute("SELECT pg_advisory_unlock(%s)", (_INIT_LOCK_ID,))
                db.commit()
        else:
            db.executescript(_SQLITE_INIT)
            db.commit()
            _migrate_sqlite(db)
