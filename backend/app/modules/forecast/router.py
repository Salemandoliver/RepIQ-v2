"""Weekly Forecast API.

Phase 2 = rep-facing endpoints (view my forecast + live achievement, submit it, and a lightweight
"do I still need to submit?" status that drives the 11am reminder). Manager endpoints (team view,
edit/unlock, missing list, reliability) are added in Phase 3.

Access: only Sales Reps can submit; everyone sees only their own forecast here.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...auth import get_current_user
from ...db import get_db
from ...models import User
from ...services.salesiq.roles import role_for_user
from . import services as svc

router = APIRouter(prefix="/api/forecast", tags=["forecast"])


def _current() -> tuple[int, int]:
    w = svc.current_week()
    return w["week_year"], w["number"]


def _is_manager(db: Session, user: User) -> bool:
    return user.role == "admin" or role_for_user(db, user) == "manager"


def _week_from(week_year: int | None, week_number: int | None) -> tuple[int, int]:
    if week_year and week_number:
        return week_year, week_number
    return _current()


@router.get("/me")
def my_forecast(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """This week's forecast + live achievement for the signed-in rep. BCs/managers get isRep=False."""
    if not svc.is_rep(db, user):
        return {"isRep": False}
    wy, wn = _current()
    fc = svc.get_forecast(db, user.id, wy, wn)
    return {
        "isRep": True,
        "week": svc.current_week()["label"],
        "forecast": svc.forecast_to_dict(fc),
        "achievement": svc.compute_achievement(db, user, wy, wn),
        "reliability": svc.reliability(db, user),
        "needsSubmit": not (fc and fc.submitted_at),
    }


@router.post("/me")
def submit_my_forecast(body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Rep submits this week's forecast. It locks after submitting — only a manager can change it."""
    if not svc.is_rep(db, user):
        raise HTTPException(403, "Only Sales Reps submit a weekly forecast.")
    try:
        data = float(body.get("data") or 0)
        cloud = float(body.get("cloud") or 0)
        mobile = float(body.get("mobile") or 0)
    except (TypeError, ValueError):
        raise HTTPException(400, "Forecast values must be numbers.")
    if min(data, cloud, mobile) < 0:
        raise HTTPException(400, "Forecast values can't be negative.")
    wy, wn = _current()
    try:
        fc = svc.submit_forecast(db, user, wy, wn, data, cloud, mobile)
    except PermissionError as e:
        raise HTTPException(409, str(e))
    return {"ok": True, "forecast": svc.forecast_to_dict(fc),
            "achievement": svc.compute_achievement(db, user, wy, wn)}


@router.get("/status")
def status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Drives the reminder: does this rep still need to enter a forecast this week? Reps on leave
    today are never nagged."""
    if not svc.is_rep(db, user):
        return {"isRep": False, "needsForecast": False}
    wy, wn = _current()
    fc = svc.get_forecast(db, user.id, wy, wn)
    on_leave = user.id in svc.leave_user_ids(db, date.today())
    return {
        "isRep": True,
        "week": svc.current_week()["label"],
        "submitted": bool(fc and fc.submitted_at),
        "onLeave": on_leave,
        "needsForecast": (not (fc and fc.submitted_at)) and not on_leave,
    }


# ===================================================================== manager endpoints
@router.get("/team")
def team(week_year: int | None = None, week_number: int | None = None, team: str | None = None,
         db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Team forecast vs actual (totals + per-rep + reliability) plus who's still missing a forecast."""
    if not _is_manager(db, user):
        raise HTTPException(403, "Managers only")
    wy, wn = _week_from(week_year, week_number)
    data = svc.team_forecast(db, wy, wn, team)
    data["missing"] = svc.missing_forecasts(db, wy, wn)
    return data


@router.get("/rep/{user_id}")
def rep_forecast(user_id: int, week_year: int | None = None, week_number: int | None = None,
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """One rep's forecast, live achievement, and reliability history. Managers (any rep) or the rep."""
    if not _is_manager(db, user) and user.id != user_id:
        raise HTTPException(403, "Not allowed")
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    wy, wn = _week_from(week_year, week_number)
    fc = svc.get_forecast(db, user_id, wy, wn)
    return {
        "userId": user_id, "name": target.short_name or target.name,
        "forecast": svc.forecast_to_dict(fc),
        "achievement": svc.compute_achievement(db, target, wy, wn),
        "reliability": svc.reliability(db, target),
        "canEdit": _is_manager(db, user),
    }


@router.put("/rep/{user_id}")
def edit_rep_forecast(user_id: int, body: dict, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """Manager edits / unlocks a rep's forecast (audited)."""
    if not _is_manager(db, user):
        raise HTTPException(403, "Managers only")
    if not db.get(User, user_id):
        raise HTTPException(404, "User not found")
    wy, wn = _week_from(body.get("weekYear"), body.get("weekNumber"))
    def _num(v):
        if v is None or v == "":
            return None
        try:
            return max(0.0, float(v))
        except (TypeError, ValueError):
            raise HTTPException(400, "Forecast values must be numbers.")
    fc = svc.manager_set_forecast(db, user, user_id, wy, wn,
                                  data=_num(body.get("data")), cloud=_num(body.get("cloud")),
                                  mobile=_num(body.get("mobile")),
                                  unlock=bool(body.get("unlock")), note=body.get("note"))
    return {"ok": True, "forecast": svc.forecast_to_dict(fc)}


@router.get("/missing")
def missing(week_year: int | None = None, week_number: int | None = None,
            db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Reps who haven't submitted this week's forecast (leave-excluded)."""
    if not _is_manager(db, user):
        raise HTTPException(403, "Managers only")
    wy, wn = _week_from(week_year, week_number)
    return {"week": svc.current_week()["label"], "missing": svc.missing_forecasts(db, wy, wn)}


@router.get("/reliability/{user_id}")
def rep_reliability(user_id: int, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """A rep's Forecast Reliability Score + component breakdown + weekly history."""
    if not _is_manager(db, user) and user.id != user_id:
        raise HTTPException(403, "Not allowed")
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    return svc.reliability(db, target)
