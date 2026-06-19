"""Org settings: users, teams, topics, playbooks, vocabulary, settings, RingCentral
admin tools, GDPR erasure."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..auth import (require_admin, require_manager, get_current_user, hash_password,
                    unusable_password, new_reset_token)
from ..config import settings as app_settings
from ..db import get_db
from ..models import (User, Team, Topic, Playbook, VocabularyTerm, Setting, Call)
from ..schemas import (UserOut, UserCreate, UserUpdate, UserInvite, TeamOut, TeamCreate,
                       TopicIn, TopicOut, PlaybookIn, PlaybookOut, VocabularyIn)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _setup_link(request: Request, token: str) -> str:
    """Build the public 'set your password' link a manager copies/sends to a user."""
    base = (app_settings.public_base_url or str(request.base_url)).rstrip("/")
    return f"{base}/set-password/{token}"


def _issue_link(user: User, hours: int) -> None:
    user.reset_token = new_reset_token()
    user.reset_token_expires = datetime.utcnow() + timedelta(hours=hours)


# ---- users ----
@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [UserOut.model_validate(u) for u in db.query(User).order_by(User.name).all()]


def _guard_admin_target(actor: User, target_role: str | None):
    """Only admins may create or promote someone to the 'admin' system role."""
    if target_role == "admin" and actor.role != "admin":
        raise HTTPException(403, "Only an admin can grant the admin role")


@router.post("/users", response_model=UserOut)
def create_user(body: UserCreate, db: Session = Depends(get_db),
                actor: User = Depends(require_manager)):
    """Create a user with an initial password set by the manager/admin."""
    if db.query(User).filter(User.email == body.email.lower()).first():
        raise HTTPException(409, "Email already exists")
    _guard_admin_target(actor, body.role)
    u = User(name=body.name, email=body.email.lower(), password_hash=hash_password(body.password),
             role=body.role, job_title=body.job_title, short_name=body.short_name,
             team_id=body.team_id, password_changed_at=datetime.utcnow())
    db.add(u)
    db.commit()
    db.refresh(u)
    return UserOut.model_validate(u)


@router.post("/users/invite")
def invite_user(body: UserInvite, request: Request, db: Session = Depends(get_db),
                actor: User = Depends(require_manager)):
    """Create a user who sets their OWN password via a one-time link. Returns the link to copy
    and send (email delivery can be wired on later)."""
    if db.query(User).filter(User.email == body.email.lower()).first():
        raise HTTPException(409, "Email already exists")
    _guard_admin_target(actor, body.role)
    u = User(name=body.name, email=body.email.lower(), password_hash=unusable_password(),
             role=body.role, job_title=body.job_title, short_name=body.short_name,
             team_id=body.team_id, must_set_password=True, active=True)
    _issue_link(u, app_settings.invite_link_hours)
    db.add(u)
    db.commit()
    db.refresh(u)
    return {"user": UserOut.model_validate(u).model_dump(),
            "link": _setup_link(request, u.reset_token),
            "expires": u.reset_token_expires.isoformat(),
            "mode": "invite"}


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, db: Session = Depends(get_db),
                actor: User = Depends(require_manager)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if u.role == "admin" and actor.role != "admin":
        raise HTTPException(403, "Only an admin can edit an admin account")
    _guard_admin_target(actor, body.role)
    for field in ("name", "role", "job_title", "short_name", "team_id", "active"):
        v = getattr(body, field)
        if v is not None:
            setattr(u, field, v)
    if body.password:
        u.password_hash = hash_password(body.password)
        u.password_changed_at = datetime.utcnow()
        u.must_set_password = False
    db.commit()
    db.refresh(u)
    return UserOut.model_validate(u)


@router.post("/users/{user_id}/reset-link")
def send_reset_link(user_id: int, request: Request, db: Session = Depends(get_db),
                    actor: User = Depends(require_manager)):
    """Generate a fresh 'set a new password' link for a user who forgot theirs."""
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if u.role == "admin" and actor.role != "admin":
        raise HTTPException(403, "Only an admin can reset an admin account")
    if not u.active:
        raise HTTPException(400, "This account is a leaver — reactivate it first")
    _issue_link(u, app_settings.reset_link_hours)
    db.commit()
    return {"link": _setup_link(request, u.reset_token),
            "expires": u.reset_token_expires.isoformat(), "mode": "reset",
            "email": u.email, "name": u.name}


@router.post("/users/{user_id}/leaver", response_model=UserOut)
def mark_leaver(user_id: int, db: Session = Depends(get_db),
                actor: User = Depends(require_manager)):
    """Mark a user as a leaver: they can no longer sign in (existing sessions are rejected on
    their next request), and we record when and by whom."""
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if u.id == actor.id:
        raise HTTPException(400, "You can't make your own account a leaver")
    if u.role == "admin" and actor.role != "admin":
        raise HTTPException(403, "Only an admin can offboard an admin account")
    u.active = False
    u.left_on = datetime.utcnow()
    u.left_by_id = actor.id
    u.reset_token = None
    u.reset_token_expires = None
    db.commit()
    db.refresh(u)
    return UserOut.model_validate(u)


@router.post("/users/{user_id}/reactivate", response_model=UserOut)
def reactivate_user(user_id: int, db: Session = Depends(get_db),
                    actor: User = Depends(require_manager)):
    """Reverse a leaver: re-enable the account. They keep their old password unless a reset
    link is also sent."""
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    u.active = True
    u.left_on = None
    u.left_by_id = None
    db.commit()
    db.refresh(u)
    return UserOut.model_validate(u)


@router.post("/calls/cleanup-dead")
def cleanup_dead_calls(max_seconds: int = 5, db: Session = Depends(get_db),
                       admin: User = Depends(require_admin)):
    """Delete settled calls shorter than max_seconds (no-answer / dead dials with no
    real conversation). Leaves in-flight calls and genuine longer calls untouched."""
    import os
    from ..models import (Call, Comment, ListenEvent, TranscriptTurn, CallAnalysis,
                          CallScore, CallTopic)
    calls = (db.query(Call)
             .filter(Call.duration_sec < max_seconds,
                     Call.status.in_(["failed", "no_recording", "completed"]))
             .all())
    n = 0
    for c in calls:
        for M in (TranscriptTurn, CallAnalysis, CallScore, CallTopic):
            db.query(M).filter(M.call_id == c.id).delete()
        db.query(Comment).filter(Comment.call_id == c.id).delete()
        db.query(ListenEvent).filter(ListenEvent.call_id == c.id).delete()
        if c.audio_path and os.path.exists(c.audio_path):
            try:
                os.remove(c.audio_path)
            except OSError:
                pass
        db.delete(c)
        n += 1
    db.commit()
    return {"deleted": n}


@router.post("/calls/retry-failed")
def retry_failed_calls(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Re-queue every failed call (resets the retry counter) so they reprocess now."""
    from ..models import Call
    n = (db.query(Call).filter(Call.status == "failed")
         .update({Call.status: "queued", Call.process_attempts: 0, Call.error: None},
                 synchronize_session=False))
    db.commit()
    return {"requeued": n}


@router.get("/calls/queue-status")
def calls_queue_status(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Counts of calls by processing status (to watch the pipeline drain) + diagnostics so
    we can see WHY calls aren't completing (recording missing, download error, etc.)."""
    from sqlalchemy import func
    from ..models import Call
    from ..pipeline.worker import worker_heartbeat
    rows = db.query(Call.status, func.count(Call.id)).group_by(Call.status).all()
    counts = {s: n for s, n in rows}

    # Of the calls not yet completed, how many actually have a recording to process?
    pending = db.query(Call).filter(Call.status.in_(["queued", "failed", "awaiting_recording"]))
    no_rec = pending.filter(Call.rc_recording_id.is_(None)).count()
    with_rec = pending.filter(Call.rc_recording_id.isnot(None)).count()

    # Most recent errors (these tell us the real failure reason)
    err_rows = (db.query(Call.id, Call.error, Call.duration_sec, Call.process_attempts,
                         Call.rc_recording_id)
                .filter(Call.error.isnot(None))
                .order_by(Call.id.desc()).limit(8).all())
    recent_errors = [{"id": r[0], "error": (r[1] or "")[:300], "duration": r[2],
                      "attempts": r[3], "has_recording": bool(r[4])} for r in err_rows]

    return {"counts": counts, "worker": worker_heartbeat(),
            "pending_no_recording": no_rec, "pending_with_recording": with_rec,
            "recent_errors": recent_errors}


@router.post("/calls/reprocess-stuck")
def reprocess_stuck_calls(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Re-queue calls stuck mid-processing (e.g. after a worker restart) so they run again."""
    from ..models import Call
    n = (db.query(Call)
         .filter(Call.status.in_(["processing", "downloading", "transcribing", "analyzing"]))
         .update({Call.status: "queued"}, synchronize_session=False))
    db.commit()
    return {"requeued": n}


@router.post("/users/reset-passwords")
def reset_passwords(body: dict, db: Session = Depends(get_db),
                    admin: User = Depends(require_admin)):
    """Set a shared password for all users except admins, the Managing Director, and the
    admin@btlocalbusiness.co.uk account. Password is supplied by the calling admin."""
    pw = (body or {}).get("password") or ""
    if len(pw) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    reset = []
    for u in db.query(User).all():
        if u.role == "admin":
            continue
        if (u.job_title or "").strip().lower() == "managing director":
            continue
        if u.email.lower() == "admin@btlocalbusiness.co.uk":
            continue
        u.password_hash = hash_password(pw)
        reset.append(u.email)
    db.commit()
    return {"reset": len(reset), "emails": reset}


# ---- teams ----
@router.get("/teams", response_model=list[TeamOut])
def list_teams(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [TeamOut.model_validate(t) for t in db.query(Team).order_by(Team.name).all()]


@router.post("/teams", response_model=TeamOut)
def create_team(body: TeamCreate, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    t = Team(name=body.name, owner_id=body.owner_id)
    db.add(t)
    db.commit()
    db.refresh(t)
    return TeamOut.model_validate(t)


@router.delete("/teams/{team_id}")
def delete_team(team_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    t = db.get(Team, team_id)
    if t:
        for u in t.users:
            u.team_id = None
        db.delete(t)
        db.commit()
    return {"ok": True}


# ---- topics ----
@router.get("/topics", response_model=list[TopicOut])
def list_topics(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [TopicOut.model_validate(t) for t in db.query(Topic).order_by(Topic.name).all()]


@router.post("/topics", response_model=TopicOut)
def create_topic(body: TopicIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    t = Topic(name=body.name, keywords=body.keywords, color=body.color, active=body.active)
    db.add(t)
    db.commit()
    db.refresh(t)
    return TopicOut.model_validate(t)


@router.patch("/topics/{topic_id}", response_model=TopicOut)
def update_topic(topic_id: int, body: TopicIn, db: Session = Depends(get_db),
                 admin: User = Depends(require_admin)):
    t = db.get(Topic, topic_id)
    if not t:
        raise HTTPException(404, "Topic not found")
    t.name, t.keywords, t.color, t.active = body.name, body.keywords, body.color, body.active
    db.commit()
    db.refresh(t)
    return TopicOut.model_validate(t)


@router.delete("/topics/{topic_id}")
def delete_topic(topic_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    t = db.get(Topic, topic_id)
    if t:
        db.delete(t)
        db.commit()
    return {"ok": True}


# ---- playbooks ----
@router.get("/playbooks", response_model=list[PlaybookOut])
def list_playbooks(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [PlaybookOut.model_validate(p) for p in db.query(Playbook).order_by(Playbook.name).all()]


@router.post("/playbooks", response_model=PlaybookOut)
def create_playbook(body: PlaybookIn, db: Session = Depends(get_db),
                    admin: User = Depends(require_admin)):
    p = Playbook(**body.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return PlaybookOut.model_validate(p)


@router.patch("/playbooks/{playbook_id}", response_model=PlaybookOut)
def update_playbook(playbook_id: int, body: PlaybookIn, db: Session = Depends(get_db),
                    admin: User = Depends(require_admin)):
    p = db.get(Playbook, playbook_id)
    if not p:
        raise HTTPException(404, "Playbook not found")
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return PlaybookOut.model_validate(p)


@router.delete("/playbooks/{playbook_id}")
def delete_playbook(playbook_id: int, db: Session = Depends(get_db),
                    admin: User = Depends(require_admin)):
    p = db.get(Playbook, playbook_id)
    if p:
        p.active = False
        db.commit()
    return {"ok": True}


# ---- vocabulary ----
@router.get("/vocabulary")
def list_vocab(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [{"id": v.id, "term": v.term} for v in
            db.query(VocabularyTerm).order_by(VocabularyTerm.term).all()]


@router.post("/vocabulary")
def add_vocab(body: VocabularyIn, db: Session = Depends(get_db),
              admin: User = Depends(require_admin)):
    if not db.query(VocabularyTerm).filter(VocabularyTerm.term == body.term).first():
        db.add(VocabularyTerm(term=body.term))
        db.commit()
    return {"ok": True}


@router.delete("/vocabulary/{vocab_id}")
def delete_vocab(vocab_id: int, db: Session = Depends(get_db),
                 admin: User = Depends(require_admin)):
    v = db.get(VocabularyTerm, vocab_id)
    if v:
        db.delete(v)
        db.commit()
    return {"ok": True}


# ---- org settings ----
@router.get("/settings")
def get_settings(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return {s.key: s.value for s in db.query(Setting).all()}


@router.put("/settings/{key}")
def put_setting(key: str, value: dict, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    s = db.get(Setting, key)
    if s:
        s.value = value
    else:
        db.add(Setting(key=key, value=value))
    db.commit()
    return {"ok": True}


# ---- Ask CallIQ presets ----
@router.post("/ask-presets")
def create_ask_preset(body: dict, db: Session = Depends(get_db),
                      admin: User = Depends(require_admin)):
    from ..models import AskPreset
    p = AskPreset(name=(body.get("name") or "").strip(),
                  prompt=(body.get("prompt") or "").strip(),
                  position=int(body.get("position") or 0))
    if not p.name or not p.prompt:
        raise HTTPException(400, "name and prompt are required")
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"id": p.id, "name": p.name, "prompt": p.prompt}


@router.patch("/ask-presets/{preset_id}")
def update_ask_preset(preset_id: int, body: dict, db: Session = Depends(get_db),
                      admin: User = Depends(require_admin)):
    from ..models import AskPreset
    p = db.get(AskPreset, preset_id)
    if not p:
        raise HTTPException(404, "Preset not found")
    if body.get("name"):
        p.name = body["name"].strip()
    if body.get("prompt"):
        p.prompt = body["prompt"].strip()
    if "position" in body:
        p.position = int(body["position"] or 0)
    db.commit()
    return {"id": p.id, "name": p.name, "prompt": p.prompt}


@router.delete("/ask-presets/{preset_id}")
def delete_ask_preset(preset_id: int, db: Session = Depends(get_db),
                      admin: User = Depends(require_admin)):
    from ..models import AskPreset
    p = db.get(AskPreset, preset_id)
    if p:
        db.delete(p)
        db.commit()
    return {"ok": True}


# ---- RingCentral setup: register webhook + backfill from the running app ----
@router.post("/ringcentral/setup")
def ringcentral_setup(webhook_url: str = "", backfill_days: int = 0,
                      db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    from ..pipeline.ringcentral import RingCentralClient, queue_backfill
    out: dict = {}
    if webhook_url:
        sub = RingCentralClient().setup_subscription(webhook_url)
        out["subscription_id"] = sub.get("id")
        out["expires"] = sub.get("expirationTime")
    if backfill_days:
        out["queued_calls"] = queue_backfill(db, backfill_days)
    return out


@router.get("/ringcentral/status")
def ringcentral_status(admin: User = Depends(require_admin)):
    """Check connectivity + list active webhook subscriptions."""
    import httpx as _hx
    from ..pipeline.ringcentral import RingCentralClient
    rc = RingCentralClient()
    try:
        token = rc._auth()
        r = _hx.get(f"{rc.base}/restapi/v1.0/subscription",
                    headers={"Authorization": f"Bearer {token}"}, timeout=30)
        subs = [{"id": s.get("id"), "address": (s.get("deliveryMode") or {}).get("address"),
                 "status": s.get("status"), "expires": s.get("expirationTime")}
                for s in r.json().get("records", [])]
        return {"connected": True, "subscriptions": subs}
    except Exception as e:
        return {"connected": False, "error": str(e)[:300]}


@router.post("/purge-demo-calls")
def purge_demo_calls(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Delete synthetic demo calls (those without a RingCentral session id) and the
    demo weekly reports, leaving real ingested calls untouched."""
    import os as _os
    from ..models import Comment as _C, ListenEvent as _L, Report as _R
    demo_calls = db.query(Call).filter(Call.rc_session_id.is_(None)).all()
    n = 0
    for c in demo_calls:
        if c.audio_path and _os.path.exists(c.audio_path):
            try:
                _os.remove(c.audio_path)
            except OSError:
                pass
        db.query(_C).filter(_C.call_id == c.id).delete()
        db.query(_L).filter(_L.call_id == c.id).delete()
        db.delete(c)
        n += 1
    r = db.query(_R).delete()
    db.commit()
    return {"purged_calls": n, "purged_reports": r}


@router.post("/requeue-failed")
def requeue_failed(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Reset all failed calls to queued so the worker retries them."""
    n = (db.query(Call).filter(Call.status == "failed")
         .update({Call.status: "queued", Call.error: None}, synchronize_session=False))
    db.commit()
    return {"requeued": n}


# ---- GDPR: erase a customer by phone number ----
@router.delete("/gdpr/erase")
def gdpr_erase(phone: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    import os
    # '+' arrives as a space when the query string isn't encoded; normalise
    phone = phone.strip()
    if phone and not phone.startswith("+"):
        phone = "+" + phone
    calls = db.query(Call).filter((Call.from_number == phone) | (Call.to_number == phone)).all()
    n = 0
    from ..models import Comment as _C, ListenEvent as _L
    for c in calls:
        if c.audio_path and os.path.exists(c.audio_path):
            try:
                os.remove(c.audio_path)
            except OSError:
                pass
        db.query(_C).filter(_C.call_id == c.id).delete()
        db.query(_L).filter(_L.call_id == c.id).delete()
        db.delete(c)  # cascades to turns/analysis/scores/topics
        n += 1
    db.commit()
    return {"erased_calls": n}
