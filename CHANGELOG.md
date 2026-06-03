# Changelog

## 3.0.0

Scaling and deployment:

- **Practice autosave**: localStorage every 30s, DB sync every 60s; flush on tab close/reload
- **Optional PostgreSQL** via `DB_TYPE=postgres` and `db_adapter.py` (SQLite remains default)
- **`docker-compose.postgres.yml`**: one-deploy stack (app + Postgres) for high concurrency
- **Second GHCR package**: `ielts-writing-practice-postgres` for Postgres stacks
- **Gunicorn tuning** via `GUNICORN_WORKERS` / `GUNICORN_THREADS` env (defaults unchanged: 1/1)
- **`migrate_sqlite_to_postgres.py`**: optional SQLite → Postgres data migration

## 2.3.1

- **Others**: open multiple users at once (no longer one-at-a-time inside Others)
- **Expand all / Collapse all** button in the Others accordion header

## 2.3.0

Sharing and privacy:

- **Others** section (renamed from All): other users’ **original** questions only — no forks
- Grouped by **author** (collapsible), then category; clearer nested layout inside main Others accordion
- **Make private / Make public** on your questions via ⋮ menu; colored Public/Private labels
- Private questions hidden from Others; forks default to **private** (can be made public)
- **Add question**: Public / Private tabs next to title; choice **persisted in localStorage**

## 2.2.1

- Home: rename **All** accordion to **Others**; list every other user’s questions (not yours)

## 2.2.0

- Forgot password: email with 6-digit reset code (SMTP via `.env`)
- Login page link to forgot / reset password flows
- Single `docker-compose.yml` with `env_file: .env` (removed extra compose files)

## 2.1.3

- Practice screen: hide elapsed timer during writing; show time remaining only

## 2.1.2

- Fix three-dot question menu clipped/hidden inside category cards (fixed positioning + overflow)

## 2.1.1

- Practice footer: centered word count; removed auto-save label and selected-word line (selection count stays on right-click menu only)

## 2.1.0

- Home: Start only on question rows; Move and Delete in a three-dot menu (bin icon)
- Practice: word count in the writing footer; cleaner top bar and pane headers
- Admin user page: fix Task 1 chart images for admins; attempts section divider; centered empty state

## 2.0.17

- Question forks: All shows originals only (no duplicate copies); Copy to My tracks source; admin fork list
- Admin can open student attempt details (full insights)
- Task 1 chart in history uses fixed-size image box

## 2.0.16

- All section shows only other users’ questions; copies appear in My questions only (no duplicates)

## 2.0.15

- Fix Move to… dropdown: load categories before questions so all user categories appear

## 2.0.14

- Practice page: fix page-level overflow on some screens (scroll contained in question/answer panes)

## 2.0.13

- Highlights tied to current attempt only; cleared on Finish and when starting a new session

## 2.0.12

- Question highlights are session-only (browser tab); not saved to DB or visible to others

## 2.0.11

- Fix 500 on home page: login redirect used wrong route name (`login` vs `login_page`)

## 2.0.10

- Fix multi-browser / multi-user 500 errors: SQLite busy timeout, single request thread, safer backups
- Friendly error page when database is busy (auto-retry on home page)
- Optional `SQLITE_JOURNAL_MODE=DELETE` for NAS network storage (see compose file)

## 2.0.9

- **Copy to My** on shared questions in All - duplicates question (and chart image) into your My questions list

## 2.0.8

- Home accordions: opening one section (My questions / All) automatically closes the other

## 2.0.7

- Questions are shared: everyone can see and practice questions added by any user
- Home page: accordion sections **My questions** and **All** (with author name on others’ questions)
- Delete/move only on your own questions; history includes attempts on shared questions

## 2.0.6

- Practice: question text shown before Task 1 chart; chart size slider in toolbar (50–100%)
- Home: clearer category cards, indented questions with left accent line, task badges

## 2.0.5

- Question prompt visibly bold (`strong` + CSS cache bust)
- Highlight toolbar button when question text is selected (works without right-click)
- Improved question right-click highlight on Chrome/Mac

## 2.0.4

- Fix right-click word count on Mac (capture selection before native menu opens)
- Show "Selected: N words" in footer while answer text is highlighted

## 2.0.2

- Fix admin user page stuck on "Loading…" (JS error handling, missing attempts fallback, cache bust)

## 2.0.1

- Fix right-click word count on essay (selection backup, reliable context menus)
- Fix question highlight using text-node offsets (works with existing highlights)
- Bolder question prompt styling + usage hint
- Admin user page: question cards with Task 1 images, prompt preview, and attempts list

## 2.0.0

- Admin bootstrap (`/setup-admin`) when no admin exists
- Admin panel: manage users, temp passwords, forced password change, edit any question
- Register requires email; students cannot access admin routes
- Per-user categories for grouping questions
- Paragraph-level time tracking (split on blank lines) and grouped writing history with analytics
- Question prompt: larger bold text, yellow highlights (right-click)
- Essay: right-click selection word count
- Version 2.0.0

## 1.3.0

- Automatic weekly SQLite backup in `data/backups/` (keeps one latest file only)
- Safe backup via SQLite `backup()` API while the app is running

## 1.2.0

- Task 1: upload chart/diagram illustration image when adding a question
- Image shown on the practice screen next to the prompt

## 1.1.0

- Production server: Gunicorn in Docker (replaces Flask dev server)
- Version shown in the UI and Docker image tags

## 1.0.0

- Initial release: login, custom questions, practice UI, timer, word count, auto-save
