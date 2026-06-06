# AGENTS.md

## Cursor Cloud specific instructions

### Overview

Single Flask app (Python 3.12) with embedded SQLite — no Node.js, no separate frontend build, no external DB process for default dev. See [README.md](README.md) for full feature and deployment docs.

### System dependencies

The VM image needs `python3.12-venv` (or equivalent) so `python3 -m venv .venv` works. If venv creation fails, install once: `sudo apt-get install -y python3.12-venv`.

### Environment

1. Copy `.env.example` → `.env` and set `SECRET_KEY` (never commit `.env`).
2. The app loads `.env` via `python-dotenv` in `app.py` — **do not** `export $(grep ... .env | xargs)`; values like `SMTP_FROM` contain spaces/angle brackets and break shell export.
3. For local dev, `BACKUP_ENABLED=0` avoids the in-process backup scheduler thread.

### Install and run (local dev)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

App listens on **http://localhost:5050** (`PORT` in `.env`, default 5050).

Use a tmux session for long-running dev server (e.g. `flask-dev-server`).

### First-run flow

1. Open `/setup-admin` to create the first admin account.
2. Register student users at `/login` (admin cannot use student practice APIs).
3. Student flow: add question → `/practice/<id>` → auto-save drafts → finish session for history.

### Lint / tests

No project linter or automated test suite. Sanity check: `python -m compileall -q .` from the repo root with the venv activated.

### Docker (optional)

`docker compose up -d --build` also works (Gunicorn on port 5050). Postgres mode is optional via `docker-compose.postgres.yml` and `DB_TYPE=postgres`.

### Key API smoke checks

- `GET /api/version` — health/version
- `POST /api/setup-admin` — first admin (JSON: username, email, password)
- `POST /api/register` / `POST /api/login` — student auth
- `POST /api/questions` — create question (student session)
- `POST /api/writings` — save practice draft
