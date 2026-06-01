# IELTS Writing Practice (lightweight)

**Version 1.1.0** — see [CHANGELOG.md](CHANGELOG.md)

Minimal practice app for IELTS-style writing: split question/answer layout, word count, adjustable text size, 40-minute timer (turns red after 40 min but keeps running), simple login, and saved drafts.

**Stack:** Python Flask + SQLite + vanilla HTML/CSS/JS (no Node build, low RAM — typically ~30–50 MB).

## Run locally

```bash
cd "/Users/danuja/Desktop/IELTS WRITING"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY="your-secret-key"
python app.py
```

Open http://localhost:5050

**Docker / NAS** uses [Gunicorn](https://gunicorn.org/) (production WSGI server), not Flask’s dev server. — register a user, add a question, click **Start**.

## Run on NAS (Docker)

```bash
docker compose up -d --build
```

Set `SECRET_KEY` in `docker-compose.yml`. Data persists in `./data/`.

## Features

- **Login / register** — per-user questions and writings
- **Add your own questions** — Task 1 or Task 2
- **Practice screen** — question left, writing right (IELTS-like)
- **Word count** — live
- **Text controls** — font size and line spacing sliders
- **40 min timer** — countdown; at 0:00 turns red and shows overtime; writing never stops
- **At finish** — total time, words at 40 min, cursor position at 40 min
- **Auto-save** every 15 seconds

## Environment

| Variable     | Default              |
|-------------|----------------------|
| `PORT`      | `5050`               |
| `SECRET_KEY`| `change-me-in-production` |
| `IELTS_DB`  | `./data/app.db`      |
