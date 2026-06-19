"""Call library: list with rich filters, detail, audio streaming, comments, listen events."""
import os
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import or_, func, distinct
from sqlalchemy.orm import Session, joinedload

from ..auth import get_current_user
from ..config import settings
from ..db import get_db
from ..models import (Call, User, TranscriptTurn, CallScore, CallTopic, Comment,
                      ListenEvent, SavedSearch)
from ..schemas import (CallPage, CallDetail, CommentCreate, CommentOut,
                       SavedSearchIn, SavedSearchOut)
from ..serializers import to_list_item, to_detail

router = APIRouter(prefix="/api/calls", tags=["calls"])


def _apply_filters(q, db: Session,
                   team_id=None, host_id=None, activity_type=None, direction=None,
                   transcript=None, said_by=None, topic_id=None, customer=None,
                   min_minutes=None, max_minutes=None, min_score=None, max_score=None,
                   period_days=None, date_from=None, date_to=None, status=None):
    if team_id:
        q = q.join(User, Call.host_id == User.id).filter(User.team_id == team_id)
    if host_id:
        q = q.filter(Call.host_id == host_id)
    if activity_type:
        q = q.filter(Call.activity_type == activity_type)
    if direction:
        q = q.filter(Call.direction == direction)
    if status:
        q = q.filter(Call.status == status)
    if customer:
        like = f"%{customer}%"
        q = q.filter(or_(Call.customer_name.ilike(like), Call.from_number.ilike(like),
                         Call.to_number.ilike(like), Call.customer_company.ilike(like)))
    if transcript:
        sub = db.query(distinct(TranscriptTurn.call_id)).filter(
            TranscriptTurn.text.ilike(f"%{transcript}%"))
        if said_by in ("rep", "customer"):
            sub = sub.filter(TranscriptTurn.speaker == said_by)
        q = q.filter(Call.id.in_(sub))
    if topic_id:
        q = q.filter(Call.id.in_(db.query(distinct(CallTopic.call_id))
                                 .filter(CallTopic.topic_id == topic_id)))
    if min_minutes is not None:
        q = q.filter(Call.duration_sec >= min_minutes * 60)
    if max_minutes is not None:
        q = q.filter(Call.duration_sec <= max_minutes * 60)
    if min_score is not None or max_score is not None:
        sq = db.query(CallScore.call_id, func.avg(CallScore.overall).label("avg")) \
               .group_by(CallScore.call_id).subquery()
        q = q.join(sq, sq.c.call_id == Call.id)
        if min_score is not None:
            q = q.filter(sq.c.avg >= min_score)
        if max_score is not None:
            q = q.filter(sq.c.avg <= max_score)
    if period_days:
        q = q.filter(Call.started_at >= datetime.utcnow() - timedelta(days=period_days))
    if date_from:
        q = q.filter(Call.started_at >= date_from)
    if date_to:
        q = q.filter(Call.started_at <= date_to)
    # Hide dead / no-answer dials (too short to hold a conversation) from all listings —
    # a real call shows once it has a recording with actual duration.
    q = q.filter(Call.duration_sec >= settings.min_call_seconds)
    return q


@router.get("", response_model=CallPage)
def list_calls(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    page: int = 1,
    page_size: int = Query(20, le=100),
    sort: str = "recent",            # recent | duration | score | plays
    mine: bool = False,
    team_id: int | None = None,
    host_id: int | None = None,
    activity_type: str | None = None,
    direction: str | None = None,
    transcript: str | None = None,
    said_by: str | None = None,      # rep | customer
    topic_id: int | None = None,
    customer: str | None = None,
    min_minutes: float | None = None,
    max_minutes: float | None = None,
    min_score: float | None = None,
    max_score: float | None = None,
    period_days: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    status: str | None = None,
):
    q = db.query(Call).options(joinedload(Call.host), joinedload(Call.topics),
                               joinedload(Call.scores))
    if mine:
        host_id = user.id
    q = _apply_filters(q, db, team_id, host_id, activity_type, direction, transcript,
                       said_by, topic_id, customer, min_minutes, max_minutes,
                       min_score, max_score, period_days, date_from, date_to, status)
    total = q.count()
    order = {"recent": Call.started_at.desc(), "duration": Call.duration_sec.desc(),
             "plays": Call.plays.desc()}.get(sort, Call.started_at.desc())
    items = q.order_by(order).offset((page - 1) * page_size).limit(page_size).all()
    from ..serializers import contact_number, contact_call_counts
    counts = contact_call_counts(db, {contact_number(c) for c in items})
    return CallPage(items=[to_list_item(db, c, contact_calls=counts.get(contact_number(c)))
                           for c in items],
                    total=total, page=page, page_size=page_size)


@router.get("/trending")
def trending(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Most-listened calls in the last 30 days."""
    since = datetime.utcnow() - timedelta(days=30)
    rows = (db.query(ListenEvent.call_id, func.count(ListenEvent.id).label("n"))
            .filter(ListenEvent.listened_at >= since)
            .group_by(ListenEvent.call_id).order_by(func.count(ListenEvent.id).desc())
            .limit(10).all())
    out = []
    for call_id, n in rows:
        call = db.get(Call, call_id)
        if call:
            item = to_list_item(db, call).model_dump()
            item["times_played"] = n
            out.append(item)
    return out


@router.get("/calliq-picks")
def calliq_picks(db: Session = Depends(get_db), user: User = Depends(get_current_user),
                 limit: int = 5):
    """CallIQ Calls of the Month: the month's highest-quality SPIN calls.

    Always prefers calls scored against the SPIN Selling playbook; falls back to the
    best overall-scored calls if no SPIN playbook exists yet. Re-evaluated on every
    request, so new high-quality calls surface automatically as they come in.
    """
    from ..models import Playbook
    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)

    spin = (db.query(Playbook)
            .filter(func.lower(Playbook.name).like("%spin%")).first())

    def _rows(playbook_id):
        q = (db.query(CallScore.call_id, CallScore.overall)
             .join(Call, Call.id == CallScore.call_id)
             .filter(Call.started_at >= month_start, Call.status == "completed"))
        if playbook_id:
            q = q.filter(CallScore.playbook_id == playbook_id)
        return q.order_by(CallScore.overall.desc(), Call.started_at.desc()).limit(limit).all()

    rows = _rows(spin.id) if spin else []
    if not rows:  # no SPIN scores this month — fall back to best overall calls
        rows = _rows(None)

    out, seen = [], set()
    for call_id, overall in rows:
        if call_id in seen:
            continue
        seen.add(call_id)
        call = db.get(Call, call_id)
        if call:
            item = to_list_item(db, call).model_dump()
            item["spin_score"] = round(overall, 1)
            item["is_spin"] = bool(spin)
            out.append(item)
    return out


@router.get("/live-feed")
def live_feed(db: Session = Depends(get_db), user: User = Depends(get_current_user),
              limit: int = 25):
    events = (db.query(ListenEvent).options(joinedload(ListenEvent.user),
                                            joinedload(ListenEvent.call))
              .order_by(ListenEvent.listened_at.desc()).limit(limit).all())
    return [{
        "id": e.id,
        "user": {"id": e.user.id, "name": e.user.name, "avatar_color": e.user.avatar_color},
        "listened_at": e.listened_at,
        "call": to_list_item(db, e.call).model_dump(),
    } for e in events]


@router.get("/ask-presets")
def ask_presets(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..models import AskPreset
    return [{"id": p.id, "name": p.name, "prompt": p.prompt} for p in
            db.query(AskPreset).order_by(AskPreset.position, AskPreset.id).all()]


@router.post("/{call_id}/ask")
def ask_call(call_id: int, body: dict, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    """Ask CallIQ: answer a free-form question about this call from its transcript."""
    from ..config import settings
    question = (body.get("question") or "").strip()
    if not question:
        raise HTTPException(400, "Question is required")
    if not settings.anthropic_api_key:
        raise HTTPException(503, "AI is not configured (no Anthropic API key)")
    call = db.query(Call).options(joinedload(Call.turns), joinedload(Call.host),
                                  joinedload(Call.analysis)).filter(Call.id == call_id).first()
    if not call:
        raise HTTPException(404, "Call not found")
    if not call.turns:
        raise HTTPException(409, "This call has no transcript yet — it may still be processing")
    turns = [{"speaker": t.speaker, "start_sec": t.start_sec, "end_sec": t.end_sec,
              "text": t.text} for t in call.turns]
    rep_name = call.host.name if call.host else "Rep"
    ctx = (f"{call.activity_type}, {call.direction}, {call.duration_sec // 60}m"
           f"{call.duration_sec % 60}s, held {call.started_at:%d %b %Y %H:%M}")
    if call.analysis and call.analysis.summary_intro:
        ctx += f". AI summary: {call.analysis.summary_intro}"
    from ..pipeline.analyzer import ask_about_call
    try:
        answer = ask_about_call(turns, rep_name, question, ctx)
    except Exception as e:
        raise HTTPException(502, f"AI request failed: {str(e)[:200]}")
    return {"answer": answer}


@router.get("/{call_id}", response_model=CallDetail)
def get_call(call_id: int, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    call = db.query(Call).options(
        joinedload(Call.host), joinedload(Call.turns), joinedload(Call.analysis),
        joinedload(Call.scores), joinedload(Call.topics)).filter(Call.id == call_id).first()
    if not call:
        raise HTTPException(404, "Call not found")
    return to_detail(db, call)


@router.get("/{call_id}/audio")
def get_audio(call_id: int, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    call = db.get(Call, call_id)
    if not call:
        raise HTTPException(404, "Audio not available")
    # Audio may have been trimmed off disk to save space — re-download on demand from
    # RingCentral (we keep the recording id) so playback still works.
    if (not call.audio_path or not os.path.exists(call.audio_path)) and call.rc_recording_id \
            and not call.rc_recording_id.startswith("ms:"):
        try:
            from ..pipeline.ringcentral import RingCentralClient
            call.audio_path = RingCentralClient().download_recording(
                call.rc_recording_id, settings.audio_dir)
            db.commit()
        except Exception:
            pass
    if not call.audio_path or not os.path.exists(call.audio_path):
        raise HTTPException(404, "Audio not available")
    return FileResponse(call.audio_path, media_type="audio/mpeg")


@router.post("/{call_id}/listen")
def record_listen(call_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    call = db.get(Call, call_id)
    if not call:
        raise HTTPException(404, "Call not found")
    db.add(ListenEvent(user_id=user.id, call_id=call_id))
    call.plays += 1
    db.commit()
    return {"ok": True, "plays": call.plays}


@router.post("/{call_id}/like")
def like(call_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    call = db.get(Call, call_id)
    if not call:
        raise HTTPException(404, "Call not found")
    call.likes += 1
    db.commit()
    return {"ok": True, "likes": call.likes}


@router.get("/{call_id}/comments", response_model=list[CommentOut])
def list_comments(call_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    return [CommentOut.model_validate(c) for c in
            db.query(Comment).options(joinedload(Comment.user))
            .filter(Comment.call_id == call_id).order_by(Comment.created_at).all()]


@router.post("/{call_id}/comments", response_model=CommentOut)
def add_comment(call_id: int, body: CommentCreate, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    if not db.get(Call, call_id):
        raise HTTPException(404, "Call not found")
    c = Comment(call_id=call_id, user_id=user.id, body=body.body, at_sec=body.at_sec)
    db.add(c)
    db.commit()
    db.refresh(c)
    return CommentOut.model_validate(c)


# ---- saved searches ----
@router.get("/saved-searches/mine", response_model=list[SavedSearchOut])
def my_saved_searches(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [SavedSearchOut.model_validate(s) for s in
            db.query(SavedSearch).filter(SavedSearch.user_id == user.id).all()]


@router.post("/saved-searches", response_model=SavedSearchOut)
def save_search(body: SavedSearchIn, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    s = SavedSearch(user_id=user.id, name=body.name, params=body.params)
    db.add(s)
    db.commit()
    db.refresh(s)
    return SavedSearchOut.model_validate(s)


@router.delete("/saved-searches/{search_id}")
def delete_search(search_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    s = db.get(SavedSearch, search_id)
    if s and s.user_id == user.id:
        db.delete(s)
        db.commit()
    return {"ok": True}
