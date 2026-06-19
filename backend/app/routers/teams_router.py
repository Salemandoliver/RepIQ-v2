"""CallIQ Agent ingestion — receives Teams (or any) call recordings from the local
recording agent and queues them for the normal Deepgram + Claude pipeline.

Contract (matches the local agent):
  POST /api/recordings/upload   (multipart/form-data)
    headers: X-Api-Key: <settings.recordings_api_key>
    fields : file        — the audio (wav/mp3/m4a/mp4/ogg/webm)
             repId       — the rep's email (looked up in the users table)
             recordedAt  — ISO-8601 timestamp (optional; defaults to now)
  -> 202 {"id": <call_id>, "status": "queued"}

The worker picks up any Call with status='queued' + an audio_path within seconds.
"""
import logging
import os
import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Call, User

log = logging.getLogger("calliq.teams")
router = APIRouter(prefix="/api/recordings", tags=["teams-recordings"])

# Formats Deepgram accepts AND that the transcriber maps to a Content-Type. The saved file
# MUST keep its real extension, because transcriber.py derives the Deepgram Content-Type from
# it — saving an .mp4 as .wav would send the wrong type and break transcription.
ALLOWED_EXTS = {"wav", "mp3", "m4a", "mp4", "ogg", "webm"}


def verify_api_key(x_api_key: str = Header(default="")):
    if not settings.recordings_api_key:
        raise HTTPException(503, "Recordings endpoint not configured")
    if x_api_key != settings.recordings_api_key:
        raise HTTPException(401, "Unauthorised")


def _safe_ext(filename: str | None, content_type: str | None) -> str:
    """Pick a sane, allowed extension from the upload's filename, falling back to its
    content-type, then to wav."""
    ext = ""
    if filename and "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()
        ext = re.sub(r"[^a-z0-9]", "", ext)
    if ext not in ALLOWED_EXTS:
        ct = (content_type or "").lower()
        ext = {"audio/wav": "wav", "audio/x-wav": "wav", "audio/mpeg": "mp3",
               "audio/mp4": "m4a", "video/mp4": "mp4", "audio/ogg": "ogg",
               "audio/webm": "webm", "video/webm": "webm"}.get(ct, "")
    return ext if ext in ALLOWED_EXTS else "wav"


@router.post("/upload", status_code=202)
async def upload_teams_recording(
    file: UploadFile = File(...),
    repId: str = Form(...),
    recordedAt: str | None = Form(None),
    db: Session = Depends(get_db),
    _: None = Depends(verify_api_key),
):
    user = db.query(User).filter(User.email == (repId or "").strip().lower()).first()
    if not user:
        log.warning("Teams upload: no user found for repId=%s (queuing unassigned)", repId)

    started_at = datetime.utcnow()
    if recordedAt:
        try:
            started_at = datetime.fromisoformat(recordedAt.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            log.warning("Teams upload: bad recordedAt=%r, using now()", recordedAt)

    os.makedirs(settings.audio_dir, exist_ok=True)
    ext = _safe_ext(file.filename, file.content_type)
    audio_path = os.path.join(settings.audio_dir, f"teams_{uuid.uuid4().hex}.{ext}")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    with open(audio_path, "wb") as f:
        f.write(data)

    call = Call(
        host_id=user.id if user else None,
        direction="outbound", activity_type="Teams Call",
        from_number="", to_number="",
        customer_name="Teams Call", customer_company="",
        started_at=started_at, duration_sec=0,
        audio_path=audio_path, status="queued",
    )
    db.add(call)
    db.commit()
    db.refresh(call)
    log.info("Queued Teams call id=%s rep=%s (%s, %d bytes)", call.id, repId, ext, len(data))
    return {"id": call.id, "status": "queued"}
