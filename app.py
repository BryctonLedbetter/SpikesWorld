"""
============================================================
  SPIKE'S WORLD — Flask backend with admin dashboard
  Built by Uncle Stephen. 🦎

  WHAT THIS DOES
  - Serves the homepage (templates/index.html)
  - Stores site content in a small SQLite database (spike.db)
  - Gives Brycton a password-protected /admin area to:
      * post announcements
      * update the tank condition (temps + humidity)
      * update Spike's health status
      * upload / delete photos of Spike
  - Exposes /api/content so the homepage can SHOW that content
    to everyone who visits (not just the person who typed it).

  HOW TO CHANGE THE ADMIN PASSWORD
  - Edit ADMIN_PASSWORD below. That's the only login Brycton needs.
============================================================
"""

import os
import sqlite3
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, jsonify, flash, abort
)
from werkzeug.utils import secure_filename

# ---------------------------------------------------------
#  CONFIG  — change these if you want
# ---------------------------------------------------------
ADMIN_PASSWORD = "spike123"          # <-- Brycton's admin password (change me!)
SECRET_KEY     = "change-this-to-any-random-string-you-like"

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
DB_PATH       = os.path.join(BASE_DIR, "spike.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_EXT   = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_MB        = 12                    # max upload size in megabytes

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = MAX_MB * 1024 * 1024
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ---------------------------------------------------------
#  DATABASE  — auto-creates spike.db on first run
# ---------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS announcements(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        body  TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS tank(
        id INTEGER PRIMARY KEY CHECK (id = 1),
        hot TEXT, cool TEXT, humidity TEXT, updated_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS health(
        id INTEGER PRIMARY KEY CHECK (id = 1),
        status TEXT, notes TEXT, updated_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS photos(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        caption  TEXT,
        uploaded_at TEXT NOT NULL
    )""")
    # seed the single-row tables with friendly defaults if empty
    if not c.execute("SELECT 1 FROM tank WHERE id=1").fetchone():
        c.execute("INSERT INTO tank(id,hot,cool,humidity,updated_at) VALUES (1,?,?,?,?)",
                  ("95°F", "80°F", "35%", _now()))
    if not c.execute("SELECT 1 FROM health WHERE id=1").fetchone():
        c.execute("INSERT INTO health(id,status,notes,updated_at) VALUES (1,?,?,?)",
                  ("Perfect", "Spike is happy, eating well, and active!", _now()))
    conn.commit()
    conn.close()

def _now():
    return datetime.now().strftime("%b %d, %Y %I:%M %p")


# ---------------------------------------------------------
#  AUTH  — simple single-password login
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
    """The homepage fetches this to display live content to all visitors."""
    conn = get_db()
    anns = conn.execute(
        "SELECT id,title,body,created_at FROM announcements ORDER BY id DESC"
    ).fetchall()
    tank   = conn.execute("SELECT hot,cool,humidity,updated_at FROM tank WHERE id=1").fetchone()
    health = conn.execute("SELECT status,notes,updated_at FROM health WHERE id=1").fetchone()
    photos = conn.execute(
        "SELECT id,filename,caption FROM photos ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return jsonify({
        "announcements": [dict(a) for a in anns],
        "tank":   dict(tank)   if tank   else {},
        "health": dict(health) if health else {},
        "photos": [
            {"id": p["id"], "caption": p["caption"] or "",
             "url": url_for("static", filename="uploads/" + p["filename"])}
            for p in photos
        ],
    })


# ---------------------------------------------------------
#  ADMIN ROUTES
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
    conn.close()
    return render_template("admin_panel.html",
                           announcements=anns, tank=tank, health=health, photos=photos)

# --- announcements ---
@app.route("/admin/announcement/add", methods=["POST"])
@login_required
def announcement_add():
    title = (request.form.get("title") or "").strip()
    body  = (request.form.get("body")  or "").strip()
    if title and body:
        conn = get_db()
        conn.execute("INSERT INTO announcements(title,body,created_at) VALUES (?,?,?)",
                     (title, body, _now()))
        conn.commit(); conn.close()
        flash("Announcement posted!", "ok")
    else:
        flash("Please fill in both a title and a message.", "error")
    return redirect(url_for("admin_panel"))

@app.route("/admin/announcement/delete/<int:aid>", methods=["POST"])
@login_required
def announcement_delete(aid):
    conn = get_db()
    conn.execute("DELETE FROM announcements WHERE id=?", (aid,))
    conn.commit(); conn.close()
    flash("Announcement deleted.", "ok")
    return redirect(url_for("admin_panel"))

# --- tank ---
@app.route("/admin/tank", methods=["POST"])
@login_required
def tank_update():
    hot      = (request.form.get("hot")      or "").strip()
    cool     = (request.form.get("cool")     or "").strip()
    humidity = (request.form.get("humidity") or "").strip()
    conn = get_db()
    conn.execute("UPDATE tank SET hot=?,cool=?,humidity=?,updated_at=? WHERE id=1",
                 (hot, cool, humidity, _now()))
    conn.commit(); conn.close()
    flash("Tank condition updated!", "ok")
    return redirect(url_for("admin_panel"))

# --- health ---
@app.route("/admin/health", methods=["POST"])
@login_required
def health_update():
    status = (request.form.get("status") or "").strip()
    notes  = (request.form.get("notes")  or "").strip()
    conn = get_db()
    conn.execute("UPDATE health SET status=?,notes=?,updated_at=? WHERE id=1",
                 (status, notes, _now()))
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
        flash("Please choose a photo to upload.", "error")
        return redirect(url_for("admin_panel"))
    if not _allowed(file.filename):
        flash("That file type isn't allowed. Use jpg, png, gif, or webp.", "error")
        return redirect(url_for("admin_panel"))
    # build a safe, unique filename
    safe = secure_filename(file.filename)
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    fname = f"{stamp}_{safe}"
    file.save(os.path.join(UPLOAD_FOLDER, fname))
    conn = get_db()
    conn.execute("INSERT INTO photos(filename,caption,uploaded_at) VALUES (?,?,?)",
                 (fname, caption, _now()))
    conn.commit(); conn.close()
    flash("Photo uploaded!", "ok")
    return redirect(url_for("admin_panel"))

@app.route("/admin/photo/delete/<int:pid>", methods=["POST"])
@login_required
def photo_delete(pid):
    conn = get_db()
    row = conn.execute("SELECT filename FROM photos WHERE id=?", (pid,)).fetchone()
    if row:
        try:
            os.remove(os.path.join(UPLOAD_FOLDER, row["filename"]))
        except OSError:
            pass
        conn.execute("DELETE FROM photos WHERE id=?", (pid,))
        conn.commit()
    conn.close()
    flash("Photo deleted.", "ok")
    return redirect(url_for("admin_panel"))


# ---------------------------------------------------------
init_db()   # make sure the database exists before serving

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
