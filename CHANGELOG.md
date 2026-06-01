# Changelog

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
