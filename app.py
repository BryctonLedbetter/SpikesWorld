"""
============================================================
  SPIKE'S WORLD — Flask backend with admin dashboard
  Built by Uncle Stephen. 🦎

  Manages: announcements, tank condition, health, photos,
  countdowns, caretakers, and Spike's birthday.
  Public homepage reads everything from /api/content.

  CHANGE THE ADMIN PASSWORD below (ADMIN_PASSWORD).
============================================================
"""

import os
import sqlite3
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, jsonify, flash
)
from werkzeug.utils import secure_filename

# ---------------------------------------------------------
#  CONFIG
# ---------------------------------------------------------
ADMIN_PASSWORD = "spike123"          # <-- Brycton's admin password (change me!)
SECRET_KEY     = "change-this-to-any-random-string-you-like"

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
DB_PATH       = os.path.join(BASE_DIR, "spike.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_EXT   = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_MB        = 12

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = MAX_MB * 1024 * 1024
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ---------------------------------------------------------
#  DATABASE
# ---------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _now():
    return datetime.now().strftime("%b %d, %Y %I:%M %p")

def init_db():
    conn = get_db(); c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS announcements(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS tank(
        id INTEGER PRIMARY KEY CHECK (id = 1),
        hot TEXT, cool TEXT, humidity TEXT, updated_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS health(
        id INTEGER PRIMARY KEY CHECK (id = 1),
        status TEXT, notes TEXT, updated_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS photos(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL, caption TEXT, uploaded_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS countdowns(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL, target_date TEXT NOT NULL, created_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS caretakers(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, role TEXT, created_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS settings(
        key TEXT PRIMARY KEY, value TEXT)""")
    # seed single-row tables
    if not c.execute("SELECT 1 FROM tank WHERE id=1").fetchone():
        c.execute("INSERT INTO tank(id,hot,cool,humidity,updated_at) VALUES (1,?,?,?,?)",
                  ("95°F", "80°F", "35%", _now()))
    if not c.execute("SELECT 1 FROM health WHERE id=1").fetchone():
        c.execute("INSERT INTO health(id,status,notes,updated_at) VALUES (1,?,?,?)",
                  ("Perfect", "Spike is happy, eating well, and active!", _now()))
    conn.commit(); conn.close()

def get_setting(key, default=""):
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default

def set_setting(key, value):
    conn = get_db()
    conn.execute("INSERT INTO settings(key,value) VALUES (?,?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    conn.commit(); conn.close()


# ---------------------------------------------------------
#  AUTH
# ---------------------------------------------------------
def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **k):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return fn(*a, **k)
    return wrapper


# ---------------------------------------------------------
#  PUBLIC ROUTES
# ---------------------------------------------------------
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/content")
def api_content():
    conn = get_db()
    anns = conn.execute("SELECT id,title,body,created_at FROM announcements ORDER BY id DESC").fetchall()
    tank   = conn.execute("SELECT hot,cool,humidity,updated_at FROM tank WHERE id=1").fetchone()
    health = conn.execute("SELECT status,notes,updated_at FROM health WHERE id=1").fetchone()
    photos = conn.execute("SELECT id,filename,caption FROM photos ORDER BY id DESC").fetchall()
    counts = conn.execute("SELECT id,title,target_date FROM countdowns ORDER BY target_date ASC").fetchall()
    carers = conn.execute("SELECT id,name,role FROM caretakers ORDER BY id ASC").fetchall()
    conn.close()
    return jsonify({
        "announcements": [dict(a) for a in anns],
        "tank":   dict(tank)   if tank   else {},
        "health": dict(health) if health else {},
        "photos": [{"id": p["id"], "caption": p["caption"] or "",
                    "url": url_for("static", filename="uploads/" + p["filename"])} for p in photos],
        "countdowns": [dict(x) for x in counts],
        "caretakers": [dict(x) for x in carers],
        "birthday": get_setting("birthday", ""),
    })


# ---------------------------------------------------------
#  ADMIN
# ---------------------------------------------------------
@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin_panel"))
        flash("Wrong password. Try again!", "error")
    if session.get("admin"):
        return redirect(url_for("admin_panel"))
    return render_template("admin.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("home"))

@app.route("/admin/panel")
@login_required
def admin_panel():
    conn = get_db()
    anns   = conn.execute("SELECT id,title,body,created_at FROM announcements ORDER BY id DESC").fetchall()
    tank   = conn.execute("SELECT hot,cool,humidity,updated_at FROM tank WHERE id=1").fetchone()
    health = conn.execute("SELECT status,notes,updated_at FROM health WHERE id=1").fetchone()
    photos = conn.execute("SELECT id,filename,caption FROM photos ORDER BY id DESC").fetchall()
    counts = conn.execute("SELECT id,title,target_date FROM countdowns ORDER BY target_date ASC").fetchall()
    carers = conn.execute("SELECT id,name,role FROM caretakers ORDER BY id ASC").fetchall()
    conn.close()
    return render_template("admin_panel.html",
                           announcements=anns, tank=tank, health=health, photos=photos,
                           countdowns=counts, caretakers=carers, birthday=get_setting("birthday", ""))

# --- announcements ---
@app.route("/admin/announcement/add", methods=["POST"])
@login_required
def announcement_add():
    title = (request.form.get("title") or "").strip()
    body  = (request.form.get("body")  or "").strip()
    if title and body:
        conn = get_db()
        conn.execute("INSERT INTO announcements(title,body,created_at) VALUES (?,?,?)", (title, body, _now()))
        conn.commit(); conn.close()
        flash("Announcement posted!", "ok")
    else:
        flash("Please fill in both a title and a message.", "error")
    return redirect(url_for("admin_panel"))

@app.route("/admin/announcement/delete/<int:aid>", methods=["POST"])
@login_required
def announcement_delete(aid):
    conn = get_db(); conn.execute("DELETE FROM announcements WHERE id=?", (aid,)); conn.commit(); conn.close()
    flash("Announcement deleted.", "ok")
    return redirect(url_for("admin_panel"))

# --- tank ---
@app.route("/admin/tank", methods=["POST"])
@login_required
def tank_update():
    conn = get_db()
    conn.execute("UPDATE tank SET hot=?,cool=?,humidity=?,updated_at=? WHERE id=1",
                 ((request.form.get("hot") or "").strip(),
                  (request.form.get("cool") or "").strip(),
                  (request.form.get("humidity") or "").strip(), _now()))
    conn.commit(); conn.close()
    flash("Tank condition updated!", "ok")
    return redirect(url_for("admin_panel"))

# --- health ---
@app.route("/admin/health", methods=["POST"])
@login_required
def health_update():
    conn = get_db()
    conn.execute("UPDATE health SET status=?,notes=?,updated_at=? WHERE id=1",
                 ((request.form.get("status") or "").strip(),
                  (request.form.get("notes") or "").strip(), _now()))
    conn.commit(); conn.close()
    flash("Health status updated!", "ok")
    return redirect(url_for("admin_panel"))

# --- photos ---
def _allowed(fname):
    return "." in fname and fname.rsplit(".", 1)[1].lower() in ALLOWED_EXT

@app.route("/admin/photo/upload", methods=["POST"])
@login_required
def photo_upload():
    file = request.files.get("photo")
    caption = (request.form.get("caption") or "").strip()
    if not file or file.filename == "":
        flash("Please choose a photo to upload.", "error"); return redirect(url_for("admin_panel"))
    if not _allowed(file.filename):
        flash("That file type isn't allowed. Use jpg, png, gif, or webp.", "error"); return redirect(url_for("admin_panel"))
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    fname = f"{stamp}_{secure_filename(file.filename)}"
    file.save(os.path.join(UPLOAD_FOLDER, fname))
    conn = get_db()
    conn.execute("INSERT INTO photos(filename,caption,uploaded_at) VALUES (?,?,?)", (fname, caption, _now()))
    conn.commit(); conn.close()
    flash("Photo uploaded!", "ok")
    return redirect(url_for("admin_panel"))

@app.route("/admin/photo/delete/<int:pid>", methods=["POST"])
@login_required
def photo_delete(pid):
    conn = get_db()
    row = conn.execute("SELECT filename FROM photos WHERE id=?", (pid,)).fetchone()
    if row:
        try: os.remove(os.path.join(UPLOAD_FOLDER, row["filename"]))
        except OSError: pass
        conn.execute("DELETE FROM photos WHERE id=?", (pid,)); conn.commit()
    conn.close()
    flash("Photo deleted.", "ok")
    return redirect(url_for("admin_panel"))

# --- countdowns ---
@app.route("/admin/countdown/add", methods=["POST"])
@login_required
def countdown_add():
    title = (request.form.get("title") or "").strip()
    date  = (request.form.get("target_date") or "").strip()   # expected: YYYY-MM-DD
    if title and date:
        conn = get_db()
        conn.execute("INSERT INTO countdowns(title,target_date,created_at) VALUES (?,?,?)", (title, date, _now()))
        conn.commit(); conn.close()
        flash("Countdown added!", "ok")
    else:
        flash("Please enter both a title and a date.", "error")
    return redirect(url_for("admin_panel"))

@app.route("/admin/countdown/delete/<int:cid>", methods=["POST"])
@login_required
def countdown_delete(cid):
    conn = get_db(); conn.execute("DELETE FROM countdowns WHERE id=?", (cid,)); conn.commit(); conn.close()
    flash("Countdown deleted.", "ok")
    return redirect(url_for("admin_panel"))

# --- caretakers ---
@app.route("/admin/caretaker/add", methods=["POST"])
@login_required
def caretaker_add():
    name = (request.form.get("name") or "").strip()
    role = (request.form.get("role") or "").strip()
    if name:
        conn = get_db()
        conn.execute("INSERT INTO caretakers(name,role,created_at) VALUES (?,?,?)", (name, role, _now()))
        conn.commit(); conn.close()
        flash("Caretaker added!", "ok")
    else:
        flash("Please enter a name.", "error")
    return redirect(url_for("admin_panel"))

@app.route("/admin/caretaker/delete/<int:cid>", methods=["POST"])
@login_required
def caretaker_delete(cid):
    conn = get_db(); conn.execute("DELETE FROM caretakers WHERE id=?", (cid,)); conn.commit(); conn.close()
    flash("Caretaker removed.", "ok")
    return redirect(url_for("admin_panel"))

# --- birthday ---
@app.route("/admin/birthday", methods=["POST"])
@login_required
def birthday_update():
    date = (request.form.get("birthday") or "").strip()   # expected: YYYY-MM-DD
    set_setting("birthday", date)
    flash("Spike's birthday saved!", "ok")
    return redirect(url_for("admin_panel"))


# ---------------------------------------------------------
init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
