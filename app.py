"""IELTS Writing Practice — Flask + SQLite."""
import json
import os
import re
import secrets
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

from backup import start_backup_scheduler

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("IELTS_DB", os.path.join(APP_DIR, "data", "app.db"))
DATA_DIR = os.path.dirname(DB_PATH)
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
ALLOWED_IMAGE_EXT = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})
MAX_IMAGE_BYTES = 8 * 1024 * 1024
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

SETUP_WHITELIST = {"/setup-admin", "/api/setup-admin", "/api/version"}
CHANGE_PW_WHITELIST = {"/change-password", "/api/change-password", "/api/logout"}


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


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def has_admin():
    row = get_db().execute("SELECT 1 FROM users WHERE is_admin = 1 LIMIT 1").fetchone()
    return row is not None


def _migrate(db):
    def add_col(table, col, typedef):
        cols = {r[1] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}
        if col not in cols:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")

    add_col("users", "email", "TEXT")
    add_col("users", "is_admin", "INTEGER NOT NULL DEFAULT 0")
    add_col("users", "must_change_password", "INTEGER NOT NULL DEFAULT 0")
    add_col("questions", "image_path", "TEXT")
    add_col("questions", "category_id", "INTEGER REFERENCES categories(id)")
    add_col("questions", "prompt_highlights", "TEXT")
    add_col("writings", "paragraph_stats", "TEXT")
    db.commit()

    db.execute(
        """CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )"""
    )
    db.commit()


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with closing(sqlite3.connect(DB_PATH)) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                email TEXT,
                is_admin INTEGER NOT NULL DEFAULT 0,
                must_change_password INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
                title TEXT NOT NULL,
                prompt TEXT NOT NULL,
                task_type TEXT DEFAULT 'task2',
                image_path TEXT,
                prompt_highlights TEXT,
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
                paragraph_stats TEXT,
                updated_at TEXT NOT NULL
            );
            """
        )
        db.commit()
        _migrate(db)


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


def _delete_question_image(image_path):
    if not image_path:
        return
    full = os.path.join(UPLOAD_DIR, image_path)
    if os.path.isfile(full):
        os.remove(full)


def _parse_highlights(raw):
    if not raw:
        return []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _apply_highlights(text, highlights):
    if not highlights:
        return text
    text = text or ""
    sorted_h = sorted(
        [h for h in highlights if isinstance(h, dict)],
        key=lambda x: x.get("start", 0),
        reverse=True,
    )
    for h in sorted_h:
        start, end = int(h.get("start", 0)), int(h.get("end", 0))
        if 0 <= start < end <= len(text):
            text = (
                text[:start]
                + "<mark class=\"q-highlight\">"
                + text[start:end]
                + "</mark>"
                + text[end:]
            )
    return text


def _question_json(row, for_user_id=None):
    d = dict(row)
    uid = for_user_id if for_user_id is not None else d.get("user_id")
    d["has_image"] = bool(d.get("image_path"))
    d["image_url"] = url_for("question_image", qid=d["id"]) if d["has_image"] else None
    d["highlights"] = _parse_highlights(d.get("prompt_highlights"))
    d["prompt_html"] = _apply_highlights(d.get("prompt") or "", d["highlights"])
    return d


def _user_json(row):
    d = dict(row)
    d.pop("password_hash", None)
    d["is_admin"] = bool(d.get("is_admin"))
    d["must_change_password"] = bool(d.get("must_change_password"))
    return d


def _writing_json(row):
    d = dict(row)
    ps = d.get("paragraph_stats")
    if ps and isinstance(ps, str):
        try:
            d["paragraph_stats"] = json.loads(ps)
        except json.JSONDecodeError:
            d["paragraph_stats"] = []
    elif not ps:
        d["paragraph_stats"] = []
    return d


def _set_session(user_row):
    session["user_id"] = user_row["id"]
    session["username"] = user_row["username"]
    session["is_admin"] = bool(user_row["is_admin"])
    session["must_change_password"] = bool(user_row["must_change_password"])


def _login_redirect_url():
    if session.get("must_change_password"):
        return url_for("change_password")
    if session.get("is_admin"):
        return url_for("admin_home")
    return url_for("home")


def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "login required"}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return wrapped


def student_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "login required"}), 401
            return redirect(url_for("login"))
        if session.get("is_admin"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "admin cannot use student features"}), 403
            return redirect(url_for("admin_home"))
        return f(*args, **kwargs)

    return wrapped


def admin_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "login required"}), 401
            return redirect(url_for("login"))
        if not session.get("is_admin"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "admin required"}), 403
            return redirect(url_for("home"))
        return f(*args, **kwargs)

    return wrapped


@app.before_request
def before_request():
    get_db()
    path = request.path

    if path.startswith("/static/"):
        return None

    if not has_admin():
        if path not in SETUP_WHITELIST:
            if path.startswith("/api/"):
                return jsonify({"error": "setup required", "setup": True}), 503
            return redirect(url_for("setup_admin"))
        return None

    if "user_id" in session and session.get("must_change_password"):
        if path not in CHANGE_PW_WHITELIST and not path.startswith("/static/"):
            if path.startswith("/api/"):
                return jsonify({"error": "password change required"}), 403
            return redirect(url_for("change_password"))

    if "user_id" in session:
        if session.get("is_admin"):
            student_paths = ("/home", "/practice", "/history", "/api/questions", "/api/writings", "/api/categories")
            if any(path == p or path.startswith(p + "/") for p in student_paths):
                if path.startswith("/api/"):
                    return jsonify({"error": "admin panel only"}), 403
                if path.startswith("/practice") or path == "/home" or path.startswith("/history"):
                    return redirect(url_for("admin_home"))
        elif path.startswith("/admin") or path.startswith("/api/admin"):
            if path.startswith("/api/"):
                return jsonify({"error": "admin required"}), 403
            return redirect(url_for("home"))

    return None


with app.app_context():
    init_db()
    start_backup_scheduler(DB_PATH, DATA_DIR)


@app.context_processor
def inject_version():
    return {"app_version": __version__}


@app.route("/api/version")
def api_version():
    return jsonify({"version": __version__})


# --- Setup & auth pages ---


@app.route("/")
def index():
    if not has_admin():
        return redirect(url_for("setup_admin"))
    if "user_id" not in session:
        return redirect(url_for("login"))
    return redirect(_login_redirect_url())


@app.route("/setup-admin", methods=["GET"])
def setup_admin():
    if has_admin():
        return redirect(url_for("login"))
    return render_template("setup_admin.html")


@app.route("/api/setup-admin", methods=["POST"])
def api_setup_admin():
    if has_admin():
        return jsonify({"error": "admin already exists"}), 400
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""
    if len(username) < 2 or len(password) < 4:
        return jsonify({"error": "username (2+) and password (4+) required"}), 400
    if not email or not EMAIL_RE.match(email):
        return jsonify({"error": "valid email required"}), 400
    db = get_db()
    try:
        db.execute(
            """INSERT INTO users (username, email, password_hash, is_admin,
               must_change_password, created_at) VALUES (?, ?, ?, 1, 0, ?)""",
            (username, email, generate_password_hash(password), now_iso()),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "username already taken"}), 409
    row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    _set_session(row)
    return jsonify({"ok": True, "redirect": url_for("admin_home")})


@app.route("/login", methods=["GET"])
def login_page():
    if not has_admin():
        return redirect(url_for("setup_admin"))
    if "user_id" in session:
        return redirect(_login_redirect_url())
    return render_template("login.html")


@app.route("/change-password", methods=["GET"])
@login_required
def change_password():
    if not session.get("must_change_password") and not session.get("is_admin"):
        return redirect(url_for("home"))
    return render_template("change_password.html")


@app.route("/api/register", methods=["POST"])
def register():
    if not has_admin():
        return jsonify({"error": "setup required"}), 503
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""
    if len(username) < 2 or len(password) < 4:
        return jsonify({"error": "username (2+) and password (4+) required"}), 400
    if not email or not EMAIL_RE.match(email):
        return jsonify({"error": "valid email required"}), 400
    db = get_db()
    try:
        db.execute(
            """INSERT INTO users (username, email, password_hash, is_admin,
               must_change_password, created_at) VALUES (?, ?, ?, 0, 0, ?)""",
            (username, email, generate_password_hash(password), now_iso()),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "username already taken"}), 409
    row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    _set_session(row)
    return jsonify({
        "ok": True,
        "redirect": _login_redirect_url(),
        "is_admin": False,
        "must_change_password": False,
    })


@app.route("/api/login", methods=["POST"])
def api_login():
    if not has_admin():
        return jsonify({"error": "setup required"}), 503
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    row = get_db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if not row or not check_password_hash(row["password_hash"], password):
        return jsonify({"error": "invalid credentials"}), 401
    _set_session(row)
    return jsonify({
        "ok": True,
        "redirect": _login_redirect_url(),
        "is_admin": bool(row["is_admin"]),
        "must_change_password": bool(row["must_change_password"]),
    })


@app.route("/api/change-password", methods=["POST"])
@login_required
def api_change_password():
    data = request.get_json(silent=True) or {}
    password = data.get("password") or ""
    confirm = data.get("confirm") or ""
    if len(password) < 4:
        return jsonify({"error": "password must be at least 4 characters"}), 400
    if password != confirm:
        return jsonify({"error": "passwords do not match"}), 400
    db = get_db()
    db.execute(
        "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
        (generate_password_hash(password), session["user_id"]),
    )
    db.commit()
    session["must_change_password"] = False
    return jsonify({"ok": True, "redirect": _login_redirect_url()})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok": True})


# --- Student pages ---


@app.route("/home")
@student_required
def home():
    return render_template("home.html", username=session.get("username", ""))


@app.route("/practice/<int:question_id>")
@student_required
def practice(question_id):
    return render_template("practice.html", question_id=question_id)


@app.route("/history")
@student_required
def history_page():
    return render_template("history.html")


@app.route("/history/<int:question_id>")
@student_required
def history_question_page(question_id):
    return render_template("history_question.html", question_id=question_id)


@app.route("/history/writing/<int:writing_id>")
@student_required
def history_writing_page(writing_id):
    return render_template("history_writing.html", writing_id=writing_id)


# --- Admin pages ---


@app.route("/admin")
@admin_required
def admin_home():
    return render_template("admin.html", username=session.get("username", ""))


@app.route("/admin/users/<int:user_id>")
@admin_required
def admin_user_page(user_id):
    return render_template("admin_user.html", user_id=user_id)


@app.route("/admin/questions/<int:qid>/edit")
@admin_required
def admin_edit_question_page(qid):
    return render_template("admin_edit_question.html", question_id=qid)


@app.route("/admin/users/<int:uid>/history/<int:question_id>")
@admin_required
def admin_history_question(uid, question_id):
    return render_template(
        "history_question.html",
        question_id=question_id,
        view_user_id=uid,
    )


@app.route("/admin/writing/<int:writing_id>")
@admin_required
def admin_writing_detail(writing_id):
    uid = request.args.get("user_id", type=int)
    return render_template(
        "history_writing.html",
        writing_id=writing_id,
        admin_view=True,
        user_id=uid,
    )


# --- Categories API ---


@app.route("/api/categories", methods=["GET"])
@student_required
def list_categories():
    rows = get_db().execute(
        """SELECT c.*, (SELECT COUNT(*) FROM questions q WHERE q.category_id = c.id) AS question_count
           FROM categories c WHERE c.user_id = ? ORDER BY c.sort_order, c.name""",
        (session["user_id"],),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/categories", methods=["POST"])
@student_required
def create_category():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()[:100]
    if not name:
        return jsonify({"error": "name required"}), 400
    db = get_db()
    cur = db.execute(
        "INSERT INTO categories (user_id, name, sort_order, created_at) VALUES (?, ?, 0, ?)",
        (session["user_id"], name, now_iso()),
    )
    db.commit()
    row = db.execute("SELECT * FROM categories WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201


@app.route("/api/categories/<int:cid>", methods=["PUT"])
@student_required
def update_category(cid):
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()[:100]
    if not name:
        return jsonify({"error": "name required"}), 400
    db = get_db()
    db.execute(
        "UPDATE categories SET name = ? WHERE id = ? AND user_id = ?",
        (name, cid, session["user_id"]),
    )
    db.commit()
    row = db.execute("SELECT * FROM categories WHERE id = ?", (cid,)).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    return jsonify(dict(row))


@app.route("/api/categories/<int:cid>", methods=["DELETE"])
@student_required
def delete_category(cid):
    db = get_db()
    db.execute(
        "UPDATE questions SET category_id = NULL WHERE category_id = ? AND user_id = ?",
        (cid, session["user_id"]),
    )
    db.execute("DELETE FROM categories WHERE id = ? AND user_id = ?", (cid, session["user_id"]))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/questions/<int:qid>/move", methods=["POST"])
@student_required
def move_question(qid):
    data = request.get_json(silent=True) or {}
    category_id = data.get("category_id")
    db = get_db()
    if category_id is not None:
        cat = db.execute(
            "SELECT id FROM categories WHERE id = ? AND user_id = ?",
            (category_id, session["user_id"]),
        ).fetchone()
        if not cat:
            return jsonify({"error": "category not found"}), 404
    db.execute(
        "UPDATE questions SET category_id = ? WHERE id = ? AND user_id = ?",
        (category_id, qid, session["user_id"]),
    )
    db.commit()
    return jsonify({"ok": True})


# --- Questions API ---


@app.route("/api/questions", methods=["GET"])
@student_required
def list_questions():
    rows = get_db().execute(
        """SELECT q.*, c.name AS category_name
           FROM questions q
           LEFT JOIN categories c ON c.id = q.category_id
           WHERE q.user_id = ? ORDER BY (c.name IS NULL), c.name, q.id DESC""",
        (session["user_id"],),
    ).fetchall()
    return jsonify([_question_json(r) for r in rows])


@app.route("/api/questions", methods=["POST"])
@student_required
def create_question():
    category_id = None
    if request.content_type and "multipart/form-data" in request.content_type:
        title = (request.form.get("title") or "Untitled").strip()[:200]
        prompt = (request.form.get("prompt") or "").strip()
        task_type = (request.form.get("task_type") or "task2").strip()[:20]
        image_file = request.files.get("image")
        raw_cat = request.form.get("category_id")
        category_id = int(raw_cat) if raw_cat and raw_cat.isdigit() else None
    else:
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "Untitled").strip()[:200]
        prompt = (data.get("prompt") or "").strip()
        task_type = (data.get("task_type") or "task2").strip()[:20]
        image_file = None
        category_id = data.get("category_id")

    if not prompt:
        return jsonify({"error": "prompt required"}), 400

    db = get_db()
    if category_id:
        cat = db.execute(
            "SELECT id FROM categories WHERE id = ? AND user_id = ?",
            (category_id, session["user_id"]),
        ).fetchone()
        if not cat:
            return jsonify({"error": "category not found"}), 404

    cur = db.execute(
        """INSERT INTO questions (user_id, category_id, title, prompt, task_type, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (session["user_id"], category_id, title, prompt, task_type, now_iso()),
    )
    db.commit()
    qid = cur.lastrowid

    if task_type == "task1" and image_file and image_file.filename:
        try:
            image_path = _save_question_image(image_file, session["user_id"], qid)
            db.execute("UPDATE questions SET image_path = ? WHERE id = ?", (image_path, qid))
            db.commit()
        except ValueError as e:
            db.execute("DELETE FROM questions WHERE id = ?", (qid,))
            db.commit()
            return jsonify({"error": str(e)}), 400

    row = db.execute("SELECT * FROM questions WHERE id = ?", (qid,)).fetchone()
    return jsonify(_question_json(row)), 201


@app.route("/api/questions/<int:qid>", methods=["GET"])
@student_required
def get_question(qid):
    row = get_db().execute(
        "SELECT * FROM questions WHERE id = ? AND user_id = ?",
        (qid, session["user_id"]),
    ).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    return jsonify(_question_json(row))


@app.route("/api/questions/<int:qid>/highlights", methods=["PUT"])
@student_required
def update_highlights(qid):
    data = request.get_json(silent=True) or {}
    highlights = data.get("highlights", [])
    if not isinstance(highlights, list):
        return jsonify({"error": "highlights must be a list"}), 400
    db = get_db()
    row = db.execute(
        "SELECT prompt FROM questions WHERE id = ? AND user_id = ?",
        (qid, session["user_id"]),
    ).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    prompt_len = len(row["prompt"] or "")
    clean = []
    for h in highlights:
        if not isinstance(h, dict):
            continue
        start, end = int(h.get("start", 0)), int(h.get("end", 0))
        if 0 <= start < end <= prompt_len:
            clean.append({"start": start, "end": end})
    db.execute(
        "UPDATE questions SET prompt_highlights = ? WHERE id = ?",
        (json.dumps(clean), qid),
    )
    db.commit()
    out = db.execute("SELECT * FROM questions WHERE id = ?", (qid,)).fetchone()
    return jsonify(_question_json(out))


@app.route("/api/questions/<int:qid>/image")
@login_required
def question_image(qid):
    if session.get("is_admin"):
        row = get_db().execute(
            "SELECT image_path FROM questions WHERE id = ?", (qid,)
        ).fetchone()
    else:
        row = get_db().execute(
            "SELECT image_path FROM questions WHERE id = ? AND user_id = ?",
            (qid, session["user_id"]),
        ).fetchone()
    if not row or not row["image_path"]:
        abort(404)
    parent = os.path.join(UPLOAD_DIR, os.path.dirname(row["image_path"]))
    name = os.path.basename(row["image_path"])
    return send_from_directory(parent, name)


@app.route("/api/questions/<int:qid>", methods=["DELETE"])
@student_required
def delete_question(qid):
    db = get_db()
    row = db.execute(
        "SELECT image_path FROM questions WHERE id = ? AND user_id = ?",
        (qid, session["user_id"]),
    ).fetchone()
    if row:
        _delete_question_image(row["image_path"])
    db.execute("DELETE FROM questions WHERE id = ? AND user_id = ?", (qid, session["user_id"]))
    db.commit()
    return jsonify({"ok": True})


# --- Writings API ---


@app.route("/api/writings", methods=["GET"])
@student_required
def list_writings():
    grouped = request.args.get("grouped") == "1"
    db = get_db()
    if grouped:
        rows = db.execute(
            """SELECT q.id AS question_id, q.title, q.task_type,
                      COUNT(w.id) AS attempt_count,
                      MAX(w.finished_at) AS last_finished,
                      MAX(w.final_words) AS best_words
               FROM questions q
               INNER JOIN writings w ON w.question_id = q.id AND w.finished_at IS NOT NULL
               WHERE q.user_id = ? AND w.user_id = ?
               GROUP BY q.id ORDER BY last_finished DESC""",
            (session["user_id"], session["user_id"]),
        ).fetchall()
        return jsonify([dict(r) for r in rows])

    rows = db.execute(
        """SELECT w.id, w.question_id, w.content, w.started_at, w.finished_at,
                  w.elapsed_ms, w.at_40min_ms, w.words_at_40min, w.final_words,
                  w.paragraph_stats, w.updated_at, q.title AS question_title
           FROM writings w
           LEFT JOIN questions q ON q.id = w.question_id
           WHERE w.user_id = ? AND w.finished_at IS NOT NULL
           ORDER BY w.finished_at DESC LIMIT 10""",
        (session["user_id"],),
    ).fetchall()
    return jsonify([_writing_json(r) for r in rows])


@app.route("/api/writings/by-question/<int:qid>", methods=["GET"])
@student_required
def writings_by_question(qid):
    rows = get_db().execute(
        """SELECT w.*, q.title AS question_title, q.task_type
           FROM writings w
           JOIN questions q ON q.id = w.question_id
           WHERE w.user_id = ? AND w.question_id = ? AND w.finished_at IS NOT NULL
           ORDER BY w.finished_at DESC""",
        (session["user_id"], qid),
    ).fetchall()
    if not rows:
        q = get_db().execute(
            "SELECT id, title FROM questions WHERE id = ? AND user_id = ?",
            (qid, session["user_id"]),
        ).fetchone()
        if not q:
            return jsonify({"error": "not found"}), 404
        return jsonify({"question": dict(q), "attempts": []})
    return jsonify({
        "question": {"id": qid, "title": rows[0]["question_title"], "task_type": rows[0]["task_type"]},
        "attempts": [_writing_json(r) for r in rows],
    })


@app.route("/api/writings/<int:wid>", methods=["GET"])
@login_required
def get_writing(wid):
    if session.get("is_admin"):
        row = get_db().execute(
            """SELECT w.*, q.title AS question_title, q.task_type, u.username
               FROM writings w
               LEFT JOIN questions q ON q.id = w.question_id
               JOIN users u ON u.id = w.user_id
               WHERE w.id = ?""",
            (wid,),
        ).fetchone()
    else:
        row = get_db().execute(
            """SELECT w.*, q.title AS question_title, q.task_type
               FROM writings w
               LEFT JOIN questions q ON q.id = w.question_id
               WHERE w.id = ? AND w.user_id = ?""",
            (wid, session["user_id"]),
        ).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    return jsonify(_writing_json(row))


@app.route("/api/writings/active/<int:qid>", methods=["GET"])
@student_required
def get_active_writing(qid):
    row = get_db().execute(
        """SELECT * FROM writings
           WHERE user_id = ? AND question_id = ? AND finished_at IS NULL
           ORDER BY id DESC LIMIT 1""",
        (session["user_id"], qid),
    ).fetchone()
    return jsonify(_writing_json(row) if row else None)


@app.route("/api/writings", methods=["POST"])
@student_required
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
    paragraph_stats = data.get("paragraph_stats")
    ps_json = json.dumps(paragraph_stats) if paragraph_stats is not None else None

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
               final_words = ?, paragraph_stats = ?, updated_at = ?,
               finished_at = CASE WHEN ? THEN ? ELSE finished_at END
               WHERE id = ?""",
            (
                content, elapsed_ms, at_40min_ms, words_at_40min,
                final_words if finish else None, ps_json, ts,
                1 if finish else 0, ts if finish else None, writing_id,
            ),
        )
        db.commit()
        out = db.execute("SELECT * FROM writings WHERE id = ?", (writing_id,)).fetchone()
        return jsonify(_writing_json(out))

    cur = db.execute(
        """INSERT INTO writings
           (user_id, question_id, content, started_at, elapsed_ms, at_40min_ms,
            words_at_40min, final_words, paragraph_stats, finished_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session["user_id"], qid, content, started_at or ts,
            elapsed_ms, at_40min_ms, words_at_40min,
            final_words if finish else None, ps_json,
            ts if finish else None, ts,
        ),
    )
    db.commit()
    out = db.execute("SELECT * FROM writings WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(_writing_json(out)), 201


# --- Admin API ---


@app.route("/api/admin/users", methods=["GET"])
@admin_required
def admin_list_users():
    rows = get_db().execute(
        """SELECT id, username, email, is_admin, must_change_password, created_at
           FROM users ORDER BY is_admin DESC, username"""
    ).fetchall()
    return jsonify([_user_json(r) for r in rows])


@app.route("/api/admin/users/<int:uid>", methods=["GET"])
@admin_required
def admin_get_user(uid):
    row = get_db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    db = get_db()
    questions = db.execute(
        "SELECT * FROM questions WHERE user_id = ? ORDER BY id DESC", (uid,)
    ).fetchall()
    out_questions = []
    for q in questions:
        qd = _question_json(q)
        attempts = db.execute(
            """SELECT id, finished_at, final_words, elapsed_ms
               FROM writings
               WHERE user_id = ? AND question_id = ? AND finished_at IS NOT NULL
               ORDER BY finished_at DESC""",
            (uid, q["id"]),
        ).fetchall()
        qd["attempt_count"] = len(attempts)
        qd["attempts"] = [dict(a) for a in attempts]
        out_questions.append(qd)
    return jsonify({
        "user": _user_json(row),
        "questions": out_questions,
    })


@app.route("/api/admin/users/<int:uid>", methods=["PUT"])
@admin_required
def admin_update_user(uid):
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip()
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    if row["is_admin"] and uid != session["user_id"]:
        return jsonify({"error": "cannot edit other admins"}), 400
    if email and not EMAIL_RE.match(email):
        return jsonify({"error": "invalid email"}), 400
    if username:
        try:
            db.execute(
                "UPDATE users SET username = ?, email = ? WHERE id = ?",
                (username, email or row["email"], uid),
            )
            db.commit()
        except sqlite3.IntegrityError:
            return jsonify({"error": "username taken"}), 409
    out = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    return jsonify(_user_json(out))


@app.route("/api/admin/users/<int:uid>/reset-password", methods=["POST"])
@admin_required
def admin_reset_password(uid):
    data = request.get_json(silent=True) or {}
    temp = (data.get("password") or "").strip() or secrets.token_urlsafe(8)
    if len(temp) < 4:
        return jsonify({"error": "temp password too short"}), 400
    db = get_db()
    row = db.execute("SELECT is_admin FROM users WHERE id = ?", (uid,)).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    if row["is_admin"]:
        return jsonify({"error": "cannot reset admin password here"}), 400
    db.execute(
        "UPDATE users SET password_hash = ?, must_change_password = 1 WHERE id = ?",
        (generate_password_hash(temp), uid),
    )
    db.commit()
    return jsonify({"ok": True, "temp_password": temp})


@app.route("/api/admin/questions/<int:qid>", methods=["GET"])
@admin_required
def admin_get_question(qid):
    row = get_db().execute("SELECT * FROM questions WHERE id = ?", (qid,)).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    cats = get_db().execute(
        "SELECT * FROM categories WHERE user_id = ? ORDER BY name",
        (row["user_id"],),
    ).fetchall()
    return jsonify({
        "question": _question_json(row),
        "categories": [dict(c) for c in cats],
    })


@app.route("/api/admin/users/<int:uid>/writings/by-question/<int:qid>", methods=["GET"])
@admin_required
def admin_writings_by_question(uid, qid):
    rows = get_db().execute(
        """SELECT w.*, q.title AS question_title, q.task_type
           FROM writings w
           JOIN questions q ON q.id = w.question_id
           WHERE w.user_id = ? AND w.question_id = ? AND w.finished_at IS NOT NULL
           ORDER BY w.finished_at DESC""",
        (uid, qid),
    ).fetchall()
    if not rows:
        q = get_db().execute(
            "SELECT id, title FROM questions WHERE id = ? AND user_id = ?",
            (qid, uid),
        ).fetchone()
        if not q:
            return jsonify({"error": "not found"}), 404
        return jsonify({"question": dict(q), "attempts": []})
    return jsonify({
        "question": {"id": qid, "title": rows[0]["question_title"], "task_type": rows[0]["task_type"]},
        "attempts": [_writing_json(r) for r in rows],
    })


@app.route("/api/admin/questions/<int:qid>", methods=["PUT"])
@admin_required
def admin_update_question(qid):
    db = get_db()
    row = db.execute("SELECT * FROM questions WHERE id = ?", (qid,)).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404

    if request.content_type and "multipart/form-data" in request.content_type:
        title = (request.form.get("title") or row["title"]).strip()[:200]
        prompt = (request.form.get("prompt") or row["prompt"]).strip()
        task_type = (request.form.get("task_type") or row["task_type"]).strip()[:20]
        raw_cat = request.form.get("category_id")
        category_id = int(raw_cat) if raw_cat and raw_cat.isdigit() else None
        if raw_cat == "" or raw_cat == "null":
            category_id = None
        image_file = request.files.get("image")
        highlights_raw = request.form.get("prompt_highlights")
    else:
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or row["title"]).strip()[:200]
        prompt = (data.get("prompt") or row["prompt"]).strip()
        task_type = (data.get("task_type") or row["task_type"]).strip()[:20]
        category_id = data.get("category_id", row["category_id"])
        image_file = None
        highlights_raw = data.get("prompt_highlights")

    if category_id:
        cat = db.execute(
            "SELECT id FROM categories WHERE id = ? AND user_id = ?",
            (category_id, row["user_id"]),
        ).fetchone()
        if not cat:
            return jsonify({"error": "category not found"}), 404

    highlights_json = row["prompt_highlights"]
    if highlights_raw is not None:
        if isinstance(highlights_raw, str):
            highlights_json = highlights_raw
        else:
            highlights_json = json.dumps(highlights_raw)

    db.execute(
        """UPDATE questions SET title = ?, prompt = ?, task_type = ?,
           category_id = ?, prompt_highlights = ? WHERE id = ?""",
        (title, prompt, task_type, category_id, highlights_json, qid),
    )

    if task_type == "task1" and image_file and image_file.filename:
        try:
            _delete_question_image(row["image_path"])
            image_path = _save_question_image(image_file, row["user_id"], qid)
            db.execute("UPDATE questions SET image_path = ? WHERE id = ?", (image_path, qid))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    db.commit()
    out = db.execute("SELECT * FROM questions WHERE id = ?", (qid,)).fetchone()
    return jsonify(_question_json(out))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    debug = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true")
    app.run(host="0.0.0.0", port=port, debug=debug)
