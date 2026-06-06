"""IELTS Writing Practice - Flask + SQLite."""
import json
import os
import re
import secrets
import shutil
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

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

from ai_eval_util import DEFAULT_MODEL, evaluate_writing, evaluation_to_dict
from backup import start_backup_scheduler
from crypto_util import decrypt_secret, encrypt_secret, mask_api_key
from db_adapter import connect_db, init_database, is_sqlite
from mail_util import send_mail, smtp_configured

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("IELTS_DB", os.path.join(APP_DIR, "data", "app.db"))
DATA_DIR = os.path.dirname(DB_PATH)
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
ALLOWED_IMAGE_EXT = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})
MAX_IMAGE_BYTES = 8 * 1024 * 1024
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

SETUP_WHITELIST = {"/setup-admin", "/api/setup-admin", "/api/version"}
CHANGE_PW_WHITELIST = {"/change-password", "/api/change-password", "/api/logout"}
PASSWORD_RESET_WHITELIST = {
    "/login",
    "/forgot-password",
    "/reset-password",
    "/api/login",
    "/api/register",
    "/api/forgot-password",
    "/api/reset-password",
    "/api/logout",
    "/api/version",
}

_FORGOT_RATE: dict[str, float] = {}
RESET_CODE_MINUTES = max(5, min(120, int(os.environ.get("RESET_CODE_MINUTES", "30"))))


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
        g.db = connect_db(DB_PATH)
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


def init_db():
    init_database(DB_PATH)


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


def _copy_question_image(source_rel, user_id: int, question_id: int) -> str:
    if not source_rel:
        return ""
    src = os.path.join(UPLOAD_DIR, source_rel)
    if not os.path.isfile(src):
        return ""
    ext = Path(source_rel).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXT:
        return ""
    rel = f"{user_id}/{question_id}{ext}"
    dest = os.path.join(UPLOAD_DIR, rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy2(src, dest)
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


def _root_question_id(db, qid: int) -> int:
    """Follow copy chain to the original (non-fork) question."""
    seen = set()
    current = qid
    while current and current not in seen:
        seen.add(current)
        row = db.execute(
            "SELECT copied_from_id FROM questions WHERE id = ?", (current,)
        ).fetchone()
        if not row or not row["copied_from_id"]:
            return current
        current = row["copied_from_id"]
    return current


def _question_json(row, for_user_id=None):
    d = dict(row)
    d["has_image"] = bool(d.get("image_path"))
    d["image_url"] = f"/api/questions/{d['id']}/image" if d["has_image"] else None
    d.pop("prompt_highlights", None)
    cid = d.get("copied_from_id")
    d["is_fork"] = bool(cid)
    d["fork_count"] = int(d.get("fork_count") or 0)
    d["is_private"] = bool(d.get("is_private"))
    if for_user_id is not None:
        d["is_mine"] = int(d.get("user_id") or 0) == int(for_user_id)
    return d


def _can_view_question(row, viewer_id: int) -> bool:
    if not row:
        return False
    if int(row["user_id"]) == int(viewer_id):
        return True
    if row["copied_from_id"] if "copied_from_id" in row.keys() else None:
        return False
    return not bool(row["is_private"] if "is_private" in row.keys() else 0)


def _question_detail_json(row):
    if not row:
        return None
    d = {
        "id": row["id"],
        "title": row["title"],
        "task_type": row["task_type"] or "task2",
        "prompt": row["prompt"] if "prompt" in row.keys() else "",
    }
    d["has_image"] = bool(row["image_path"] if "image_path" in row.keys() else None)
    d["image_url"] = f"/api/questions/{row['id']}/image" if d["has_image"] else None
    return d


def _writing_detail_json(row):
    out = _writing_json(row)
    if "task_type" in row.keys():
        out["question_task_type"] = row["task_type"]
    if "question_title" in row.keys():
        out["question_title"] = row["question_title"]
    if "username" in row.keys():
        out["username"] = row["username"]
    if "image_path" in row.keys() and row["question_id"]:
        out["question_has_image"] = bool(row["image_path"])
        out["question_image_url"] = (
            f"/api/questions/{row['question_id']}/image" if row["image_path"] else None
        )
    else:
        out["question_has_image"] = False
        out["question_image_url"] = None
    return out


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


def _get_user_openrouter_key(user_id: int) -> str:
    row = get_db().execute(
        "SELECT openrouter_api_key_enc FROM user_api_keys WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if not row:
        return ""
    return decrypt_secret(row["openrouter_api_key_enc"])


def _evaluation_json(row):
    if not row:
        return None
    d = dict(row)
    for field, key in (
        ("criterion_scores_json", "criterion_scores"),
        ("mistakes_json", "mistakes"),
        ("areas_for_improvement_json", "areas_for_improvement"),
    ):
        raw = d.pop(field, None)
        try:
            d[key] = json.loads(raw) if isinstance(raw, str) else (raw or [])
        except json.JSONDecodeError:
            d[key] = [] if key != "criterion_scores" else {}
    return d


def _get_writing_for_eval(wid: int, user_id: int):
    return get_db().execute(
        """SELECT w.*, q.title AS question_title, q.task_type, q.prompt AS question_prompt
           FROM writings w
           LEFT JOIN questions q ON q.id = w.question_id
           WHERE w.id = ? AND w.user_id = ? AND w.finished_at IS NOT NULL""",
        (wid, user_id),
    ).fetchone()


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
    path = request.path
    if path.startswith("/static/"):
        return None

    get_db()

    if not has_admin():
        if path not in SETUP_WHITELIST:
            if path.startswith("/api/"):
                return jsonify({"error": "setup required", "setup": True}), 503
            return redirect(url_for("setup_admin"))
        return None

    if "user_id" in session and session.get("must_change_password"):
        if path not in CHANGE_PW_WHITELIST and path not in PASSWORD_RESET_WHITELIST and not path.startswith("/static/"):
            if path.startswith("/api/"):
                return jsonify({"error": "password change required"}), 403
            return redirect(url_for("change_password"))

    if "user_id" in session:
        if session.get("is_admin"):
            if re.match(r"^/api/writings/\d+$", path) and request.method == "GET":
                return None
            if re.match(r"^/api/questions/\d+/image$", path) and request.method == "GET":
                return None
            student_paths = (
                "/home", "/practice", "/history", "/settings",
                "/api/questions", "/api/writings", "/api/categories", "/api/settings",
            )
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


@app.errorhandler(sqlite3.OperationalError)
def handle_sqlite_operational_error(exc):
    app.logger.warning("SQLite operational error: %s", exc)
    msg = str(exc).lower()
    if "locked" in msg or "busy" in msg:
        body = {"error": "Database busy - please refresh in a moment."}
        if request.path.startswith("/api/"):
            return jsonify(body), 503
        return render_template("error.html", message=body["error"], code=503), 503
    if request.path.startswith("/api/"):
        return jsonify({"error": "Database error"}), 500
    return render_template("error.html", message="Database error.", code=500), 500


@app.errorhandler(500)
def handle_internal_error(exc):
    app.logger.exception("Unhandled server error: %s", exc)
    if request.path.startswith("/api/"):
        return jsonify({"error": "Internal server error"}), 500
    return render_template("error.html", message="Something went wrong. Try refreshing.", code=500), 500


with app.app_context():
    init_db()
    if is_sqlite():
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


@app.route("/login", methods=["GET"], endpoint="login")
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


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _forgot_rate_key() -> str:
    return request.remote_addr or "unknown"


def _check_forgot_rate_limit() -> bool:
    key = _forgot_rate_key()
    now = time.time()
    last = _FORGOT_RATE.get(key, 0)
    if now - last < 60:
        return False
    _FORGOT_RATE[key] = now
    return True


def _generate_reset_code() -> str:
    return f"{secrets.randbelow(1000000):06d}"


def _password_reset_expires_iso() -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=RESET_CODE_MINUTES)).isoformat()


def _forgot_password_ok_message() -> str:
    return (
        "If an account with that email exists, we sent a 6-digit reset code. "
        "Check your inbox (and spam folder)."
    )


@app.route("/forgot-password", methods=["GET"], endpoint="forgot_password")
def forgot_password_page():
    if not has_admin():
        return redirect(url_for("setup_admin"))
    if "user_id" in session:
        return redirect(_login_redirect_url())
    return render_template("forgot_password.html")


@app.route("/reset-password", methods=["GET"], endpoint="reset_password")
def reset_password_page():
    if not has_admin():
        return redirect(url_for("setup_admin"))
    if "user_id" in session:
        return redirect(_login_redirect_url())
    email = (request.args.get("email") or "").strip()
    return render_template("reset_password.html", email=email)


@app.route("/api/forgot-password", methods=["POST"])
def api_forgot_password():
    if not has_admin():
        return jsonify({"error": "setup required"}), 503
    if not smtp_configured():
        return jsonify({
            "error": "Password reset email is not configured. Set SMTP_* in your .env file.",
        }), 503
    if not _check_forgot_rate_limit():
        return jsonify({"error": "Please wait a minute before requesting another code."}), 429

    data = request.get_json(silent=True) or {}
    email = _normalize_email(data.get("email") or "")
    if not email or not EMAIL_RE.match(email):
        return jsonify({"error": "valid email required"}), 400

    db = get_db()
    row = db.execute(
        "SELECT id, username, email FROM users WHERE LOWER(TRIM(COALESCE(email, ''))) = ?",
        (email,),
    ).fetchone()

    if row and row["email"]:
        code = _generate_reset_code()
        expires = _password_reset_expires_iso()
        created = now_iso()
        db.execute(
            "UPDATE password_reset_tokens SET used_at = ? WHERE user_id = ? AND used_at IS NULL",
            (created, row["id"]),
        )
        db.execute(
            """INSERT INTO password_reset_tokens (user_id, code_hash, expires_at, created_at)
               VALUES (?, ?, ?, ?)""",
            (row["id"], generate_password_hash(code), expires, created),
        )
        db.commit()
        try:
            send_mail(
                row["email"].strip(),
                "IELTS Writing Practice — password reset code",
                (
                    f"Hello {row['username']},\n\n"
                    f"Your password reset code is: {code}\n\n"
                    f"This code expires in {RESET_CODE_MINUTES} minutes.\n\n"
                    "If you did not request this, you can ignore this email.\n"
                ),
            )
        except Exception as exc:
            app.logger.exception("Failed to send reset email: %s", exc)
            return jsonify({"error": "Could not send email. Check SMTP settings."}), 500

    return jsonify({"ok": True, "message": _forgot_password_ok_message()})


@app.route("/api/reset-password", methods=["POST"])
def api_reset_password():
    if not has_admin():
        return jsonify({"error": "setup required"}), 503

    data = request.get_json(silent=True) or {}
    email = _normalize_email(data.get("email") or "")
    code = (data.get("code") or "").strip()
    password = data.get("password") or ""
    confirm = data.get("confirm") or ""

    if not email or not EMAIL_RE.match(email):
        return jsonify({"error": "valid email required"}), 400
    if not re.fullmatch(r"\d{6}", code):
        return jsonify({"error": "enter the 6-digit code from your email"}), 400
    if len(password) < 4:
        return jsonify({"error": "password must be at least 4 characters"}), 400
    if password != confirm:
        return jsonify({"error": "passwords do not match"}), 400

    db = get_db()
    user = db.execute(
        "SELECT id FROM users WHERE LOWER(TRIM(COALESCE(email, ''))) = ?",
        (email,),
    ).fetchone()
    if not user:
        return jsonify({"error": "invalid or expired reset code"}), 400

    token = db.execute(
        """SELECT id, code_hash, expires_at FROM password_reset_tokens
           WHERE user_id = ? AND used_at IS NULL
           ORDER BY id DESC LIMIT 1""",
        (user["id"],),
    ).fetchone()
    if not token:
        return jsonify({"error": "invalid or expired reset code"}), 400

    try:
        expires = datetime.fromisoformat(token["expires_at"].replace("Z", "+00:00"))
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
    except ValueError:
        return jsonify({"error": "invalid or expired reset code"}), 400

    if datetime.now(timezone.utc) > expires:
        return jsonify({"error": "reset code has expired — request a new one"}), 400
    if not check_password_hash(token["code_hash"], code):
        return jsonify({"error": "invalid or expired reset code"}), 400

    used = now_iso()
    db.execute(
        "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
        (generate_password_hash(password), user["id"]),
    )
    db.execute(
        "UPDATE password_reset_tokens SET used_at = ? WHERE id = ?",
        (used, token["id"]),
    )
    db.commit()
    return jsonify({"ok": True, "message": "Password updated. You can log in now.", "redirect": url_for("login")})


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


@app.route("/settings")
@student_required
def settings_page():
    return render_template("settings.html", username=session.get("username", ""))


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


@app.route("/api/questions/<int:qid>/private", methods=["POST"])
@student_required
def set_question_private(qid):
    data = request.get_json(silent=True) or {}
    if "private" not in data:
        return jsonify({"error": "private (true/false) required"}), 400
    is_private = 1 if data.get("private") else 0
    db = get_db()
    row = db.execute(
        "SELECT id, user_id FROM questions WHERE id = ?",
        (qid,),
    ).fetchone()
    if not row:
        return jsonify({"error": "question not found"}), 404
    if row["user_id"] != session["user_id"]:
        return jsonify({
            "error": "You can only change privacy on your own questions (not copies in Others).",
        }), 403
    db.execute("UPDATE questions SET is_private = ? WHERE id = ?", (is_private, qid))
    db.commit()
    return jsonify({"ok": True, "is_private": bool(is_private)})


@app.route("/api/questions/<int:qid>/copy", methods=["POST"])
@student_required
def copy_question(qid):
    uid = session["user_id"]
    db = get_db()
    source = db.execute(
        """SELECT q.*, c.name AS category_name
           FROM questions q
           LEFT JOIN categories c ON c.id = q.category_id
           WHERE q.id = ?""",
        (qid,),
    ).fetchone()
    if not source:
        return jsonify({"error": "not found"}), 404
    if not _can_view_question(source, uid):
        return jsonify({"error": "not found"}), 404
    if source["user_id"] == uid:
        return jsonify({"error": "already in My questions"}), 400

    root_id = _root_question_id(db, qid)
    existing = db.execute(
        "SELECT id FROM questions WHERE user_id = ? AND copied_from_id = ?",
        (uid, root_id),
    ).fetchone()
    if existing:
        return jsonify({"error": "already copied to My questions", "id": existing["id"]}), 400

    category_id = None
    if source["category_name"]:
        mine_cat = db.execute(
            "SELECT id FROM categories WHERE user_id = ? AND name = ?",
            (uid, source["category_name"]),
        ).fetchone()
        if mine_cat:
            category_id = mine_cat["id"]

    cur = db.execute(
        """INSERT INTO questions
           (user_id, category_id, title, prompt, task_type, copied_from_id, is_private, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 1, ?)""",
        (
            uid,
            category_id,
            source["title"],
            source["prompt"],
            source["task_type"],
            root_id,
            now_iso(),
        ),
    )
    db.commit()
    new_id = cur.lastrowid

    if source["image_path"]:
        copied = _copy_question_image(source["image_path"], uid, new_id)
        if copied:
            db.execute(
                "UPDATE questions SET image_path = ? WHERE id = ?",
                (copied, new_id),
            )
            db.commit()

    row = db.execute(
        """SELECT q.*, c.name AS category_name, u.username AS owner_username
           FROM questions q
           LEFT JOIN categories c ON c.id = q.category_id
           JOIN users u ON u.id = q.user_id
           WHERE q.id = ?""",
        (new_id,),
    ).fetchone()
    return jsonify(_question_json(row, for_user_id=uid)), 201


# --- Questions API ---


@app.route("/api/questions", methods=["GET"])
@student_required
def list_questions():
    uid = session["user_id"]
    rows = get_db().execute(
        """SELECT q.*, c.name AS category_name, u.username AS owner_username,
                  (SELECT COUNT(*) FROM questions f WHERE f.copied_from_id = q.id) AS fork_count
           FROM questions q
           LEFT JOIN categories c ON c.id = q.category_id
           JOIN users u ON u.id = q.user_id
           WHERE q.user_id = ?
              OR (q.copied_from_id IS NULL AND IFNULL(q.is_private, 0) = 0)
           ORDER BY (c.name IS NULL), c.name, q.id DESC""",
        (uid,),
    ).fetchall()
    return jsonify([_question_json(r, for_user_id=uid) for r in rows])


@app.route("/api/questions", methods=["POST"])
@student_required
def create_question():
    category_id = None
    is_private = 0
    if request.content_type and "multipart/form-data" in request.content_type:
        title = (request.form.get("title") or "Untitled").strip()[:200]
        prompt = (request.form.get("prompt") or "").strip()
        task_type = (request.form.get("task_type") or "task2").strip()[:20]
        image_file = request.files.get("image")
        raw_cat = request.form.get("category_id")
        category_id = int(raw_cat) if raw_cat and raw_cat.isdigit() else None
        raw_private = request.form.get("is_private", "0")
        is_private = 1 if str(raw_private).lower() in ("1", "true", "yes") else 0
    else:
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "Untitled").strip()[:200]
        prompt = (data.get("prompt") or "").strip()
        task_type = (data.get("task_type") or "task2").strip()[:20]
        image_file = None
        category_id = data.get("category_id")
        if data.get("is_private"):
            is_private = 1

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
        """INSERT INTO questions (user_id, category_id, title, prompt, task_type, is_private, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (session["user_id"], category_id, title, prompt, task_type, is_private, now_iso()),
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
        """SELECT q.*, u.username AS owner_username
           FROM questions q
           JOIN users u ON u.id = q.user_id
           WHERE q.id = ?""",
        (qid,),
    ).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    if not _can_view_question(row, session["user_id"]):
        return jsonify({"error": "not found"}), 404
    return jsonify(_question_json(row, for_user_id=session["user_id"]))


@app.route("/api/questions/<int:qid>/image")
@login_required
def question_image(qid):
    if session.get("is_admin"):
        row = get_db().execute(
            "SELECT image_path FROM questions WHERE id = ?", (qid,)
        ).fetchone()
    else:
        row = get_db().execute(
            "SELECT user_id, image_path, is_private FROM questions WHERE id = ?",
            (qid,),
        ).fetchone()
        if not row or not _can_view_question(row, session["user_id"]):
            abort(404)
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
               FROM writings w
               INNER JOIN questions q ON q.id = w.question_id
               WHERE w.user_id = ? AND w.finished_at IS NOT NULL
               GROUP BY q.id ORDER BY last_finished DESC""",
            (session["user_id"],),
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
    db = get_db()
    rows = db.execute(
        """SELECT w.*, q.title AS question_title, q.task_type
           FROM writings w
           JOIN questions q ON q.id = w.question_id
           WHERE w.user_id = ? AND w.question_id = ? AND w.finished_at IS NOT NULL
           ORDER BY w.finished_at DESC""",
        (session["user_id"], qid),
    ).fetchall()
    q = db.execute("SELECT * FROM questions WHERE id = ?", (qid,)).fetchone()
    if not q:
        return jsonify({"error": "not found"}), 404
    return jsonify({
        "question": _question_detail_json(q),
        "attempts": [_writing_json(r) for r in rows],
    })


@app.route("/api/writings/<int:wid>", methods=["GET"])
@login_required
def get_writing(wid):
    if session.get("is_admin"):
        row = get_db().execute(
            """SELECT w.*, q.title AS question_title, q.task_type, q.image_path, u.username
               FROM writings w
               LEFT JOIN questions q ON q.id = w.question_id
               JOIN users u ON u.id = w.user_id
               WHERE w.id = ?""",
            (wid,),
        ).fetchone()
    else:
        row = get_db().execute(
            """SELECT w.*, q.title AS question_title, q.task_type, q.image_path
               FROM writings w
               LEFT JOIN questions q ON q.id = w.question_id
               WHERE w.id = ? AND w.user_id = ?""",
            (wid, session["user_id"]),
        ).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    return jsonify(_writing_detail_json(row))


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


# --- AI settings & evaluation ---


@app.route("/api/settings/ai", methods=["GET"])
@student_required
def get_ai_settings():
    row = get_db().execute(
        "SELECT openrouter_api_key_enc, updated_at FROM user_api_keys WHERE user_id = ?",
        (session["user_id"],),
    ).fetchone()
    if not row:
        return jsonify({"configured": False, "masked_key": "", "updated_at": None})
    plain = decrypt_secret(row["openrouter_api_key_enc"])
    return jsonify({
        "configured": bool(plain),
        "masked_key": mask_api_key(plain),
        "updated_at": row["updated_at"],
    })


@app.route("/api/settings/ai", methods=["PUT"])
@student_required
def save_ai_settings():
    data = request.get_json(silent=True) or {}
    api_key = (data.get("openrouter_api_key") or "").strip()
    if not api_key:
        return jsonify({"error": "openrouter_api_key required"}), 400
    ts = now_iso()
    enc = encrypt_secret(api_key)
    db = get_db()
    existing = db.execute(
        "SELECT user_id FROM user_api_keys WHERE user_id = ?",
        (session["user_id"],),
    ).fetchone()
    if existing:
        db.execute(
            "UPDATE user_api_keys SET openrouter_api_key_enc = ?, updated_at = ? WHERE user_id = ?",
            (enc, ts, session["user_id"]),
        )
    else:
        db.execute(
            "INSERT INTO user_api_keys (user_id, openrouter_api_key_enc, updated_at) VALUES (?, ?, ?)",
            (session["user_id"], enc, ts),
        )
    db.commit()
    return jsonify({
        "ok": True,
        "configured": True,
        "masked_key": mask_api_key(api_key),
        "updated_at": ts,
    })


@app.route("/api/settings/ai", methods=["DELETE"])
@student_required
def delete_ai_settings():
    get_db().execute("DELETE FROM user_api_keys WHERE user_id = ?", (session["user_id"],))
    get_db().commit()
    return jsonify({"ok": True, "configured": False})


@app.route("/api/writings/<int:wid>/evaluation", methods=["GET"])
@login_required
def get_writing_evaluation(wid):
    db = get_db()
    if session.get("is_admin"):
        writing = db.execute("SELECT user_id FROM writings WHERE id = ?", (wid,)).fetchone()
        if not writing:
            return jsonify({"error": "not found"}), 404
        owner_id = writing["user_id"]
    else:
        writing = db.execute(
            "SELECT id FROM writings WHERE id = ? AND user_id = ?",
            (wid, session["user_id"]),
        ).fetchone()
        if not writing:
            return jsonify({"error": "not found"}), 404
        owner_id = session["user_id"]

    row = db.execute(
        "SELECT * FROM writing_evaluations WHERE writing_id = ? AND user_id = ?",
        (wid, owner_id),
    ).fetchone()
    if not row:
        return jsonify(None)
    return jsonify(_evaluation_json(row))


@app.route("/api/writings/<int:wid>/evaluate", methods=["POST"])
@student_required
def evaluate_writing_attempt(wid):
    row = _get_writing_for_eval(wid, session["user_id"])
    if not row:
        return jsonify({"error": "not found or attempt not finished"}), 404

    api_key = _get_user_openrouter_key(session["user_id"])
    if not api_key:
        return jsonify({
            "error": "OpenRouter API key not configured",
            "settings_url": url_for("settings_page"),
        }), 400

    model = DEFAULT_MODEL
    try:
        result = evaluate_writing(
            api_key=api_key,
            task_type=row["task_type"] or "task2",
            question_title=row["question_title"] or "",
            question_prompt=row["question_prompt"] or "",
            essay=row["content"] or "",
            word_count=row["final_words"],
            elapsed_ms=row["elapsed_ms"],
            model=model,
        )
    except Exception as exc:
        app.logger.exception("AI evaluation failed for writing %s", wid)
        return jsonify({"error": f"Evaluation failed: {exc}"}), 502

    payload = evaluation_to_dict(result, model=model)
    ts = now_iso()
    db = get_db()
    existing = db.execute(
        "SELECT id FROM writing_evaluations WHERE writing_id = ?",
        (wid,),
    ).fetchone()
    if existing:
        db.execute(
            """UPDATE writing_evaluations SET
               band_score = ?, criterion_scores_json = ?, overall_feedback = ?,
               mistakes_json = ?, areas_for_improvement_json = ?, rewritten_essay = ?,
               model = ?, updated_at = ?
               WHERE writing_id = ?""",
            (
                payload["band_score"],
                json.dumps(payload["criterion_scores"]),
                payload["overall_feedback"],
                json.dumps(payload["mistakes"]),
                json.dumps(payload["areas_for_improvement"]),
                payload["rewritten_essay"],
                payload["model"],
                ts,
                wid,
            ),
        )
    else:
        db.execute(
            """INSERT INTO writing_evaluations
               (writing_id, user_id, band_score, criterion_scores_json, overall_feedback,
                mistakes_json, areas_for_improvement_json, rewritten_essay, model,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                wid,
                session["user_id"],
                payload["band_score"],
                json.dumps(payload["criterion_scores"]),
                payload["overall_feedback"],
                json.dumps(payload["mistakes"]),
                json.dumps(payload["areas_for_improvement"]),
                payload["rewritten_essay"],
                payload["model"],
                ts,
                ts,
            ),
        )
    db.commit()
    saved = db.execute(
        "SELECT * FROM writing_evaluations WHERE writing_id = ?",
        (wid,),
    ).fetchone()
    return jsonify(_evaluation_json(saved))


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
        qd["fork_count"] = db.execute(
            "SELECT COUNT(*) AS n FROM questions WHERE copied_from_id = ?",
            (q["id"],),
        ).fetchone()["n"]
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
    db = get_db()
    rows = db.execute(
        """SELECT w.*, q.title AS question_title, q.task_type
           FROM writings w
           JOIN questions q ON q.id = w.question_id
           WHERE w.user_id = ? AND w.question_id = ? AND w.finished_at IS NOT NULL
           ORDER BY w.finished_at DESC""",
        (uid, qid),
    ).fetchall()
    q = db.execute("SELECT * FROM questions WHERE id = ?", (qid,)).fetchone()
    if not q:
        return jsonify({"error": "not found"}), 404
    return jsonify({
        "question": _question_detail_json(q),
        "attempts": [_writing_json(r) for r in rows],
    })


@app.route("/api/admin/questions/<int:qid>/forks", methods=["GET"])
@admin_required
def admin_question_forks(qid):
    db = get_db()
    root = db.execute("SELECT id FROM questions WHERE id = ?", (qid,)).fetchone()
    if not root:
        return jsonify({"error": "not found"}), 404
    root_id = _root_question_id(db, qid)
    rows = db.execute(
        """SELECT q.id, q.created_at, q.user_id, u.username
           FROM questions q
           JOIN users u ON u.id = q.user_id
           WHERE q.copied_from_id = ?
           ORDER BY q.created_at DESC""",
        (root_id,),
    ).fetchall()
    original = db.execute(
        """SELECT q.id, q.title, u.username AS owner_username
           FROM questions q
           JOIN users u ON u.id = q.user_id
           WHERE q.id = ?""",
        (root_id,),
    ).fetchone()
    return jsonify({
        "original": dict(original) if original else None,
        "forks": [dict(r) for r in rows],
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
