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


@router.get("/league")
def league(days: int = 30, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Team league table (managers/admin) — reps ranked by call quality + orders, with most-improved."""
    if not _is_manager(db, user):
        raise HTTPException(403, "Manager view only")
    from ..services.intelligence.benchmarks import league as _league
    data = _league(db, days=max(7, min(120, days)))
    # Forecast-reliability lens — attach each rep's score (BCs don't forecast, so they're skipped).
    try:
        from ..modules.forecast import services as _fc
        for r in data.get("reps", []):
            if r.get("group") == "business_creators":
                continue
            u = db.get(User, r["userId"])
            if u and _fc.is_rep(db, u):
                rel = _fc.reliability(db, u)
                r["reliabilityScore"] = rel.get("score")
                r["reliabilityBand"] = rel.get("band")
                r["reliabilityWeeks"] = rel.get("weeks")
    except Exception:
        pass
    return data


@router.get("/insights")
def insights(scope: str | None = None, subject_id: int | None = None, status: str = "open",
             db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The insight feed. Reps see their own; managers/admin see everything (optionally filtered)."""
    from ..services.intelligence.insights import list_for, to_dict
    rows = list_for(db, user, _is_manager(db, user), scope=scope, subject_id=subject_id, status=status)
    return {"insights": [to_dict(i) for i in rows]}


@router.post("/insights/generate")
def insights_generate(body: dict | None = None, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """Regenerate the insight feed now (managers/admin). Runs automatically each morning too."""
    if not _is_manager(db, user):
        raise HTTPException(403, "Managers only")
    from ..services.intelligence.insights import generate
    days = int((body or {}).get("days", 30))
    try:
        return generate(db, days=max(7, min(120, days)), polish=bool((body or {}).get("polish", True)))
    except Exception as e:
        db.rollback()
        import logging
        logging.getLogger("calliq").exception("insight generation failed")
        raise HTTPException(500, f"Generation failed: {e}")


@router.get("/one-to-one/{user_id}")
def one_to_one(user_id: int, days: int = 30, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """Auto-generated 1-to-1 prep brief for a rep (managers/admin, or the rep themselves)."""
    if user_id != user.id and not _is_manager(db, user):
        raise HTTPException(403, "Not permitted")
    from ..services.intelligence.one_to_one import brief
    try:
        return brief(db, user_id, days=max(7, min(120, days)))
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/insights/{insight_id}/feedback")
def insight_feedback(insight_id: int, body: dict, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """Acknowledge / mark actioned / dismiss / rate an insight. Teaches the engine (dismissals stick)."""
    from ..models import Insight
    from ..services.intelligence.insights import apply_feedback, to_dict
    i = db.get(Insight, insight_id)
    if not i:
        raise HTTPException(404, "Insight not found")
    if not _is_manager(db, user) and not (i.scope == "rep" and i.subject_id == user.id):
        raise HTTPException(403, "Not permitted")
    b = body or {}
    return to_dict(apply_feedback(db, i, user, b.get("status"), b.get("feedback"), b.get("note")))


@router.post("/oracle")
def oracle(body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The Org Oracle — cross-rep, org-wide questions (managers/admin). Reasons over the skill table,
    insights, mined knowledge and the most relevant calls."""
    if not _is_manager(db, user):
        raise HTTPException(403, "The Oracle is for managers/admin")
    q = ((body or {}).get("question") or "").strip()
    if not q:
        raise HTTPException(400, "Ask the Oracle a question")
    from ..services.intelligence.oracle import ask_oracle
    return ask_oracle(db, user, q)


@router.get("/knowledge")
def knowledge_list(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The knowledge + exemplar library (what works, pinned great moments)."""
    from ..models import KnowledgeEntry
    rows = (db.query(KnowledgeEntry).filter(KnowledgeEntry.active.is_(True))
            .order_by(KnowledgeEntry.pinned.desc(), KnowledgeEntry.created_at.desc()).all())
    return {"entries": [{"id": e.id, "kind": e.kind, "title": e.title, "body": e.body,
                         "tags": e.tags or [], "evidence": e.evidence or [], "callId": e.call_id,
                         "pinned": e.pinned} for e in rows]}


@router.post("/knowledge")
def knowledge_add(body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Add a manager note to the knowledge library (managers/admin)."""
    if not _is_manager(db, user):
        raise HTTPException(403, "Managers only")
    from ..models import KnowledgeEntry
    if not (body.get("title") or "").strip():
        raise HTTPException(400, "Title required")
    e = KnowledgeEntry(kind=body.get("kind", "note"), title=body["title"].strip(),
                       body=body.get("body", ""), tags=body.get("tags") or [],
                       pinned=bool(body.get("pinned")), created_by=user.id, active=True)
    db.add(e)
    db.commit()
    return {"id": e.id}


@router.delete("/knowledge/{entry_id}")
def knowledge_delete(entry_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not _is_manager(db, user):
        raise HTTPException(403, "Managers only")
    from ..models import KnowledgeEntry
    e = db.get(KnowledgeEntry, entry_id)
    if e:
        e.active = False
        db.commit()
    return {"ok": True}


@router.post("/mine")
def mine_what_works(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Refresh the mined 'what works' patterns + auto-exemplars (managers/admin)."""
    if not _is_manager(db, user):
        raise HTTPException(403, "Managers only")
    from ..services.intelligence.whatworks import auto_exemplars, mine
    try:
        res = mine(db)
        res["exemplars"] = auto_exemplars(db)
        return res
    except Exception as e:
        db.rollback()
        import logging
        logging.getLogger("calliq").exception("mining failed")
        raise HTTPException(500, f"Mining failed: {e}")


@router.get("/team")
def team(team: str | None = None, db: Session = Depends(get_db),
         user: User = Depends(get_current_user)):
    """Manager Team Command Centre (managers/admin only)."""
    if not _is_manager(db, user):
        raise HTTPException(403, "The command centre is for managers only")
    return command_centre(db, user, team=team)


@router.post("/deals/highlight")
def highlight_deal(body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Manager cycles a deal through Highlight → Actioning → Actioned — shared with every manager,
    stamped with who. Tri-state via `status` ("actioning"/"actioned"); anything else clears it.
    Back-compatible with older clients that send `actioned` as a boolean."""
    if not _is_manager(db, user):
        raise HTTPException(403, "Managers only")
    from datetime import datetime as _dt
    from ..models import DealHighlight
    key = (body.get("dealKey") or "").strip()
    if not key:
        raise HTTPException(400, "dealKey required")
    if "status" in body:
        status = body.get("status")
        status = status if status in ("actioning", "actioned") else None
    else:  # legacy boolean toggle
        status = "actioning" if bool(body.get("actioned", True)) else None
    row = db.query(DealHighlight).filter(DealHighlight.deal_key == key).first()
    if status:
        if not row:
            row = DealHighlight(deal_key=key)
            db.add(row)
        row.actioned = True
        row.status = status
        row.actioned_by_id = user.id
        row.actioned_by_name = user.short_name or user.name
        row.actioned_at = _dt.utcnow()
        row.company = body.get("company") or row.company
        row.rep_name = body.get("rep") or row.rep_name
    elif row:
        db.delete(row)
    db.commit()
    return {"ok": True, "status": status, "actioned": bool(status),
            "actionedBy": (user.short_name or user.name) if status else None}


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


@router.get("/video/review")
def my_review(user_id: int | None = None, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    """The latest monthly/quarterly REVIEW for the signed-in rep (or, for a manager, any user_id)."""
    from ..services.intelligence.videos import latest_review, refresh_video, video_payload
    target = user
    if user_id and user_id != user.id:
        if not _is_manager(db, user):
            raise HTTPException(403, "Managers only")
        target = db.get(User, user_id) or user
    v = latest_review(db, target)
    if not v:
        return {"hasReview": False}
    try:
        refresh_video(db, v)
    except Exception:
        pass
    return {"hasReview": True, **video_payload(v)}


@router.post("/video/review/generate")
def generate_one_review(body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Manager: generate ONE rep's monthly (or quarterly) review on demand — for testing without
    waiting for the first Monday. Regenerates if it already exists."""
    if not _is_manager(db, user):
        raise HTTPException(403, "Managers only")
    from ..services.intelligence.videos import ensure_review_video, refresh_video, video_payload
    target = db.get(User, body.get("userId")) if body.get("userId") else user
    if not target:
        raise HTTPException(404, "User not found")
    period = "quarter" if (body.get("period") == "quarter") else "month"
    try:
        v = ensure_review_video(db, target, period, regenerate=True)
        try:
            refresh_video(db, v)
        except Exception:
            pass
        return {"ok": True, **video_payload(v)}
    except Exception as e:
        db.rollback()
        import logging
        logging.getLogger("calliq").exception("single review generate failed")
        raise HTTPException(500, str(e)[:300])


@router.post("/video/generate-reviews")
def generate_reviews_ep(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Manager/admin: pre-generate the monthly (and quarterly when due) reviews for all reps/BCs."""
    if not _is_manager(db, user):
        raise HTTPException(403, "Managers only")
    from ..services.intelligence.videos import generate_all_reviews
    try:
        return generate_all_reviews(db)
    except Exception as e:
        db.rollback()
        import logging
        logging.getLogger("calliq").exception("generate-reviews failed")
        return {"generated": 0, "errors": [str(e)[:300]]}


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
