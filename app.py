"""Minimal IELTS Writing Practice — Flask + SQLite."""
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from functools import wraps

from flask import (
    Flask,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("IELTS_DB", os.path.join(APP_DIR, "data", "app.db"))

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
        """SELECT id, title, prompt, task_type, created_at
           FROM questions WHERE user_id = ? ORDER BY id DESC""",
        (session["user_id"],),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/questions", methods=["POST"])
@login_required
def create_question():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "Untitled").strip()[:200]
    prompt = (data.get("prompt") or "").strip()
    task_type = (data.get("task_type") or "task2").strip()[:20]
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
    row = db.execute("SELECT * FROM questions WHERE id = ?", (qid,)).fetchone()
    return jsonify(dict(row)), 201


@app.route("/api/questions/<int:qid>", methods=["GET"])
@login_required
def get_question(qid):
    row = get_db().execute(
        "SELECT * FROM questions WHERE id = ? AND user_id = ?",
        (qid, session["user_id"]),
    ).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    return jsonify(dict(row))


@app.route("/api/questions/<int:qid>", methods=["DELETE"])
@login_required
def delete_question(qid):
    db = get_db()
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
    port = int(os.environ.get("PORT", 5050))
    debug = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true")
    app.run(host="0.0.0.0", port=port, debug=debug)
