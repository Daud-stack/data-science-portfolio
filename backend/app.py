import json
import os
import sqlite3
import smtplib
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse, FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel, EmailStr


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "backend" / "data"
DB_PATH = DATA_DIR / "app.db"
FRONTEND_DIR = BASE_DIR

DATA_DIR.mkdir(parents=True, exist_ok=True)

APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("APP_PORT", "9000"))
SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me")

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or 587)
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "")
SMTP_TO_EMAIL = os.getenv("SMTP_TO_EMAIL", "")

app = FastAPI(title="Portfolio Backend")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
templates = Jinja2Templates(directory=str(BASE_DIR / "backend" / "templates"))


class ContactIn(BaseModel):
  name: str
  email: EmailStr
  message: str


class TrackIn(BaseModel):
  event_name: str
  path: str
  meta: dict = {}


def get_db():
  conn = sqlite3.connect(DB_PATH)
  conn.row_factory = sqlite3.Row
  return conn


def init_db():
  conn = get_db()
  cur = conn.cursor()
  cur.execute(
    """
    CREATE TABLE IF NOT EXISTS projects (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT NOT NULL,
      description TEXT NOT NULL,
      image TEXT,
      tags TEXT,
      case_study_url TEXT,
      source_url TEXT,
      created_at TEXT NOT NULL
    )
    """
  )
  cur.execute(
    """
    CREATE TABLE IF NOT EXISTS posts (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT NOT NULL,
      excerpt TEXT NOT NULL,
      url TEXT,
      tags TEXT,
      published_at TEXT,
      created_at TEXT NOT NULL
    )
    """
  )
  cur.execute(
    """
    CREATE TABLE IF NOT EXISTS contacts (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      email TEXT NOT NULL,
      message TEXT NOT NULL,
      created_at TEXT NOT NULL
    )
    """
  )
  cur.execute(
    """
    CREATE TABLE IF NOT EXISTS analytics (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      event_name TEXT NOT NULL,
      path TEXT NOT NULL,
      meta TEXT,
      ip TEXT,
      user_agent TEXT,
      created_at TEXT NOT NULL
    )
    """
  )
  conn.commit()
  conn.close()


def seed_data():
  conn = get_db()
  cur = conn.cursor()
  cur.execute("SELECT COUNT(*) FROM projects")
  projects_count = cur.fetchone()[0]
  if projects_count == 0:
    sample_projects = [
      (
        "Customer Churn Intelligence",
        "Built a churn prediction pipeline and executive dashboard to prioritize retention actions.",
        "Images/Projects/1.jpg",
        json.dumps(["Python", "XGBoost", "Power BI"]),
        "",
        "",
        datetime.utcnow().isoformat(),
      ),
      (
        "Supply Chain KPI Console",
        "Designed a KPI suite to track OTIF, lead times, and cost variance for operations leaders.",
        "Images/Projects/2.jpg",
        json.dumps(["SQL", "Tableau", "ETL"]),
        "",
        "",
        datetime.utcnow().isoformat(),
      ),
      (
        "Quality Audit Automation",
        "Automated audit scheduling and corrective action tracking for ISO 9001 readiness.",
        "Images/Projects/3.jpg",
        json.dumps(["Excel", "Power Automate", "QA"]),
        "",
        "",
        datetime.utcnow().isoformat(),
      ),
    ]
    cur.executemany(
      """
      INSERT INTO projects (title, description, image, tags, case_study_url, source_url, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?)
      """,
      sample_projects,
    )
  cur.execute("SELECT COUNT(*) FROM posts")
  posts_count = cur.fetchone()[0]
  if posts_count == 0:
    sample_posts = [
      (
        "From Raw Data to Reliable KPIs",
        "How I structure KPI definitions and build dashboards that teams actually use.",
        "",
        json.dumps(["KPIs", "Analytics", "Ops"]),
        "2025-01-10",
        datetime.utcnow().isoformat(),
      ),
      (
        "Ethical Data Practice in Early-Stage Projects",
        "A checklist for building responsible analytics from day one.",
        "",
        json.dumps(["Ethics", "Governance"]),
        "2025-02-05",
        datetime.utcnow().isoformat(),
      ),
    ]
    cur.executemany(
      """
      INSERT INTO posts (title, excerpt, url, tags, published_at, created_at)
      VALUES (?, ?, ?, ?, ?, ?)
      """,
      sample_posts,
    )
  conn.commit()
  conn.close()


def row_to_project(row):
  return {
    "id": row["id"],
    "title": row["title"],
    "description": row["description"],
    "image": row["image"],
    "tags": json.loads(row["tags"] or "[]"),
    "case_study_url": row["case_study_url"],
    "source_url": row["source_url"],
  }


def row_to_post(row):
  return {
    "id": row["id"],
    "title": row["title"],
    "excerpt": row["excerpt"],
    "url": row["url"],
    "tags": json.loads(row["tags"] or "[]"),
    "published_at": row["published_at"],
  }


def send_email(subject: str, body: str):
  if not SMTP_HOST or not SMTP_FROM_EMAIL or not SMTP_TO_EMAIL:
    return False

  msg = EmailMessage()
  msg["Subject"] = subject
  msg["From"] = SMTP_FROM_EMAIL
  msg["To"] = SMTP_TO_EMAIL
  msg.set_content(body)

  with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
    server.starttls()
    if SMTP_USERNAME and SMTP_PASSWORD:
      server.login(SMTP_USERNAME, SMTP_PASSWORD)
    server.send_message(msg)
  return True


def is_admin(request: Request) -> bool:
  return bool(request.session.get("admin"))


def require_admin(request: Request):
  if not is_admin(request):
    raise HTTPException(status_code=403, detail="Unauthorized")


@app.on_event("startup")
def on_startup():
  init_db()
  seed_data()


@app.get("/api/projects")
def api_projects():
  conn = get_db()
  cur = conn.cursor()
  cur.execute("SELECT * FROM projects ORDER BY id DESC")
  rows = cur.fetchall()
  conn.close()
  return [row_to_project(row) for row in rows]


@app.get("/api/posts")
def api_posts():
  conn = get_db()
  cur = conn.cursor()
  cur.execute("SELECT * FROM posts ORDER BY id DESC")
  rows = cur.fetchall()
  conn.close()
  return [row_to_post(row) for row in rows]


@app.post("/api/contact")
def api_contact(payload: ContactIn, request: Request):
  conn = get_db()
  cur = conn.cursor()
  cur.execute(
    """
    INSERT INTO contacts (name, email, message, created_at)
    VALUES (?, ?, ?, ?)
    """,
    (payload.name, payload.email, payload.message, datetime.utcnow().isoformat()),
  )
  conn.commit()
  conn.close()

  email_sent = False
  try:
    email_sent = send_email(
      subject=f"New Portfolio Message from {payload.name}",
      body=f"Name: {payload.name}\nEmail: {payload.email}\n\n{payload.message}",
    )
  except Exception:
    email_sent = False

  if email_sent:
    return JSONResponse({"message": "Message sent successfully."})
  return JSONResponse({"message": "Message saved. Email delivery not configured yet."})


@app.post("/api/track")
def api_track(payload: TrackIn, request: Request):
  conn = get_db()
  cur = conn.cursor()
  cur.execute(
    """
    INSERT INTO analytics (event_name, path, meta, ip, user_agent, created_at)
    VALUES (?, ?, ?, ?, ?, ?)
    """,
    (
      payload.event_name,
      payload.path,
      json.dumps(payload.meta),
      request.client.host if request.client else "",
      request.headers.get("user-agent", ""),
      datetime.utcnow().isoformat(),
    ),
  )
  conn.commit()
  conn.close()
  return JSONResponse({"status": "ok"})


@app.get("/admin/login", response_class=HTMLResponse)
def admin_login(request: Request):
  return templates.TemplateResponse("admin_login.html", {"request": request})


@app.post("/admin/login")
def admin_login_post(request: Request, password: str = Form(...)):
  if password != ADMIN_PASSWORD:
    return templates.TemplateResponse(
      "admin_login.html",
      {"request": request, "error": "Invalid password."},
      status_code=401,
    )
  request.session["admin"] = True
  return RedirectResponse("/admin", status_code=303)


@app.post("/admin/logout")
def admin_logout(request: Request):
  request.session.clear()
  return RedirectResponse("/admin/login", status_code=303)


@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
  require_admin(request)
  conn = get_db()
  cur = conn.cursor()
  cur.execute("SELECT COUNT(*) FROM projects")
  projects_count = cur.fetchone()[0]
  cur.execute("SELECT COUNT(*) FROM posts")
  posts_count = cur.fetchone()[0]
  cur.execute("SELECT COUNT(*) FROM contacts")
  contacts_count = cur.fetchone()[0]
  cur.execute("SELECT COUNT(*) FROM analytics")
  analytics_count = cur.fetchone()[0]
  conn.close()
  return templates.TemplateResponse(
    "admin_dashboard.html",
    {
      "request": request,
      "projects_count": projects_count,
      "posts_count": posts_count,
      "contacts_count": contacts_count,
      "analytics_count": analytics_count,
    },
  )


@app.get("/admin/projects", response_class=HTMLResponse)
def admin_projects(request: Request):
  require_admin(request)
  conn = get_db()
  cur = conn.cursor()
  cur.execute("SELECT * FROM projects ORDER BY id DESC")
  rows = cur.fetchall()
  conn.close()
  projects = [row_to_project(row) for row in rows]
  return templates.TemplateResponse(
    "admin_projects.html", {"request": request, "projects": projects}
  )


@app.post("/admin/projects/create")
def admin_projects_create(
  request: Request,
  title: str = Form(...),
  description: str = Form(...),
  image: str = Form(""),
  tags: str = Form(""),
  case_study_url: str = Form(""),
  source_url: str = Form(""),
):
  require_admin(request)
  conn = get_db()
  cur = conn.cursor()
  tag_list = [t.strip() for t in tags.split(",") if t.strip()]
  cur.execute(
    """
    INSERT INTO projects (title, description, image, tags, case_study_url, source_url, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
    (
      title,
      description,
      image,
      json.dumps(tag_list),
      case_study_url,
      source_url,
      datetime.utcnow().isoformat(),
    ),
  )
  conn.commit()
  conn.close()
  return RedirectResponse("/admin/projects", status_code=303)


@app.post("/admin/projects/update")
def admin_projects_update(
  request: Request,
  project_id: int = Form(...),
  title: str = Form(...),
  description: str = Form(...),
  image: str = Form(""),
  tags: str = Form(""),
  case_study_url: str = Form(""),
  source_url: str = Form(""),
):
  require_admin(request)
  conn = get_db()
  cur = conn.cursor()
  tag_list = [t.strip() for t in tags.split(",") if t.strip()]
  cur.execute(
    """
    UPDATE projects
    SET title = ?, description = ?, image = ?, tags = ?, case_study_url = ?, source_url = ?
    WHERE id = ?
    """,
    (
      title,
      description,
      image,
      json.dumps(tag_list),
      case_study_url,
      source_url,
      project_id,
    ),
  )
  conn.commit()
  conn.close()
  return RedirectResponse("/admin/projects", status_code=303)


@app.post("/admin/projects/delete")
def admin_projects_delete(request: Request, project_id: int = Form(...)):
  require_admin(request)
  conn = get_db()
  cur = conn.cursor()
  cur.execute("DELETE FROM projects WHERE id = ?", (project_id,))
  conn.commit()
  conn.close()
  return RedirectResponse("/admin/projects", status_code=303)


@app.get("/admin/posts", response_class=HTMLResponse)
def admin_posts(request: Request):
  require_admin(request)
  conn = get_db()
  cur = conn.cursor()
  cur.execute("SELECT * FROM posts ORDER BY id DESC")
  rows = cur.fetchall()
  conn.close()
  posts = [row_to_post(row) for row in rows]
  return templates.TemplateResponse("admin_posts.html", {"request": request, "posts": posts})


@app.post("/admin/posts/create")
def admin_posts_create(
  request: Request,
  title: str = Form(...),
  excerpt: str = Form(...),
  url: str = Form(""),
  tags: str = Form(""),
  published_at: str = Form(""),
):
  require_admin(request)
  conn = get_db()
  cur = conn.cursor()
  tag_list = [t.strip() for t in tags.split(",") if t.strip()]
  cur.execute(
    """
    INSERT INTO posts (title, excerpt, url, tags, published_at, created_at)
    VALUES (?, ?, ?, ?, ?, ?)
    """,
    (
      title,
      excerpt,
      url,
      json.dumps(tag_list),
      published_at,
      datetime.utcnow().isoformat(),
    ),
  )
  conn.commit()
  conn.close()
  return RedirectResponse("/admin/posts", status_code=303)


@app.post("/admin/posts/update")
def admin_posts_update(
  request: Request,
  post_id: int = Form(...),
  title: str = Form(...),
  excerpt: str = Form(...),
  url: str = Form(""),
  tags: str = Form(""),
  published_at: str = Form(""),
):
  require_admin(request)
  conn = get_db()
  cur = conn.cursor()
  tag_list = [t.strip() for t in tags.split(",") if t.strip()]
  cur.execute(
    """
    UPDATE posts
    SET title = ?, excerpt = ?, url = ?, tags = ?, published_at = ?
    WHERE id = ?
    """,
    (
      title,
      excerpt,
      url,
      json.dumps(tag_list),
      published_at,
      post_id,
    ),
  )
  conn.commit()
  conn.close()
  return RedirectResponse("/admin/posts", status_code=303)


@app.post("/admin/posts/delete")
def admin_posts_delete(request: Request, post_id: int = Form(...)):
  require_admin(request)
  conn = get_db()
  cur = conn.cursor()
  cur.execute("DELETE FROM posts WHERE id = ?", (post_id,))
  conn.commit()
  conn.close()
  return RedirectResponse("/admin/posts", status_code=303)


@app.get("/admin/analytics", response_class=HTMLResponse)
def admin_analytics(request: Request):
  require_admin(request)
  conn = get_db()
  cur = conn.cursor()
  cur.execute("SELECT * FROM analytics ORDER BY id DESC LIMIT 200")
  rows = cur.fetchall()
  conn.close()
  events = [
    {
      "event_name": row["event_name"],
      "path": row["path"],
      "meta": row["meta"],
      "ip": row["ip"],
      "user_agent": row["user_agent"],
      "created_at": row["created_at"],
    }
    for row in rows
  ]
  return templates.TemplateResponse("admin_analytics.html", {"request": request, "events": events})


@app.get("/", response_class=HTMLResponse)
def serve_index():
  index_path = FRONTEND_DIR / "index.html"
  return FileResponse(index_path)


@app.get("/{path:path}")
def serve_static(path: str):
  if path.startswith("api") or path.startswith("admin"):
    raise HTTPException(status_code=404)
  file_path = FRONTEND_DIR / path
  if file_path.exists() and file_path.is_file():
    return FileResponse(file_path)
  index_path = FRONTEND_DIR / "index.html"
  if index_path.exists():
    return FileResponse(index_path)
  raise HTTPException(status_code=404)


if __name__ == "__main__":
  import uvicorn

  reload_enabled = os.getenv("APP_RELOAD", "0") == "1"
  uvicorn.run("app:app", host=APP_HOST, port=APP_PORT, reload=reload_enabled)
