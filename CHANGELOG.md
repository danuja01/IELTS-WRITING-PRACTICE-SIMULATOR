# Changelog

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
