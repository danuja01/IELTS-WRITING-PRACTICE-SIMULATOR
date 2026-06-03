#!/usr/bin/env python3
"""One-time migration from SQLite to PostgreSQL.

Usage:
  export DB_TYPE=postgres
  export POSTGRES_HOST=localhost
  export POSTGRES_PASSWORD=...
  export IELTS_DB=./data/app.db
  python migrate_sqlite_to_postgres.py

Requires PostgreSQL schema to exist (run the app once with DB_TYPE=postgres
or call db_adapter.init_database with a dummy path).
"""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv()

from db_adapter import connect_db, init_database, is_postgres
from db_util import connect_sqlite

TABLES = (
    "users",
    "categories",
    "questions",
    "writings",
    "password_reset_tokens",
)


def _sqlite_path() -> str:
    app_dir = os.path.dirname(os.path.abspath(__file__))
    return os.environ.get("IELTS_DB", os.path.join(app_dir, "data", "app.db"))


def migrate() -> None:
    if not is_postgres():
        print("Set DB_TYPE=postgres before running this script.", file=sys.stderr)
        sys.exit(1)

    sqlite_path = _sqlite_path()
    if not os.path.isfile(sqlite_path):
        print(f"SQLite database not found: {sqlite_path}", file=sys.stderr)
        sys.exit(1)

    init_database(sqlite_path)

    src = connect_sqlite(sqlite_path)
    dst = connect_db(sqlite_path)
    try:
        for table in TABLES:
            rows = src.execute(f"SELECT * FROM {table}").fetchall()
            if not rows:
                print(f"  {table}: 0 rows")
                continue
            cols = rows[0].keys()
            col_list = ", ".join(cols)
            placeholders = ", ".join(["?"] * len(cols))
            count = 0
            for row in rows:
                dst.execute(
                    f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) ON CONFLICT (id) DO NOTHING",
                    tuple(row[c] for c in cols),
                )
                count += 1
            dst.commit()
            print(f"  {table}: {count} rows copied")
    finally:
        src.close()
        dst.close()

    print("Migration complete.")


if __name__ == "__main__":
    migrate()
