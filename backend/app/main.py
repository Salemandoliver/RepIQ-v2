import logging
import os
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .config import settings
from .db import Base, engine, SessionLocal
from .routers import (auth_router, calls_router, insights_router,
                      admin_router, reports_router, webhooks_router,
                      playlists_router, companyiq_router, salesiq_router,
                      intelligence_router, teams_router, company_router)
# RepIQ v2 modular monolith: core + feature modules self-register with the registry.
from .core import audit as _audit_models          # noqa: F401  registers audit_log on Base.metadata
from .core import registry as module_registry
from .modules import hr as _hr_module             # noqa: F401  registers HR module + its tables
from .modules import catalog as _catalog_module   # noqa: F401  registers product catalogue + its tables
from .modules import campaigns as _campaigns_module  # noqa: F401  registers Campaigns (promotions + incentives)
from .modules import orders as _orders_module        # noqa: F401  registers Order Entry (orders + commission + Schedule 5)

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="CallIQ API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

for r in (auth_router, calls_router, insights_router, admin_router,
          reports_router, webhooks_router, playlists_router, companyiq_router,
          salesiq_router, intelligence_router, teams_router, company_router):
    app.include_router(r.router)

# Feature modules registered via the core registry (HR, and future Orders, …).
for _mod_router in module_registry.all_routers():
    app.include_router(_mod_router)


@app.get("/api/health")
def health():
    return {"ok": True, "app": settings.app_name, "demo_mode": settings.demo_mode}


def _ensure_columns():
    """Lightweight additive migrations for create_all-managed schemas (no Alembic).
    Adds columns introduced after a table was first created. Idempotent + safe."""
    stmts = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS short_name VARCHAR(120)",
        # Auth / onboarding lifecycle
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS must_set_password BOOLEAN DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token VARCHAR(64)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token_expires TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS left_on TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS left_by_id INTEGER",
        # RepIQ v2 platform RBAC
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS platform_role VARCHAR(20)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS scopes JSON",
        "ALTER TABLE calls ADD COLUMN IF NOT EXISTS process_attempts INTEGER DEFAULT 0",
        # Intelligence Layer — call outcome logging (keystone)
        "ALTER TABLE calls ADD COLUMN IF NOT EXISTS outcome VARCHAR(24)",
        "ALTER TABLE calls ADD COLUMN IF NOT EXISTS outcome_note TEXT",
        "ALTER TABLE calls ADD COLUMN IF NOT EXISTS outcome_at TIMESTAMP",
        "ALTER TABLE calls ADD COLUMN IF NOT EXISTS outcome_by INTEGER",
        # Intelligence Layer — post-call coaching-card fields on call_analyses
        "ALTER TABLE call_analyses ADD COLUMN IF NOT EXISTS interruptions INTEGER DEFAULT 0",
        "ALTER TABLE call_analyses ADD COLUMN IF NOT EXISTS filler_count INTEGER DEFAULT 0",
        "ALTER TABLE call_analyses ADD COLUMN IF NOT EXISTS question_breakdown JSON",
        "ALTER TABLE call_analyses ADD COLUMN IF NOT EXISTS objections JSON",
        "ALTER TABLE call_analyses ADD COLUMN IF NOT EXISTS strengths JSON",
        "ALTER TABLE call_analyses ADD COLUMN IF NOT EXISTS improvements JSON",
        "ALTER TABLE call_analyses ADD COLUMN IF NOT EXISTS one_thing TEXT",
        "ALTER TABLE call_analyses ADD COLUMN IF NOT EXISTS energy_note TEXT",
        "ALTER TABLE call_analyses ADD COLUMN IF NOT EXISTS best_moment JSON",
        "ALTER TABLE call_analyses ADD COLUMN IF NOT EXISTS followups JSON",
        # Feature 8 — HeyGen completed video_url is a long signed URL; varchar(500) truncates it.
        "ALTER TABLE performance_videos ALTER COLUMN video_url TYPE TEXT",
        # Order Entry — BT financial-year week + the "Order Placed" flag.
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS week_number INTEGER",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS week_year INTEGER",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS placed BOOLEAN DEFAULT FALSE",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS placed_at TIMESTAMP",
        # Cobra GM = the GM BT actually paid us per line (drives the commission run).
        "ALTER TABLE order_lines ADD COLUMN IF NOT EXISTS cobra_gm DOUBLE PRECISION",
    ]
    from sqlalchemy import text
    # Each statement in its OWN transaction — so one failure can't abort the others (a single
    # shared transaction aborts entirely on any error in Postgres, which could leave a column
    # missing and break every query, including login).
    for s in stmts:
        try:
            with engine.begin() as conn:
                conn.execute(text(s))
        except Exception as e:  # already-exists / SQLite limitations — safe to ignore
            logging.getLogger("calliq").warning("migration skipped: %s (%s)", s, e)


def _derive_platform_role(db, u, role_for_user, ops_first_names: set[str]) -> str:
    """Map an existing user to a RepIQ v2 platform role (employee|manager|operations|admin)."""
    if (u.role or "") == "admin":
        return "admin"
    title = (u.job_title or "").lower()
    team_name = ""
    if u.team_id:
        from .models import Team
        t = db.get(Team, u.team_id)
        team_name = (t.name if t else "").lower()
    sales = role_for_user(db, u)                       # rep | bc | manager | None
    if ("operation" in title or "ops" in title.split() or "aftersales" in title
            or "operation" in team_name):
        return "operations"
    # Known Operations team members (their sales role resolves to None) — best-effort seed;
    # admin can correct any of these from the People page (the role is admin-assignable).
    first = ((u.name or "").strip().split(" ") or [""])[0].lower()
    if sales is None and first in ops_first_names:
        return "operations"
    if sales == "manager":
        return "manager"
    return "employee"


def _backfill_platform_roles(db):
    """One-time, idempotent backfill of User.platform_role + scopes (RepIQ v2 RBAC). Only fills
    values that are unset, so it is safe to run on every boot and never overrides admin edits."""
    from .models import User
    from .services.salesiq.roles import role_for_user
    FINANCIAL_ACCOUNTS = {"admin@btlocalbusiness.co.uk", "szerti@synvestment.co.uk"}
    OPS_FIRST_NAMES = {"zahida", "james", "lee", "michelle", "elli"}
    log = logging.getLogger("calliq")
    changed = 0
    for u in db.query(User).all():
        touched = False
        if not getattr(u, "platform_role", None):
            u.platform_role = _derive_platform_role(db, u, role_for_user, OPS_FIRST_NAMES)
            touched = True
        if getattr(u, "scopes", None) is None:
            u.scopes = ["financial"] if u.email.lower() in FINANCIAL_ACCOUNTS else []
            touched = True
        elif u.email.lower() in FINANCIAL_ACCOUNTS and "financial" not in (u.scopes or []):
            u.scopes = list(u.scopes or []) + ["financial"]
            touched = True
        changed += 1 if touched else 0
    if changed:
        db.commit()
        log.info("platform_role/scopes backfill: updated %d user(s)", changed)


def _backfill_order_weeks(db):
    """One-time, idempotent: stamp the BT financial week on any order missing it (e.g. the orders
    imported before the week_number column existed). Derived from the order date; safe every boot."""
    from .modules.orders.models import Order
    from .modules.orders.services import stamp_week
    rows = db.query(Order).filter(Order.week_number.is_(None), Order.order_date.isnot(None)).all()
    for o in rows:
        stamp_week(o)
    if rows:
        db.commit()
        logging.getLogger("calliq").info("order week backfill: stamped %d order(s)", len(rows))


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    try:
        _ensure_columns()
    except Exception:
        logging.getLogger("calliq").exception("column migration failed")
    db = SessionLocal()
    try:
        from .seed.bootstrap import ensure_bootstrap
        ensure_bootstrap(db)
        try:
            _backfill_platform_roles(db)
        except Exception:
            logging.getLogger("calliq").exception("platform role backfill failed")
        try:
            from .modules.catalog.models import seed_products
            seed_products(db)
        except Exception:
            logging.getLogger("calliq").exception("product catalogue seed failed")
        try:
            from .modules.orders.extra_router import seed_order_products
            seed_order_products(db)
        except Exception:
            logging.getLogger("calliq").exception("order product seed failed")
        try:
            _backfill_order_weeks(db)
        except Exception:
            logging.getLogger("calliq").exception("order week backfill failed")
        # Emergency access recovery: set ADMIN_RESET_PASSWORD in the environment to reset the
        # admin@btlocalbusiness.co.uk password on boot (then remove the variable again).
        _reset_pw = os.environ.get("ADMIN_RESET_PASSWORD", "").strip()
        if _reset_pw:
            from .models import User as _User
            from .auth import hash_password as _hash
            _a = db.query(_User).filter(_User.email == "admin@btlocalbusiness.co.uk").first()
            if _a:
                _a.password_hash = _hash(_reset_pw)
                db.commit()
                logging.getLogger("calliq").info("Admin password reset via ADMIN_RESET_PASSWORD")
        if settings.demo_mode:
            from .seed.demo import seed_demo_if_empty
            seed_demo_if_empty(db)
    finally:
        db.close()
    # Single-service deployments (e.g. Railway): run the pipeline worker in-process.
    # Default ON; set RUN_WORKER_IN_APP=false only if running a separate worker process.
    if os.environ.get("RUN_WORKER_IN_APP", "true").lower() not in ("0", "false", "no"):
        from .pipeline.worker import run_forever
        threading.Thread(target=run_forever, daemon=True, name="calliq-worker").start()
        logging.getLogger("calliq").info("In-process worker thread started")


# ---- Static frontend (present when built into the image; see root Dockerfile) ----
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        candidate = os.path.normpath(os.path.join(_static_dir, full_path))
        if (full_path and candidate.startswith(_static_dir)
                and os.path.isfile(candidate)):
            return FileResponse(candidate)
        return FileResponse(os.path.join(_static_dir, "index.html"))
