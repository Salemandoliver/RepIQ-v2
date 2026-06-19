"""SalesIQ — role-aware sales performance dashboard (Feature Brief v2.0).

Phase 1: Sales Rep view (Sales Tracker + CallIQ calls) + targets by job title + manager
team-overall figures. Roles/targets derive from the user's job title; Operations roles get
no SalesIQ access.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_admin
from ..db import get_db
from ..models import User
from ..services.salesiq import graph, sales, trackers
from ..services.salesiq.dashboard import bc_dashboard, rep_dashboard
from ..services.salesiq.manager import holiday_calendar_view, manager_dashboard, match_debug
from ..services.salesiq.roles import get_all_targets, role_for_user, save_targets

router = APIRouter(prefix="/api/salesiq", tags=["salesiq"])


@router.get("/dashboard")
def dashboard(period: str = Query("mtd"), month: str | None = None, user_id: int | None = None,
              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The viewer's dashboard. Managers may request another user's via ?user_id=. A specific
    sales month can be viewed via ?month=YYYY-MM."""
    role = role_for_user(db, user)
    if role is None:
        return {"meta": {"access": False, "name": user.name,
                         "reason": "SalesIQ isn't available for your role."}}
    target = user
    if user_id and user_id != user.id:
        if role != "manager":
            raise HTTPException(403, "Not permitted to view another user's dashboard")
        target = db.get(User, user_id)
        if not target:
            raise HTTPException(404, "User not found")
    target_role = role_for_user(db, target) or "rep"
    if target_role == "bc":
        return bc_dashboard(db, target, period=period, month=month)
    return rep_dashboard(db, target, period=period, role=target_role, month=month)


@router.get("/manager")
def manager(period: str = Query("month"), team: str | None = None,
            db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Team intelligence digest (managers/admin only). period = week|month|quarter;
    optional team filter (all | business creators | value | volume | bdm)."""
    if role_for_user(db, user) != "manager":
        raise HTTPException(403, "Manager view is not available for your role")
    return manager_dashboard(db, period=period, team=team)


@router.get("/holiday-calendar")
def holiday_calendar(ym: str | None = None, team: str | None = None,
                     db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Month holiday grid (registered app users only) for the calendar popup (managers/admin).
    ym = YYYY-MM; optional team filter."""
    if role_for_user(db, user) != "manager":
        raise HTTPException(403, "Not permitted")
    from datetime import date
    if ym and len(ym) >= 7:
        y, m = int(ym[:4]), int(ym[5:7])
    else:
        t = date.today()
        y, m = t.year, t.month
    return holiday_calendar_view(db, y, m, team)


@router.post("/refresh")
def refresh(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Force-reload the trackers now so a just-placed order shows immediately."""
    if role_for_user(db, user) is None:
        raise HTTPException(403, "SalesIQ isn't available for your role")
    sales.refresh()
    trackers.refresh()
    return {"ok": True, "months": len(sales.status().get("months", []))}


@router.get("/status")
def status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..config import settings
    return {
        "role": role_for_user(db, user),
        "trackers": {
            "sales": sales.configured(),
            "leads": trackers.leads_configured(),
            "activity": trackers.activity_configured(),
            "holiday": trackers.holiday_configured(),
        },
    }


@router.get("/sales-debug")
def sales_debug(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return sales.status()


@router.get("/master-debug")
def master_debug(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Dump the Sales Tracker 'Master Dashboard' sheet so its layout can be wired up."""
    return sales.master_dashboard_dump()


@router.get("/match-debug")
def match_dbg(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Name-matching diagnosis: tracker agents ↔ CallIQ reps, and who has no match."""
    return match_debug(db)


@router.get("/graph-debug")
def graph_debug(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Graph (Sites.Selected) connectivity + what files the app can see."""
    return graph.debug()


@router.get("/lead-debug")
def lead_debug(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Lead Tracker structure + detected columns (to calibrate parsing)."""
    return trackers.lead_debug()


@router.get("/activity-debug")
def activity_debug(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Activity Tracker structure + detected columns (to calibrate parsing)."""
    return trackers.activity_debug()


@router.get("/holiday-debug")
def holiday_debug(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Holiday Tracker structure + detected day-row (to calibrate parsing)."""
    return trackers.holiday_debug()


# ---- targets admin ----
@router.get("/targets")
def list_targets(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    users = [{"id": u.id, "name": u.name, "jobTitle": u.job_title,
              "role": role_for_user(db, u)}
             for u in db.query(User).filter(User.active.is_(True)).order_by(User.name).all()]
    return {"targets": get_all_targets(db), "users": users}


@router.put("/targets")
def update_targets(body: dict, db: Session = Depends(get_db),
                   admin: User = Depends(require_admin)):
    return save_targets(db, body.get("byTitle"), body.get("reps"))
