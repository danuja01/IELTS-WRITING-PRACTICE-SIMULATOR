# Host on NAS with Dockge

Repo: https://github.com/danuja01/IELTS-WRITING-PRACTICE-SIMULATOR

## One compose file

Use **`docker-compose.yml`** in the project root (no other compose variants).

## Setup

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
5. Dockge → **New stack** → point at this folder (or paste `docker-compose.yml` + add `.env` beside it) → **Deploy**.

Updates: `docker compose pull && docker compose up -d` (image mode) or `docker compose up -d --build` (build mode).

## Appdata folder (once)

```bash
mkdir -p /srv/.../appdata/ielts-writing
```

Backups: `appdata/ielts-writing/backups/app.db.latest.bak`

## GitHub image (optional)

Push to `main` → GitHub Actions publishes `ghcr.io/danuja01/ielts-writing-practice-simulator:latest`.  
Set the package **public** under GitHub → Packages if the NAS cannot pull private images.
