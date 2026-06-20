"""CallIQ Intelligence Layer — Phase 1 endpoints.

Coaching cards, one-tap outcome logging, the rep morning dashboard, and the manager
command centre. Access: reps see their own data; managers/admin see the whole team."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import Call, User
from ..services.intelligence.coaching import coaching_card, log_outcome
from ..services.intelligence.common import OUTCOMES
from ..services.intelligence.daily_plan import ask_copilot, daily_plan
from ..services.intelligence.morning import morning_dashboard
from ..services.intelligence.team import command_centre
from ..services.intelligence.videos import ensure_weekly_video, refresh_video, video_payload
from ..services.salesiq.roles import role_for_user

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])


def _is_manager(db: Session, user: User) -> bool:
    return user.role == "admin" or role_for_user(db, user) == "manager"


def _can_see_call(db: Session, user: User, call: Call) -> bool:
    return call.host_id == user.id or _is_manager(db, user)


@router.get("/outcomes")
def outcomes():
    """The outcome vocabulary for the one-tap logger."""
    return {"outcomes": OUTCOMES}


@router.get("/coaching/{call_id}")
def coaching(call_id: int, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    call = db.get(Call, call_id)
    if not call:
        raise HTTPException(404, "Call not found")
    if not _can_see_call(db, user, call):
        raise HTTPException(403, "Not permitted to view this call")
    return coaching_card(db, call)


@router.post("/calls/{call_id}/outcome")
def set_outcome(call_id: int, body: dict, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    call = db.get(Call, call_id)
    if not call:
        raise HTTPException(404, "Call not found")
    if not _can_see_call(db, user, call):
        raise HTTPException(403, "Not permitted to log an outcome on this call")
    try:
        return log_outcome(db, call, (body or {}).get("outcome", ""),
                           (body or {}).get("note"), user)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/plan")
def plan(user_id: int | None = None, db: Session = Depends(get_db),
         user: User = Depends(get_current_user)):
    """The rep/BC co-pilot daily plan (action-first). Managers may view a rep's via ?user_id=."""
    target = user
    if user_id and user_id != user.id:
        if not _is_manager(db, user):
            raise HTTPException(403, "Not permitted")
        target = db.get(User, user_id)
        if not target:
            raise HTTPException(404, "User not found")
    return daily_plan(db, target)


@router.post("/ask")
def ask(body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Ask CallIQ about your day — yesterday's calls, follow-ups, prospects, your numbers."""
    question = ((body or {}).get("question") or "").strip()
    if not question:
        raise HTTPException(400, "Ask a question")
    scope = ((body or {}).get("scope") or "yesterday").lower()
    if scope not in ("yesterday", "week", "month"):
        scope = "yesterday"
    return {"answer": ask_copilot(db, user, question, scope)}


@router.get("/morning")
def morning(user_id: int | None = None, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    """The viewer's morning dashboard. Managers may request a rep's via ?user_id=."""
    target = user
    if user_id and user_id != user.id:
        if not _is_manager(db, user):
            raise HTTPException(403, "Not permitted to view another user's dashboard")
        target = db.get(User, user_id)
        if not target:
            raise HTTPException(404, "User not found")
    return morning_dashboard(db, target)


@router.get("/benchmarks")
def benchmarks(user_id: int | None = None, weeks: int = 12,
               db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """A rep's call-quality & orders over time vs the team average, plus their rank. Managers may
    request a team member's via ?user_id=."""
    from ..services.intelligence.benchmarks import rep_vs_team
    target = user
    if user_id and user_id != user.id:
        if not _is_manager(db, user):
            raise HTTPException(403, "Not permitted")
        target = db.get(User, user_id)
        if not target:
            raise HTTPException(404, "User not found")
    return rep_vs_team(db, target.id, weeks=max(4, min(26, weeks)))


@router.get("/team")
def team(team: str | None = None, db: Session = Depends(get_db),
         user: User = Depends(get_current_user)):
    """Manager Team Command Centre (managers/admin only)."""
    if not _is_manager(db, user):
        raise HTTPException(403, "The command centre is for managers only")
    return command_centre(db, user, team=team)


def _safe_weekly(db, target: User) -> dict:
    """Never 500 — always return a payload (with the briefing if we have it) so the card shows
    content; carry any error so it can be surfaced for diagnosis."""
    import logging
    try:
        v = ensure_weekly_video(db, target)
    except Exception as e:
        logging.getLogger("calliq").exception("weekly video load failed for user %s", target.id)
        return {"status": "error", "error": str(e)[:400], "script": "", "title": "",
                "headline": "", "weekStart": None, "hasVideo": False, "videoUrl": None}
    try:
        refresh_video(db, v)
    except Exception:
        pass
    return video_payload(v)


@router.get("/video")
def my_weekly_video(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """This week's AI performance video/briefing for the signed-in rep/BC."""
    return _safe_weekly(db, user)


@router.post("/video/generate-all")
def generate_all_videos(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Manager/admin: pre-generate this week's videos for all enabled reps/BCs now (so they
    render in the background instead of on first open). Also runs automatically early Monday."""
    if not _is_manager(db, user):
        raise HTTPException(403, "Managers only")
    from ..services.intelligence.videos import generate_all_weekly
    try:
        return generate_all_weekly(db)            # {"generated": n, "errors": [...]}
    except Exception as e:
        db.rollback()
        import logging
        logging.getLogger("calliq").exception("generate-all failed")
        return {"generated": 0, "errors": [str(e)[:300]]}


@router.get("/videos/status")
def videos_status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """This week's video render status across the team (for the Settings readout)."""
    if not _is_manager(db, user):
        raise HTTPException(403, "Managers only")
    from datetime import datetime, time, date
    from ..models import PerformanceVideo
    from ..services.intelligence.videos import _this_monday, refresh_video
    wk = datetime.combine(_this_monday(date.today()), time.min)
    rows = (db.query(PerformanceVideo)
            .filter(PerformanceVideo.week_start == wk,
                    PerformanceVideo.video_type == "weekly_rep").all())
    counts, items = {}, []
    for v in rows:
        refresh_video(db, v)            # poll any still-rendering ones so the readout is current
        counts[v.status] = counts.get(v.status, 0) + 1
        items.append({"userId": v.user_id, "name": v.user.name if v.user else "?",
                      "status": v.status, "error": v.error})
    return {"weekStart": wk.isoformat(), "total": len(rows), "counts": counts,
            "items": sorted(items, key=lambda x: x["name"])}


@router.get("/video/people")
def video_people(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Rep/BC list for the manager's weekly-video picker."""
    if not _is_manager(db, user):
        raise HTTPException(403, "Managers only")
    from ..services.intelligence.team import _team_reps
    return {"people": [{"id": u.id, "name": u.name, "role": role_for_user(db, u)}
                       for u in _team_reps(db, None)]}


@router.get("/video/{user_id}")
def rep_weekly_video(user_id: int, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """A specific rep/BC's weekly video — the signed-in user's own, or any for a manager."""
    if user_id != user.id and not _is_manager(db, user):
        raise HTTPException(403, "Not permitted")
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    return _safe_weekly(db, target)


@router.get("/scorecard/{user_id}")
def scorecard(user_id: int, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    """Individual rep scorecard drill-down (managers/admin, or the rep themselves)."""
    if user_id != user.id and not _is_manager(db, user):
        raise HTTPException(403, "Not permitted")
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    return morning_dashboard(db, target)
