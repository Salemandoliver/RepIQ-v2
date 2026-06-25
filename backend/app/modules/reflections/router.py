"""Review Reflection API.

Rep-facing: open the reflection on a review, exchange messages with the presenter (Oliver/Gary),
complete it, and check whether a fresh review is awaiting reflection (drives the Today nudge). Plus a
config-gated TTS endpoint that returns the presenter's spoken reply as audio (ElevenLabs); the
frontend falls back to the browser's own speech synthesis when it isn't configured.

Manager endpoints (view a rep's reflection, team rollup) are added in Phase 3.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ...auth import get_current_user
from ...config import settings
from ...db import get_db
from ...models import PerformanceVideo, User
from ...services.salesiq.roles import role_for_user
from . import dialogue as dlg
from . import services as svc
from .models import ReviewReflection

router = APIRouter(prefix="/api/reflection", tags=["reflections"])


def _is_manager(db: Session, user: User) -> bool:
    return user.role == "admin" or role_for_user(db, user) == "manager"


def _video(db: Session, user: User, video_id: int, allow_manager: bool = False) -> PerformanceVideo:
    v = db.get(PerformanceVideo, video_id)
    if not v:
        raise HTTPException(404, "Review not found")
    if v.user_id != user.id and not allow_manager:
        raise HTTPException(403, "That isn't your review")
    return v


def _reflection(db: Session, user: User, reflection_id: str, allow_manager: bool = False) -> ReviewReflection:
    try:
        key = uuid.UUID(str(reflection_id))
    except (ValueError, TypeError):
        raise HTTPException(404, "Reflection not found")
    r = db.get(ReviewReflection, key)
    if not r:
        raise HTTPException(404, "Reflection not found")
    if r.user_id != user.id and not allow_manager:
        raise HTTPException(403, "Not allowed")
    return r


@router.get("/me/pending")
def my_pending(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Is there a fresh review the signed-in rep hasn't reflected on yet?"""
    return {"pending": svc.pending_reflection(db, user)}


@router.get("/me/status")
def my_status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Rep's reflection standing — pending review + streak/total (drives the Today nudge + streak)."""
    sig = svc.reflection_signal(db, user)
    return {"pending": sig.get("pending"), "streak": sig.get("streak"),
            "totalReflected": sig.get("totalReflected"), "lastReflectedAt": sig.get("lastReflectedAt")}


@router.get("/video/{video_id}")
def for_video(video_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Open (or resume) the reflection for one of the rep's reviews — ensures the presenter's opening
    message exists, then returns the transcript + status."""
    v = _video(db, user, video_id)
    r = svc.get_or_create(db, user, v)
    svc.open_dialogue(db, user, v, r)
    return {"presenter": dlg.presenter_for(v.video_type), "period": dlg.period_for(v.video_type),
            "reflection": svc.to_dict(r)}


@router.post("/{reflection_id}/message")
def send_message(reflection_id: str, body: dict, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """Rep sends a message; returns the presenter's next line + whether the dialogue is complete."""
    r = _reflection(db, user, reflection_id)
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "Message can't be empty.")
    v = db.get(PerformanceVideo, r.video_id)
    out = svc.add_rep_message(db, user, v, r, text)
    return {**out, "reflection": svc.to_dict(r)}


@router.post("/{reflection_id}/complete")
def complete(reflection_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Finalise the reflection now (also happens automatically when the dialogue wraps up)."""
    r = _reflection(db, user, reflection_id)
    v = db.get(PerformanceVideo, r.video_id)
    svc.complete(db, user, v, r)
    return {"reflection": svc.to_dict(r)}


@router.get("/tts")
def tts(text: str, presenter: str = "Oliver", db: Session = Depends(get_db),
        user: User = Depends(get_current_user)):
    """Presenter's spoken reply as audio. 501 when ElevenLabs isn't configured → the frontend uses the
    browser's built-in voice instead."""
    if not settings.elevenlabs_api_key:
        raise HTTPException(501, "Presenter voice not configured")
    voice = (settings.elevenlabs_gary_voice_id if presenter.lower() == "gary"
             else settings.elevenlabs_oliver_voice_id)
    if not voice:
        raise HTTPException(501, "Presenter voice not configured")
    import httpx
    try:
        resp = httpx.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
            headers={"xi-api-key": settings.elevenlabs_api_key, "content-type": "application/json"},
            json={"text": (text or "")[:1500], "model_id": settings.elevenlabs_model_id,
                  "voice_settings": {"stability": 0.4, "similarity_boost": 0.8}},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception:
        raise HTTPException(502, "Voice synthesis failed")
    return Response(content=resp.content, media_type="audio/mpeg")


# ===================================================================== manager endpoints
@router.get("/rep/{user_id}")
def rep_reflections(user_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """A rep's reflections — signal + recent transcripts/summaries (managers, or the rep themselves)."""
    if not _is_manager(db, user) and user.id != user_id:
        raise HTTPException(403, "Not allowed")
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    rows = (db.query(ReviewReflection).filter(ReviewReflection.user_id == user_id)
            .order_by(ReviewReflection.created_at.desc()).limit(12).all())
    return {"userId": user_id, "name": target.short_name or target.name,
            "signal": svc.reflection_signal(db, target),
            "reflections": [svc.to_dict(r, full=True) for r in rows]}


@router.get("/team")
def team(team: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Team-wide reflection rollup — who's reflected, blockers needing help, recurring themes."""
    if not _is_manager(db, user):
        raise HTTPException(403, "Managers only")
    return svc.team_reflection_summary(db, team)
