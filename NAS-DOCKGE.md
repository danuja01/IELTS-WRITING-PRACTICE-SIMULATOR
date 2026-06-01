# Host on NAS with Dockge

Paths used on your server:

| Purpose | Path |
|--------|------|
| Persistent data (SQLite) | `/srv/dev-disk-by-uuid-9ac22f70-05c6-442f-993b-0d9ca1ae5988/appdata/ielts-writing` |
| Dockge stack (compose + app files) | `/srv/dev-disk-by-uuid-9ac22f70-05c6-442f-993b-0d9ca1ae5988/docker-compose/ielts-writing` |

---

## Step 1 — Create the appdata folder (once)

SSH into the NAS or use the file manager:

```bash
mkdir -p /srv/dev-disk-by-uuid-9ac22f70-05c6-442f-993b-0d9ca1ae5988/appdata/ielts-writing
```

This is where `app.db` will live. Dockge does **not** need to create this; only the compose stack folder appears when you add the stack.

---

## Step 2 — Copy the app into the stack folder

Copy these from your Mac into  
`/srv/.../docker-compose/ielts-writing/`  
(SMB share, `scp`, or File Station):

```
ielts-writing/
├── docker-compose.yml    ← use docker-compose.nas.yml from the project (renamed)
├── Dockerfile
├── app.py
├── requirements.txt
├── static/               ← whole folder
└── templates/            ← whole folder
```

**Do not copy:** `.venv`, `data/`, `.git` (optional).

Example from your Mac (adjust NAS IP and user):

```bash
NAS="root@192.168.1.50"
STACK="/srv/dev-disk-by-uuid-9ac22f70-05c6-442f-993b-0d9ca1ae5988/docker-compose/ielts-writing"

ssh $NAS "mkdir -p $STACK"

cd "/Users/danuja/Desktop/IELTS WRITING"
scp Dockerfile app.py requirements.txt $NAS:$STACK/
scp -r static templates $NAS:$STACK/
scp docker-compose.nas.yml $NAS:$STACK/docker-compose.yml
```

---

## Step 3 — Edit secrets in compose

On the NAS, open `docker-compose.yml` in the stack folder and set:

```yaml
SECRET_KEY: "your-long-random-secret-here"
```

Generate one (on NAS or Mac):

```bash
openssl rand -hex 32
```

---

## Step 4 — Deploy in Dockge

1. Open **Dockge** → **+ Compose** (or **New Stack**).
2. **Name:** `ielts-writing` (this creates `docker-compose/ielts-writing` if it matches your setup).
3. Either:
   - **Paste** the contents of `docker-compose.nas.yml`, **or**
   - Point Dockge at the existing folder if it already has the files from Step 2.
4. Ensure **Compose path** / working directory is the stack folder that contains `Dockerfile` and `app.py`.
5. Click **Deploy** / **Start** (Dockge will run `docker compose build` then `up -d`).

First deploy builds the image (1–2 minutes). Later restarts are instant.

---

## Step 5 — Open the app

Browser:

```
http://<NAS-IP>:5050
```

If port 5050 is taken, change the left side in compose, e.g. `"8080:5050"`, redeploy, then use port 8080.

---

## Updates (after you change code on Mac)

Copy changed files to the stack folder again, then in Dockge: **Recreate** or:

```bash
cd /srv/dev-disk-by-uuid-9ac22f70-05c6-442f-993b-0d9ca1ae5988/docker-compose/ielts-writing
docker compose up -d --build
```

Your database in `appdata/ielts-writing` is kept.

---

## Backup

Back up only:

```
/srv/.../appdata/ielts-writing/
```

That folder contains `app.db` (all users, questions, writings).

---

## Troubleshooting

| Problem | Fix |
|--------|-----|
| Build fails “no such file Dockerfile” | Stack folder must contain `Dockerfile` + `app.py`; check Dockge working directory |
| Permission denied on appdata | `chown -R 1000:1000` or match your Docker user; Alpine container runs as root by default so usually fine |
| Empty app after deploy | DB is in appdata volume; ensure volume path matches compose |
| Can’t reach from phone/PC | Open port 5050 on NAS firewall; use LAN IP not `localhost` |
