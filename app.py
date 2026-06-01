"""Minimal IELTS Writing Practice — Flask + SQLite."""
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    abort,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("IELTS_DB", os.path.join(APP_DIR, "data", "app.db"))
DATA_DIR = os.path.dirname(DB_PATH)
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
ALLOWED_IMAGE_EXT = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})
MAX_IMAGE_BYTES = 8 * 1024 * 1024


def _load_version() -> str:
    try:
        with open(os.path.join(APP_DIR, "VERSION"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return os.environ.get("APP_VERSION", "dev")


__version__ = _load_version()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


def get_db():
    if "db" not in g:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with closing(sqlite3.connect(DB_PATH)) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                prompt TEXT NOT NULL,
                task_type TEXT DEFAULT 'task2',
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
                updated_at TEXT NOT NULL
            );
            """
        )
        db.commit()
        _migrate_questions_image(db)


def _migrate_questions_image(db):
    cols = {row[1] for row in db.execute("PRAGMA table_info(questions)").fetchall()}
    if "image_path" not in cols:
        db.execute("ALTER TABLE questions ADD COLUMN image_path TEXT")
        db.commit()


def _save_question_image(file_storage, user_id: int, question_id: int) -> str:
    if not file_storage or not file_storage.filename:
        return ""
    ext = Path(secure_filename(file_storage.filename)).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXT:
        raise ValueError("image must be PNG, JPG, WEBP, or GIF")
    raw = file_storage.read()
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("image too large (max 8 MB)")
    rel = f"{user_id}/{question_id}{ext}"
    dest = os.path.join(UPLOAD_DIR, rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(raw)
    return rel


def _delete_question_image(image_path: str | None) -> None:
    if not image_path:
        return
    full = os.path.join(UPLOAD_DIR, image_path)
    if os.path.isfile(full):
        os.remove(full)


def _question_json(row) -> dict:
    d = dict(row)
    d["has_image"] = bool(d.get("image_path"))
    if d["has_image"]:
        d["image_url"] = url_for("question_image", qid=d["id"])
    else:
        d["image_url"] = None
    return d


def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "login required"}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return wrapped


def now_iso():
    return datetime.now(timezone.utc).isoformat()


@app.before_request
def ensure_db():
    get_db()


with app.app_context():
    init_db()


@app.context_processor
def inject_version():
    return {"app_version": __version__}


@app.route("/api/version")
def api_version():
    return jsonify({"version": __version__})


# --- Pages ---


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("home"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET"])
def login():
    if "user_id" in session:
        return redirect(url_for("home"))
    return render_template("login.html")


@app.route("/home")
@login_required
def home():
    return render_template("home.html", username=session.get("username", ""))


@app.route("/practice/<int:question_id>")
@login_required
def practice(question_id):
    return render_template("practice.html", question_id=question_id)


# --- API ---


@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if len(username) < 2 or len(password) < 4:
        return jsonify({"error": "username (2+) and password (4+) required"}), 400
    db = get_db()
    try:
        db.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, generate_password_hash(password), now_iso()),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "username already taken"}), 409
    row = db.execute(
        "SELECT id, username FROM users WHERE username = ?", (username,)
    ).fetchone()
    session["user_id"] = row["id"]
    session["username"] = row["username"]
    return jsonify({"ok": True, "username": row["username"]})


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    row = get_db().execute(
        "SELECT id, username, password_hash FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    if not row or not check_password_hash(row["password_hash"], password):
        return jsonify({"error": "invalid credentials"}), 401
    session["user_id"] = row["id"]
    session["username"] = row["username"]
    return jsonify({"ok": True, "username": row["username"]})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/questions", methods=["GET"])
@login_required
def list_questions():
    rows = get_db().execute(
        """SELECT id, title, prompt, task_type, image_path, created_at
           FROM questions WHERE user_id = ? ORDER BY id DESC""",
        (session["user_id"],),
    ).fetchall()
    return jsonify([_question_json(r) for r in rows])


@app.route("/api/questions", methods=["POST"])
@login_required
def create_question():
    if request.content_type and "multipart/form-data" in request.content_type:
        title = (request.form.get("title") or "Untitled").strip()[:200]
        prompt = (request.form.get("prompt") or "").strip()
        task_type = (request.form.get("task_type") or "task2").strip()[:20]
        image_file = request.files.get("image")
    else:
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "Untitled").strip()[:200]
        prompt = (data.get("prompt") or "").strip()
        task_type = (data.get("task_type") or "task2").strip()[:20]
        image_file = None

    if not prompt:
        return jsonify({"error": "prompt required"}), 400

    db = get_db()
    cur = db.execute(
        """INSERT INTO questions (user_id, title, prompt, task_type, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (session["user_id"], title, prompt, task_type, now_iso()),
    )
    db.commit()
    qid = cur.lastrowid
    image_path = ""

    if task_type == "task1" and image_file and image_file.filename:
        try:
            image_path = _save_question_image(
                image_file, session["user_id"], qid
            )
            db.execute(
                "UPDATE questions SET image_path = ? WHERE id = ?",
                (image_path, qid),
            )
            db.commit()
        except ValueError as e:
            db.execute("DELETE FROM questions WHERE id = ?", (qid,))
            db.commit()
            return jsonify({"error": str(e)}), 400

    row = db.execute("SELECT * FROM questions WHERE id = ?", (qid,)).fetchone()
    return jsonify(_question_json(row)), 201


@app.route("/api/questions/<int:qid>", methods=["GET"])
@login_required
def get_question(qid):
    row = get_db().execute(
        "SELECT * FROM questions WHERE id = ? AND user_id = ?",
        (qid, session["user_id"]),
    ).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    return jsonify(_question_json(row))


@app.route("/api/questions/<int:qid>/image")
@login_required
def question_image(qid):
    row = get_db().execute(
        "SELECT image_path FROM questions WHERE id = ? AND user_id = ?",
        (qid, session["user_id"]),
    ).fetchone()
    if not row or not row["image_path"]:
        abort(404)
    directory = UPLOAD_DIR
    filename = row["image_path"]
    # image_path stored as user_id/qid.ext — send_from_directory needs parent + name
    parent = os.path.join(directory, os.path.dirname(filename))
    name = os.path.basename(filename)
    if not os.path.isfile(os.path.join(parent, name)):
        abort(404)
    return send_from_directory(parent, name)


@app.route("/api/questions/<int:qid>", methods=["DELETE"])
@login_required
def delete_question(qid):
    db = get_db()
    row = db.execute(
        "SELECT image_path FROM questions WHERE id = ? AND user_id = ?",
        (qid, session["user_id"]),
    ).fetchone()
    if row:
        _delete_question_image(row["image_path"])
    db.execute(
        "DELETE FROM questions WHERE id = ? AND user_id = ?",
        (qid, session["user_id"]),
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/writings", methods=["GET"])
@login_required
def list_writings():
    rows = get_db().execute(
        """SELECT w.id, w.question_id, w.content, w.started_at, w.finished_at,
                  w.elapsed_ms, w.at_40min_ms, w.words_at_40min, w.final_words,
                  w.updated_at, q.title AS question_title
           FROM writings w
           LEFT JOIN questions q ON q.id = w.question_id
           WHERE w.user_id = ? AND w.finished_at IS NOT NULL
           ORDER BY w.finished_at DESC LIMIT 50""",
        (session["user_id"],),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/writings/active/<int:qid>", methods=["GET"])
@login_required
def get_active_writing(qid):
    row = get_db().execute(
        """SELECT * FROM writings
           WHERE user_id = ? AND question_id = ? AND finished_at IS NULL
           ORDER BY id DESC LIMIT 1""",
        (session["user_id"], qid),
    ).fetchone()
    return jsonify(dict(row) if row else None)


@app.route("/api/writings", methods=["POST"])
@login_required
def save_writing():
    data = request.get_json(silent=True) or {}
    qid = data.get("question_id")
    content = data.get("content") or ""
    writing_id = data.get("id")
    started_at = data.get("started_at")
    elapsed_ms = data.get("elapsed_ms")
    at_40min_ms = data.get("at_40min_ms")
    words_at_40min = data.get("words_at_40min")
    finish = data.get("finish", False)
    final_words = data.get("final_words")

    db = get_db()
    ts = now_iso()

    if writing_id:
        row = db.execute(
            "SELECT id FROM writings WHERE id = ? AND user_id = ?",
            (writing_id, session["user_id"]),
        ).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
        db.execute(
            """UPDATE writings SET
               content = ?, elapsed_ms = ?, at_40min_ms = ?, words_at_40min = ?,
               final_words = ?, updated_at = ?,
               finished_at = CASE WHEN ? THEN ? ELSE finished_at END
               WHERE id = ?""",
            (
                content,
                elapsed_ms,
                at_40min_ms,
                words_at_40min,
                final_words if finish else None,
                ts,
                1 if finish else 0,
                ts if finish else None,
                writing_id,
            ),
        )
        db.commit()
        out = db.execute("SELECT * FROM writings WHERE id = ?", (writing_id,)).fetchone()
        return jsonify(dict(out))

    cur = db.execute(
        """INSERT INTO writings
           (user_id, question_id, content, started_at, elapsed_ms, at_40min_ms,
            words_at_40min, final_words, finished_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session["user_id"],
            qid,
            content,
            started_at or ts,
            elapsed_ms,
            at_40min_ms,
            words_at_40min,
            final_words if finish else None,
            ts if finish else None,
            ts,
        ),
    )
    db.commit()
    out = db.execute("SELECT * FROM writings WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(dict(out)), 201


if __name__ == "__main__":
    # Local dev only — Docker/production uses gunicorn (see Dockerfile)
    port = int(os.environ.get("PORT", 5050))
    debug = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true")
    app.run(host="0.0.0.0", port=port, debug=debug)
