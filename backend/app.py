import json
import os
import secrets
import sqlite3
import smtplib
from hmac import compare_digest
from contextlib import contextmanager, asynccontextmanager
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse, FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel, EmailStr, Field


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "backend" / "data"
DB_PATH = DATA_DIR / "app.db"
FRONTEND_DIR = BASE_DIR

DATA_DIR.mkdir(parents=True, exist_ok=True)

APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("APP_PORT", "9000"))
IS_PRODUCTION = (
  os.getenv("APP_ENV", "").lower() == "production"
  or os.getenv("RENDER", "").lower() == "true"
)


def env_secret(name: str, local_default: str) -> str:
  value = os.getenv(name)
  if IS_PRODUCTION and (not value or value == local_default):
    raise RuntimeError(f"{name} must be configured in production.")
  return value or local_default


SECRET_KEY = env_secret("SECRET_KEY", "change-me")
ADMIN_PASSWORD = env_secret("ADMIN_PASSWORD", "change-me")

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or 587)
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "")
SMTP_TO_EMAIL = os.getenv("SMTP_TO_EMAIL", "")

BROKEN_PROJECT_DEMO_URLS = set()

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
  meta: dict = Field(default_factory=dict)


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
    cur.executemany(
      "UPDATE projects SET case_study_url = '' WHERE case_study_url = ?",
      [(url,) for url in BROKEN_PROJECT_DEMO_URLS],
    )
    cur.execute(
      "UPDATE projects SET case_study_url = 'https://personal-productivity-app-3ml0.onrender.com' "
      "WHERE title = 'Personal Productivity App' AND (case_study_url = '' OR case_study_url IS NULL)"
    )
    sample_posts = [
      (
        "From Raw Data to Reliable KPIs",
        "A practical reflection on turning scattered operational records into trusted metrics, governance rituals, and dashboards people can use with confidence.",
        "from-raw-data-to-reliable-kpis",
        "Overview\nReliable KPIs are not created by a charting tool. They are created when teams agree on what matters, define it clearly, test it against reality, and build a rhythm for using it. This note explains how I move from raw operational data to dashboards that decision-makers can trust.\n\nWhy This Matters\nMany teams already have data, but they do not always have confidence. A sales team may define active customers one way, finance may define them another, and operations may track them manually in a spreadsheet. When those numbers meet in a leadership meeting, the discussion becomes about whose report is correct instead of what action should be taken.\n\nMy approach starts by treating KPI work as both a technical and human problem. The data model matters, but so do definitions, ownership, review habits, and the trust people build through repeated validation.\n\n1) Discovery: Start With Decisions, Not Charts\nBefore building anything, I map the decisions the dashboard should support.\n\nKey questions:\n- What decision will this metric influence?\n- Who owns the decision?\n- How often is the decision made?\n- What action should happen when the number changes?\n- What source system is closest to the truth?\n\nThis keeps the dashboard from becoming a gallery of attractive but unused visuals. A KPI should earn its place by helping someone act.\n\n2) KPI Definition: Make Meaning Explicit\nA reliable KPI needs a written definition. I document:\n- Metric name and purpose\n- Formula and calculation grain\n- Included and excluded records\n- Data source and refresh frequency\n- Owner and approval path\n- Known limitations\n- Example interpretation\n\nExample: instead of simply reporting turnaround time, I would define when the clock starts, when it stops, how weekends are handled, how outliers are treated, and which team is responsible for investigating delays.\n\n3) Data Hygiene: Find Weakness Before Users Do\nRaw data usually carries gaps, duplicates, inconsistent categories, and timestamp problems. I profile the data before modeling it.\n\nChecks I look for:\n- Missing fields in critical columns\n- Duplicate identifiers\n- Broken joins between tables\n- Outliers that may be real or may be entry errors\n- Inconsistent naming conventions\n- Records outside expected date ranges\n\nThis is where Python and SQL become useful companions. Python helps with profiling and repeatable checks; SQL helps test joins, grains, and reconciliation totals.\n\n4) Modeling: Build Around the Decision Grain\nA dashboard becomes fragile when metrics are calculated at the wrong grain. I separate dimensions, facts, and lookup tables so that each metric can be aggregated safely.\n\nA simple structure might include:\n- Date dimension for consistent time grouping\n- Department or location dimension for accountability\n- Fact table at daily, weekly, or transaction level\n- KPI dictionary that connects business meaning to technical logic\n\nThe goal is not complexity. The goal is traceability. A user should be able to ask where a number came from and get a clear answer.\n\n5) Validation: Compare Against Known Reality\nBefore launch, I compare the new metrics against existing reports, historical expectations, and stakeholder knowledge.\n\nValidation methods:\n- Backtest three to six months of history\n- Reconcile totals with trusted manual reports\n- Explain material differences in plain language\n- Document accepted variance thresholds\n- Review sample records with business owners\n\nThis step is where trust is earned. If numbers differ, the answer should not be hidden. It should be explained.\n\n6) Dashboard Delivery: Design for Action\nA useful dashboard should help people move from signal to action quickly.\n\nI prefer three layers:\n- Executive view: what changed, where attention is needed, and whether targets are being met\n- Operational view: breakdowns by team, location, process, or segment\n- Diagnostic view: details that help investigate root causes\n\nGood dashboards reduce cognitive load. They use clear labels, consistent time periods, meaningful color, and enough context to prevent misreading.\n\n7) Adoption: Build a Review Ritual\nA dashboard without a review habit slowly becomes decoration. I encourage teams to attach dashboards to recurring meetings and decision cycles.\n\nA weekly KPI review might ask:\n- What changed since last week?\n- Which metric is outside threshold?\n- What is the likely cause?\n- Who owns the next action?\n- What should be checked before the next meeting?\n\nOutcome\nWhen this process works, the result is more than a dashboard. The organization gains a shared language for performance.\n\nExpected gains:\n- Fewer arguments about definitions\n- Faster reporting cycles\n- Clearer ownership\n- Better root-cause discussions\n- Stronger trust in data\n\nTools and Practices\nPython, SQL, Power BI or Tableau, spreadsheet reconciliation, KPI dictionaries, automated quality checks, stakeholder interviews, and recurring review rituals.\n\nReflection\nThe best KPI systems are not the loudest or most complicated. They are the ones people return to because the numbers are clear, the logic is traceable, and the next action is obvious.",
        "/post/from-raw-data-to-reliable-kpis",
        json.dumps(["KPIs", "Analytics", "Ops", "Dashboards"]),
        "2025-01-10",
        datetime.utcnow().isoformat(),
      ),
      (
        "Ethical Data Practice in Early-Stage Projects",
        "A deeper checklist for building analytics and AI workflows that respect privacy, reduce harm, and earn trust before a project scales.",
        "ethical-data-practice-in-early-stage-projects",
        "Overview\nEthical data practice is not something to add after a project becomes successful. It should shape the project from the first spreadsheet, form, dashboard, or AI workflow. Early-stage projects often move quickly, but speed without guardrails can create privacy risks, biased decisions, and systems that users do not trust.\n\nThis note is a practical checklist I use when thinking about responsible analytics, especially where data connects to people, health, work, finance, access, or opportunity.\n\n1) Start With Purpose\nThe first ethical question is simple: why are we collecting this data?\n\nA strong purpose statement should answer:\n- What decision are we trying to improve?\n- Who benefits from the analysis?\n- Who could be harmed if the analysis is wrong?\n- What data is truly necessary?\n- What should not be collected?\n\nPurpose creates boundaries. If a field does not support the purpose, it should be challenged.\n\n2) Practice Data Minimization\nData minimization means collecting the least amount of data needed to solve the problem well. This reduces privacy risk and simplifies governance.\n\nPractical actions:\n- Remove unnecessary personal identifiers\n- Avoid collecting sensitive fields unless there is a clear need\n- Separate identity data from behavioral or operational data\n- Limit free-text fields where sensitive information may be entered accidentally\n- Define retention periods early\n\nThe discipline is to resist the phrase: we may need it later. If later comes, the need can be reviewed then.\n\n3) Make Consent Understandable\nConsent should not be buried in language only specialists can understand. People should know what is being collected, why it is being collected, how it will be used, and whether it may influence decisions about them.\n\nGood consent is:\n- Specific\n- Plain-language\n- Easy to access\n- Easy to withdraw where possible\n- Honest about limitations\n\n4) Check Bias Before It Becomes a System\nBias often enters through historical data, missing records, uneven access, or assumptions built into categories. The danger is not only biased models; even dashboards can amplify unfairness when they present incomplete data as complete truth.\n\nQuestions to ask:\n- Which groups are underrepresented?\n- Are some locations, income bands, languages, or age groups missing?\n- Does the data reflect past inequality?\n- Are we using proxy variables that may create unfair treatment?\n- Could this metric punish teams or people for conditions outside their control?\n\n5) Keep Humans in High-Impact Decisions\nAI and analytics can support decisions, but high-impact decisions should include human review, appeal paths, and accountability.\n\nThis matters in areas such as:\n- Healthcare prioritization\n- Hiring or performance review\n- Credit, pricing, or eligibility\n- Safety and incident response\n- Education or social services\n\nA model can point to risk. A person should still understand context.\n\n6) Be Transparent About Limits\nEvery dashboard, model, or AI workflow has limits. Stating those limits is not weakness; it is professionalism.\n\nDocumentation should include:\n- What the system does\n- What data it uses\n- What it does not know\n- Known failure modes\n- Update frequency\n- Who to contact when something looks wrong\n\nFor AI workflows, I also document where human review is required and where generated output must not be treated as final truth.\n\n7) Secure the Data Lifecycle\nEthics and security are connected. A project cannot claim to respect users if it leaves their data exposed.\n\nMinimum practices:\n- Strong access control\n- Least-privilege permissions\n- Secure backups\n- Encrypted storage where appropriate\n- Audit trails for sensitive changes\n- Deletion routines when retention periods expire\n\n8) Monitor After Launch\nEthical practice continues after deployment. Data shifts, user behavior changes, and systems can drift away from their original intent.\n\nPost-launch checks:\n- Are people using the dashboard as intended?\n- Are decisions improving?\n- Are any groups being disadvantaged?\n- Are users reporting confusion or harm?\n- Is the data still accurate enough for the decisions being made?\n\nOutcome\nA responsible data project should create trust, not just insight.\n\nExpected benefits:\n- Lower compliance risk\n- Stronger stakeholder confidence\n- Better user acceptance\n- Fewer harmful surprises\n- More durable systems\n\nPractical Principle\nIf I cannot explain the data logic, limitations, and consequences to a non-technical stakeholder, the work is not ready. Clarity is part of responsibility.\n\nReflection\nEthical analytics is not about slowing innovation. It is about making innovation strong enough to last. The goal is to build systems that improve decisions while respecting the people behind the data.",
        "/post/ethical-data-practice-in-early-stage-projects",
        json.dumps(["Ethics", "Governance", "AI", "Privacy"]),
        "2025-02-05",
        datetime.utcnow().isoformat(),
      ),
      (
        "Bridging Data Science, Quality, and AI in Africa",
        "A reflection on building useful analytics and AI in African contexts by combining quality systems, local realities, governance, and practical deployment discipline.",
        "bridging-data-science-quality-ai-africa",
        "Overview\nData science and AI can create real value in Africa, but only when they are built with local realities in mind. The challenge is not only technical. It includes infrastructure, documentation, data quality, language, trust, cost, regulation, and the daily pressures of organizations trying to serve people with limited resources.\n\nThis reflection explains why I see quality systems as a bridge between data science and responsible AI. Quality gives structure. Data science gives insight. AI gives leverage. Together, they can help organizations make better decisions, improve services, and build systems that last.\n\n1) Why Quality Systems Matter\nAI depends on data, and data depends on process. If the process is unclear, the data becomes unreliable. If the data is unreliable, the model or dashboard becomes fragile.\n\nQuality systems help by defining:\n- Workflows\n- Responsibilities\n- Documentation standards\n- Review cycles\n- Corrective actions\n- Audit trails\n- Continuous improvement routines\n\nStandards such as ISO 9001, ISO 15189, ISO 45001, and ISO 7101 are not just paperwork. Used well, they create the discipline needed for reliable analytics.\n\n2) Start With Operational Reality\nMany African organizations work with constraints that global case studies often ignore.\n\nCommon constraints:\n- Intermittent internet connectivity\n- Manual records and fragmented spreadsheets\n- Limited technical staff\n- High cost of cloud tools\n- Inconsistent data capture\n- Multiple local languages\n- Informal workarounds that keep operations moving\n\nA good solution respects these constraints instead of pretending they do not exist.\n\n3) Build Offline-First and Low-Bandwidth Thinking\nNot every system should assume constant connectivity. In some contexts, batch sync, compressed data, and simple local capture tools may create more value than a sophisticated cloud-only system.\n\nDesign principles:\n- Capture only what is needed\n- Validate data at entry point\n- Allow offline capture where necessary\n- Sync in batches\n- Compress files and reports\n- Keep interfaces simple and fast\n\n4) Use AI Where It Adds Measurable Value\nAI should not be added because it sounds modern. It should solve a real problem better, faster, or more consistently than the current approach.\n\nUseful AI patterns may include:\n- Summarizing long reports for managers\n- Drafting audit preparation notes\n- Classifying support requests\n- Detecting unusual operational patterns\n- Assisting with data cleaning and documentation\n- Translating or simplifying technical guidance\n- Supporting forecasting for inventory or service demand\n\nThe key question is: what decision or workflow improves because AI is present?\n\n5) Keep Human Review in the Loop\nIn high-impact environments, AI should support people, not replace accountability. A generated summary, forecast, or risk score should be reviewed before it influences serious decisions.\n\nHuman review is especially important in:\n- Health services\n- Safety systems\n- Financial access\n- Hiring and performance decisions\n- Public service delivery\n- Compliance and audit work\n\n6) Invest in Local Language and Context\nLanguage is not a cosmetic layer. It affects adoption, trust, and accuracy. If tools only work well in English, many users are left at the edge of the system.\n\nBetter practice includes:\n- Local language interfaces where useful\n- Domain-specific glossaries\n- Human-reviewed translations\n- Training examples from local contexts\n- Clear explanations for non-technical users\n\n7) Govern the System, Not Just the Model\nA model can be accurate in testing and still fail in practice if governance is weak.\n\nGovernance should cover:\n- Who owns the data\n- Who approves metric definitions\n- Who reviews AI outputs\n- How errors are reported\n- How changes are documented\n- How performance is monitored\n- When the system should be paused or updated\n\n8) Case Patterns\nHealthcare laboratories:\nISO 15189 documentation plus analytics can improve turnaround time, sample tracking, stock visibility, and non-conformance reporting.\n\nWorkplace safety:\nISO 45001 systems plus dashboards can reveal incident patterns, training gaps, and high-risk processes.\n\nBusiness operations:\nKPI governance plus AI-assisted reporting can help teams summarize performance, detect bottlenecks, and prepare management briefs faster.\n\nPublic service delivery:\nSimple data pipelines plus local-language support can improve visibility, accountability, and planning.\n\nOutcome\nThe strongest data and AI systems in Africa will not simply copy tools from elsewhere. They will be practical, governed, affordable, multilingual where needed, and aligned with real workflows.\n\nExpected benefits:\n- Better decision visibility\n- Stronger accountability\n- More reliable reporting\n- Faster service improvement\n- Higher trust from users and regulators\n- AI adoption that respects people and context\n\nReflection\nFor me, the future is not data science alone, quality alone, or AI alone. The opportunity is in the bridge between them. When process discipline, reliable data, and responsible AI work together, organizations can move from reacting to problems toward learning, improving, and serving people better.",
        "/post/bridging-data-science-quality-ai-africa",
        json.dumps(["AI", "Quality", "Africa", "Governance"]),
        "2025-03-01",
        datetime.utcnow().isoformat(),
      ),
    ]
    for post in sample_posts:
      (
        title,
        excerpt,
        slug,
        content,
        url,
        tags,
        published_at,
        created_at,
      ) = post
      cur.execute("SELECT 1 FROM posts WHERE slug = ?", (slug,))
      if cur.fetchone():
        cur.execute(
          """
          UPDATE posts
          SET title = ?, excerpt = ?, content = ?, url = ?, tags = ?, published_at = ?
          WHERE slug = ?
          """,
          (title, excerpt, content, url, tags, published_at, slug),
        )
      else:
        cur.execute(
          """
          INSERT INTO posts (title, excerpt, slug, content, url, tags, published_at, created_at)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?)
          """,
          post,
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


def csrf_token(request: Request) -> str:
  token = request.session.get("csrf_token")
  if not token:
    token = secrets.token_urlsafe(32)
    request.session["csrf_token"] = token
  return token


def validate_csrf_token(request: Request, submitted_token: str):
  expected_token = request.session.get("csrf_token")
  if not expected_token or not compare_digest(expected_token, submitted_token):
    raise HTTPException(status_code=403, detail="Invalid CSRF token")


def admin_template(request: Request, template_name: str, context: dict | None = None, status_code: int = 200):
  template_context = {"request": request, "csrf_token": csrf_token(request)}
  if context:
    template_context.update(context)
  return templates.TemplateResponse(template_name, template_context, status_code=status_code)


def safe_frontend_file(path: str) -> Path | None:
  try:
    frontend_root = FRONTEND_DIR.resolve()
    requested_file = (frontend_root / path).resolve()
    requested_file.relative_to(frontend_root)
  except (OSError, ValueError):
    return None
  if requested_file.exists() and requested_file.is_file():
    return requested_file
  return None


def validate_tracking_payload(payload: TrackIn):
  if not payload.event_name or len(payload.event_name) > 80:
    raise HTTPException(status_code=400, detail="Invalid event name.")
  if not (
    payload.event_name == "pageview"
    or payload.event_name == "contact-submit"
    or payload.event_name.startswith("link-")
  ):
    raise HTTPException(status_code=400, detail="Unsupported event.")
  if not payload.path.startswith("/") or len(payload.path) > 200:
    raise HTTPException(status_code=400, detail="Invalid path.")
  meta_json = json.dumps(payload.meta)
  if len(meta_json) > 1000:
    raise HTTPException(status_code=400, detail="Metadata too large.")


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
  validate_tracking_payload(payload)
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
  return admin_template(request, "admin_login.html")


@app.post("/admin/login")
def admin_login_post(request: Request, password: str = Form(...), csrf: str = Form("")):
  validate_csrf_token(request, csrf)
  if not compare_digest(password, ADMIN_PASSWORD):
    return admin_template(
      request,
      "admin_login.html",
      {"error": "Invalid password."},
      status_code=401,
    )
  request.session["admin"] = True
  return RedirectResponse("/admin", status_code=303)


@app.post("/admin/logout")
def admin_logout(request: Request, csrf: str = Form("")):
  require_admin(request)
  validate_csrf_token(request, csrf)
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
  return admin_template(
    request,
    "admin_dashboard.html",
    {
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
  return admin_template(request, "admin_projects.html", {"projects": projects})


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
  csrf: str = Form(""),
):
  require_admin(request)
  validate_csrf_token(request, csrf)
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
  csrf: str = Form(""),
):
  require_admin(request)
  validate_csrf_token(request, csrf)
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
def admin_projects_delete(request: Request, project_id: int = Form(...), csrf: str = Form("")):
  require_admin(request)
  validate_csrf_token(request, csrf)
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
  return admin_template(request, "admin_posts.html", {"posts": posts})


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
  csrf: str = Form(""),
):
  require_admin(request)
  validate_csrf_token(request, csrf)
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
  csrf: str = Form(""),
):
  require_admin(request)
  validate_csrf_token(request, csrf)
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
def admin_posts_delete(request: Request, post_id: int = Form(...), csrf: str = Form("")):
  require_admin(request)
  validate_csrf_token(request, csrf)
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
  return admin_template(request, "admin_analytics.html", {"events": events})


@app.get("/", response_class=HTMLResponse)
def serve_index():
  index_path = FRONTEND_DIR / "index.html"
  return FileResponse(index_path)


@app.get("/{path:path}")
def serve_static(path: str):
  if path.startswith("api") or path.startswith("admin"):
    raise HTTPException(status_code=404)
  file_path = safe_frontend_file(path)
  if file_path:
    return FileResponse(file_path)
  index_path = FRONTEND_DIR / "index.html"
  if index_path.exists():
    return FileResponse(index_path)
  raise HTTPException(status_code=404)


if __name__ == "__main__":
  import uvicorn

  reload_enabled = os.getenv("APP_RELOAD", "0") == "1"
  uvicorn.run("app:app", host=APP_HOST, port=APP_PORT, reload=reload_enabled)
