# Host on NAS with Dockge

Repo: https://github.com/danuja01/IELTS-WRITING-PRACTICE-SIMULATOR

## Choose a compose file

| Stack | Compose file | GHCR image | Starts |
|---|---|---|---|
| **SQLite (default prod)** | `docker-compose.yml` | `ghcr.io/danuja01/ielts-writing-practice-simulator:latest` | App only |
| **PostgreSQL (50+ users)** | `docker-compose.postgres.yml` | `ghcr.io/danuja01/ielts-writing-practice-postgres:latest` | App + Postgres |

Both GHCR packages contain the **same app image**. The Postgres package name matches the Postgres compose stack so Dockge users know which file to use.

## Setup (SQLite — most deployments)

1. Copy the project folder to your NAS stack directory (or clone the repo there).
2. In that folder:

   ```bash
   cp .env.example .env
   ```

3. Edit **`.env`**:
   - `SECRET_KEY` — long random string (`openssl rand -hex 32`)
   - `SMTP_*` — if you want forgot-password emails
4. Edit **`docker-compose.yml`** if needed:
   - **Volume:** change `./data:/app/data` to your appdata path, e.g.  
     `/srv/.../appdata/ielts-writing:/app/data`
   - **Pre-built image:** comment out `build: .` and uncomment the `image:` line (GHCR).
5. Dockge → **New stack** → point at this folder with **`docker-compose.yml`** → **Deploy**.

Updates: `docker compose pull && docker compose up -d` (image mode) or `docker compose up -d --build` (build mode).

## Setup (PostgreSQL — high concurrency)

1. Same folder + `cp .env.example .env`
2. Edit **`.env`** — required extras:
   - `SECRET_KEY`
   - `POSTGRES_PASSWORD` — strong password (used by both app and Postgres container)
   - Optional: `GUNICORN_WORKERS=2`, `GUNICORN_THREADS=4` (already defaulted in compose)
3. Dockge → **New stack** → use **`docker-compose.postgres.yml`** (not `docker-compose.yml`) → **Deploy**.

   Or from CLI:

   ```bash
   docker compose -f docker-compose.postgres.yml pull
   docker compose -f docker-compose.postgres.yml up -d
   ```

4. **Migrating from SQLite:** run `migrate_sqlite_to_postgres.py` once after Postgres is up (see repo root).

Postgres data is stored in the Docker volume `postgres-data`. App uploads still use `./data` (change volume path for NAS as needed).

## Appdata folder (once)

```bash
mkdir -p /srv/.../appdata/ielts-writing
```

SQLite backups: `appdata/ielts-writing/backups/app.db.latest.bak` (SQLite stack only)

## GitHub images

Push to `main` → GitHub Actions publishes both packages:

- `ghcr.io/danuja01/ielts-writing-practice-simulator:latest`
- `ghcr.io/danuja01/ielts-writing-practice-postgres:latest`

Set each package **public** under GitHub → Packages if the NAS cannot pull private images.
