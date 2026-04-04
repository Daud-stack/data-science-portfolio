import json
import os
import sqlite3
import smtplib
from contextlib import contextmanager, asynccontextmanager
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from fastapi import FastAPI, Request, Form, HTTPException
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

@asynccontextmanager
async def lifespan(app: FastAPI):
  init_db()
  seed_data()
  yield


app = FastAPI(title="Portfolio Backend", lifespan=lifespan)
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


@contextmanager
def get_db():
  conn = sqlite3.connect(DB_PATH)
  conn.row_factory = sqlite3.Row
  try:
    yield conn
  finally:
    conn.close()


def init_db():
  with get_db() as conn:
    cur = conn.cursor()
    cur.execute(
      """
      CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        image TEXT,
        icon_class TEXT,
        tags TEXT,
        case_study_url TEXT,
        source_url TEXT,
        created_at TEXT NOT NULL
      )
      """
    )
    try:
      cur.execute("ALTER TABLE projects ADD COLUMN icon_class TEXT")
    except sqlite3.OperationalError:
      pass
    cur.execute(
      """
      CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        excerpt TEXT NOT NULL,
        slug TEXT,
        content TEXT,
        url TEXT,
        tags TEXT,
        published_at TEXT,
        created_at TEXT NOT NULL
      )
      """
    )
    try:
      cur.execute("ALTER TABLE posts ADD COLUMN slug TEXT")
    except sqlite3.OperationalError:
      pass
    try:
      cur.execute("ALTER TABLE posts ADD COLUMN content TEXT")
    except sqlite3.OperationalError:
      pass
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


def seed_data():
  with get_db() as conn:
    cur = conn.cursor()
    sample_projects = [
      (
        "Personal Productivity App",
        "A focused task and habit tracker designed to help users plan, execute, and reflect on daily goals.",
        "Images/Projects/personal-productivity.svg",
        "fa-solid fa-calendar-check",
        json.dumps(["Productivity", "UX", "Planning"]),
        "https://personal-productivity-app-3ml0.onrender.com",
        "https://github.com/Daud-stack/Personal-productivity-app.git",
        datetime.utcnow().isoformat(),
      ),
      (
        "MDH MIS Platform",
        "A management information system concept to centralize reporting, tracking, and operational visibility.",
        "Images/Projects/mdh-mis.svg",
        "fa-solid fa-gauge-high",
        json.dumps(["MIS", "Reporting", "Operations"]),
        "https://mdh-mis-platform.vercel.app/",
        "https://github.com/Daud-stack/mdh-mis-platform.git",
        datetime.utcnow().isoformat(),
      ),
      (
        "MedMarket Starter",
        "A starter template for a healthcare marketplace experience with scalable data foundations.",
        "Images/Projects/medmarket.svg",
        "fa-solid fa-shop",
        json.dumps(["Healthcare", "Marketplace", "Data"]),
        "https://medmarket-starter.onrender.com",
        "https://github.com/Daud-stack/medmarket-starter.git",
        datetime.utcnow().isoformat(),
      ),
      (
        "OpsHub Intranet",
        "A healthcare operations intranet with secure staff sign-in, centralized access, and a polished admin-first experience.",
        "Images/Projects/opshub.svg",
        "fa-solid fa-user-doctor",
        json.dumps(["Healthcare", "Intranet", "Operations"]),
        "https://mdh-intranet.onrender.com",
        "",
        datetime.utcnow().isoformat(),
      ),
    ]
    cur.execute("SELECT COUNT(*) FROM projects")
    projects_count = cur.fetchone()[0]
    if projects_count == 0:
      cur.executemany(
        """
        INSERT INTO projects (title, description, image, icon_class, tags, case_study_url, source_url, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        sample_projects,
      )
    else:
      cur.execute("SELECT 1 FROM projects WHERE case_study_url = ?", ("https://mdh-intranet.onrender.com",))
      if cur.fetchone() is None:
        cur.execute(
          """
          INSERT INTO projects (title, description, image, icon_class, tags, case_study_url, source_url, created_at)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?)
          """,
          sample_projects[-1],
        )
    cur.execute("SELECT COUNT(*) FROM posts")
    posts_count = cur.fetchone()[0]
    if posts_count == 0:
      sample_posts = [
        (
          "From Raw Data to Reliable KPIs",
          "How I structure KPI definitions and build dashboards that teams actually use.",
          "from-raw-data-to-reliable-kpis",
          "Overview\nThis case study documents how raw operational data becomes trusted KPIs and dashboards. The focus is reliability: definitions, lineage, and alignment with decision cadence.\n\nContext\n- Multiple departments reporting the same metric differently\n- Manual weekly reports causing delays and errors\n- Low trust in numbers during executive reviews\n\n1) Discovery & KPI Alignment\n- Stakeholder interviews to define decisions, owners, and cadence\n- KPI dictionary: formula, grain, target, and exception logic\n- Data availability matrix (source, latency, owner, quality notes)\n\n2) Data Hygiene & Modeling\n- Source profiling: missingness, outliers, join integrity\n- Canonical dimensions: time, location, product, and customer\n- Fact tables built at the decision grain (daily/weekly)\n- “Golden record” rules for customer and product matching\n\n3) Validation & Trust\n- Backtesting 3–6 months of history against known reports\n- Variance thresholds with reconciliation notes\n- KPI approval workflow before executive rollout\n- Audit trail for metric changes\n\n4) Delivery & Adoption\n- Dashboard layers: executive summary + operational drilldowns\n- Alerting for threshold breaches\n- Training and a lightweight usage guide\n- Weekly KPI review ritual to reinforce ownership\n\nOutcome\n- One source of truth for KPIs\n- Faster weekly reporting cycles\n- Increased trust in dashboard numbers\n\nTools\nPython, SQL, Power BI/Tableau, automated QA checks.",
          "/post/from-raw-data-to-reliable-kpis",
          json.dumps(["KPIs", "Analytics", "Ops"]),
          "2025-01-10",
          datetime.utcnow().isoformat(),
        ),
        (
          "Ethical Data Practice in Early-Stage Projects",
          "A checklist for building responsible analytics from day one.",
          "ethical-data-practice-in-early-stage-projects",
          "Overview\nEthical analytics is not a “later” concern. This checklist is designed for early-stage teams where speed matters but trust matters more.\n\n1) Purpose & Consent\n- Define the decision you are enabling\n- Collect only what you need\n- Make consent explicit and easy to understand\n\n2) Data Minimization\n- Remove unnecessary fields at ingestion\n- Use pseudonymous identifiers where possible\n- Separate identifiers from behavioral data\n\n3) Bias & Fairness Checks\n- Segment performance by critical demographics\n- Monitor for selection bias and data gaps\n- Document tradeoffs and residual risk\n\n4) Transparency & Accountability\n- Model cards: what the model does, limits, and risks\n- Human override paths for high‑impact decisions\n- Post‑deployment monitoring and escalation triggers\n\n5) Security & Retention\n- Encrypt sensitive data at rest\n- Set retention windows and deletion routines\n- Implement least‑privilege access\n\nPractical Tip\nIf you can’t explain the logic to a non‑technical stakeholder, pause and simplify.\n\nOutcome\n- Faster buy‑in from stakeholders\n- Lower downstream compliance risk\n- Better long‑term trust with users",
          "/post/ethical-data-practice-in-early-stage-projects",
          json.dumps(["Ethics", "Governance"]),
          "2025-02-05",
          datetime.utcnow().isoformat(),
        ),
        (
          "Bridging Data Science, Quality, and AI in Africa",
          "How to align analytics, quality systems, and AI with real-world African constraints.",
          "bridging-data-science-quality-ai-africa",
          "Overview\nIn many African contexts, data science succeeds or fails based on infrastructure, data quality, and operational discipline. Quality systems provide the structure; AI provides leverage. The bridge is practical governance.\n\n1) Start with Process Discipline (Quality Systems)\n- Define workflows and data ownership\n- ISO‑aligned documentation for traceability\n- Internal audits for continuous improvement\n\n2) Build Reliable Data Pipelines\n- Offline‑first capture where connectivity is weak\n- Lightweight ETL with validation at the edge\n- Clear lineage from source to dashboard\n- Data quality gates before modeling\n\n3) Apply AI Where It Adds Measurable Value\n- Focus on high‑impact use cases (inventory, health outcomes, service delivery)\n- Use interpretable models when accountability is essential\n- Monitor drift and recalibrate with local context\n\n4) Address African Context Constraints\n- Low bandwidth: prioritize compressed data and batch sync\n- Local language data: invest in labeling and domain lexicons\n- Bias risk: test across regions and income bands\n- Affordability: optimize compute costs, prefer efficient models\n\nCase Patterns\n- Health labs: ISO 15189 + analytics for turnaround time\n- Safety systems: ISO 45001 + incident prediction dashboards\n- Governance: ISO 9001 + KPI compliance monitoring\n\nOutcome\nSustainable AI that respects constraints, improves quality, and earns trust from users and regulators.",
          "/post/bridging-data-science-quality-ai-africa",
          json.dumps(["AI", "Quality", "Africa"]),
          "2025-03-01",
          datetime.utcnow().isoformat(),
        ),
      ]
      cur.executemany(
        """
        INSERT INTO posts (title, excerpt, slug, content, url, tags, published_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        sample_posts,
      )
    conn.commit()


def row_to_project(row):
  return {
    "id": row["id"],
    "title": row["title"],
    "description": row["description"],
    "image": row["image"],
    "icon_class": row["icon_class"],
    "tags": json.loads(row["tags"] or "[]"),
    "case_study_url": row["case_study_url"],
    "source_url": row["source_url"],
  }


def row_to_post(row):
  return {
    "id": row["id"],
    "title": row["title"],
    "excerpt": row["excerpt"],
    "slug": row["slug"],
    "content": row["content"],
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


@app.get("/api/health")
def api_health():
  return {"status": "ok"}


@app.get("/api/projects")
def api_projects():
  with get_db() as conn:
    cur = conn.cursor()
    cur.execute("SELECT * FROM projects ORDER BY id DESC")
    rows = cur.fetchall()
  return [row_to_project(row) for row in rows]


@app.get("/api/posts")
def api_posts():
  with get_db() as conn:
    cur = conn.cursor()
    cur.execute("SELECT * FROM posts ORDER BY id DESC")
    rows = cur.fetchall()
  return [row_to_post(row) for row in rows]


@app.post("/api/contact")
def api_contact(payload: ContactIn, request: Request):
  name = payload.name.strip()
  message = payload.message.strip()
  if len(name) < 2 or len(message) < 5:
    raise HTTPException(status_code=400, detail="Message too short.")
  if len(name) > 100 or len(message) > 2000:
    raise HTTPException(status_code=400, detail="Message too long.")

  with get_db() as conn:
    cur = conn.cursor()
    cur.execute(
      """
      INSERT INTO contacts (name, email, message, created_at)
      VALUES (?, ?, ?, ?)
      """,
      (name, payload.email, message, datetime.utcnow().isoformat()),
    )
    conn.commit()

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
  with get_db() as conn:
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
  with get_db() as conn:
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM projects")
    projects_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM posts")
    posts_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM contacts")
    contacts_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM analytics")
    analytics_count = cur.fetchone()[0]
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
  with get_db() as conn:
    cur = conn.cursor()
    cur.execute("SELECT * FROM projects ORDER BY id DESC")
    rows = cur.fetchall()
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
  icon_class: str = Form(""),
  tags: str = Form(""),
  case_study_url: str = Form(""),
  source_url: str = Form(""),
):
  require_admin(request)
  tag_list = [t.strip() for t in tags.split(",") if t.strip()]
  with get_db() as conn:
    cur = conn.cursor()
    cur.execute(
      """
      INSERT INTO projects (title, description, image, icon_class, tags, case_study_url, source_url, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      """,
      (
        title,
        description,
        image,
        icon_class,
        json.dumps(tag_list),
        case_study_url,
        source_url,
        datetime.utcnow().isoformat(),
      ),
    )
    conn.commit()
  return RedirectResponse("/admin/projects", status_code=303)


@app.post("/admin/projects/update")
def admin_projects_update(
  request: Request,
  project_id: int = Form(...),
  title: str = Form(...),
  description: str = Form(...),
  image: str = Form(""),
  icon_class: str = Form(""),
  tags: str = Form(""),
  case_study_url: str = Form(""),
  source_url: str = Form(""),
):
  require_admin(request)
  tag_list = [t.strip() for t in tags.split(",") if t.strip()]
  with get_db() as conn:
    cur = conn.cursor()
    cur.execute(
      """
      UPDATE projects
      SET title = ?, description = ?, image = ?, icon_class = ?, tags = ?, case_study_url = ?, source_url = ?
      WHERE id = ?
      """,
      (
        title,
        description,
        image,
        icon_class,
        json.dumps(tag_list),
        case_study_url,
        source_url,
        project_id,
      ),
    )
    conn.commit()
  return RedirectResponse("/admin/projects", status_code=303)


@app.post("/admin/projects/delete")
def admin_projects_delete(request: Request, project_id: int = Form(...)):
  require_admin(request)
  with get_db() as conn:
    cur = conn.cursor()
    cur.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
  return RedirectResponse("/admin/projects", status_code=303)


@app.get("/admin/posts", response_class=HTMLResponse)
def admin_posts(request: Request):
  require_admin(request)
  with get_db() as conn:
    cur = conn.cursor()
    cur.execute("SELECT * FROM posts ORDER BY id DESC")
    rows = cur.fetchall()
  posts = [row_to_post(row) for row in rows]
  return templates.TemplateResponse("admin_posts.html", {"request": request, "posts": posts})


@app.get("/post/{slug}", response_class=HTMLResponse)
def post_detail(request: Request, slug: str):
  with get_db() as conn:
    cur = conn.cursor()
    cur.execute("SELECT * FROM posts WHERE slug = ?", (slug,))
    row = cur.fetchone()
  if not row:
    raise HTTPException(status_code=404)
  post = row_to_post(row)
  return templates.TemplateResponse("post_detail.html", {"request": request, "post": post})


@app.post("/admin/posts/create")
def admin_posts_create(
  request: Request,
  title: str = Form(...),
  excerpt: str = Form(...),
  slug: str = Form(""),
  content: str = Form(""),
  url: str = Form(""),
  tags: str = Form(""),
  published_at: str = Form(""),
):
  require_admin(request)
  tag_list = [t.strip() for t in tags.split(",") if t.strip()]
  with get_db() as conn:
    cur = conn.cursor()
    cur.execute(
      """
      INSERT INTO posts (title, excerpt, slug, content, url, tags, published_at, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      """,
      (
        title,
        excerpt,
        slug,
        content,
        url,
        json.dumps(tag_list),
        published_at,
        datetime.utcnow().isoformat(),
      ),
    )
    conn.commit()
  return RedirectResponse("/admin/posts", status_code=303)


@app.post("/admin/posts/update")
def admin_posts_update(
  request: Request,
  post_id: int = Form(...),
  title: str = Form(...),
  excerpt: str = Form(...),
  slug: str = Form(""),
  content: str = Form(""),
  url: str = Form(""),
  tags: str = Form(""),
  published_at: str = Form(""),
):
  require_admin(request)
  tag_list = [t.strip() for t in tags.split(",") if t.strip()]
  with get_db() as conn:
    cur = conn.cursor()
    cur.execute(
      """
      UPDATE posts
      SET title = ?, excerpt = ?, slug = ?, content = ?, url = ?, tags = ?, published_at = ?
      WHERE id = ?
      """,
      (
        title,
        excerpt,
        slug,
        content,
        url,
        json.dumps(tag_list),
        published_at,
        post_id,
      ),
    )
    conn.commit()
  return RedirectResponse("/admin/posts", status_code=303)


@app.post("/admin/posts/delete")
def admin_posts_delete(request: Request, post_id: int = Form(...)):
  require_admin(request)
  with get_db() as conn:
    cur = conn.cursor()
    cur.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    conn.commit()
  return RedirectResponse("/admin/posts", status_code=303)


@app.get("/admin/analytics", response_class=HTMLResponse)
def admin_analytics(request: Request):
  require_admin(request)
  with get_db() as conn:
    cur = conn.cursor()
    cur.execute("SELECT * FROM analytics ORDER BY id DESC LIMIT 200")
    rows = cur.fetchall()
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
