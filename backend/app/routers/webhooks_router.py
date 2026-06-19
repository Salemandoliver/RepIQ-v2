"""RingCentral webhook receiver.

Subscription flow:
1. We create a webhook subscription on RingCentral for telephony/recording events
   (see pipeline/ringcentral.py setup_subscription()).
2. RingCentral validates the endpoint with a Validation-Token header — we must echo it back.
3. On each completed recorded call, RingCentral POSTs an event; we enqueue a Call row
   with status='queued'; the worker picks it up, downloads audio, transcribes and analyses.
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Call, User

log = logging.getLogger("calliq.webhooks")
router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/ringcentral")
async def ringcentral_webhook(request: Request, db: Session = Depends(get_db)):
    # Endpoint validation handshake
    vt = request.headers.get("Validation-Token")
    if vt:
        return Response(headers={"Validation-Token": vt})

    payload = await request.json()
    body = payload.get("body", {})
    session_id = body.get("sessionId") or body.get("telephonySessionId")
    if not session_id:
        return {"ok": True, "ignored": True}

    # Pull the monitored party (one with an extension) + any recording id + call state.
    parties = body.get("parties", [])
    recording_id, ext_id = None, None
    direction, from_num, to_num, status_code, missed = "outbound", "", "", "", False
    for p in parties:
        recs = p.get("recordings") or []
        if recs and not recording_id:
            recording_id = str(recs[0].get("id") or "")
        if p.get("extensionId"):
            ext_id = str(p["extensionId"])
            direction = (p.get("direction") or "outbound").lower()
            from_num = (p.get("from") or {}).get("phoneNumber", "")
            to_num = (p.get("to") or {}).get("phoneNumber", "")
            status_code = ((p.get("status") or {}).get("code") or "")
            missed = bool(p.get("missedCall"))
    if not recording_id:
        top = body.get("recordings") or []
        if top:
            recording_id = str(top[0].get("id") or "")

    existing = db.query(Call).filter(Call.rc_session_id == str(session_id)).first()

    # ---- A recording is now available: attach it and queue for processing ----
    if recording_id:
        if existing:
            changed = False
            if not existing.rc_recording_id:
                existing.rc_recording_id = recording_id
                changed = True
            if existing.status in ("awaiting_recording", "no_recording"):
                existing.status, existing.error = "queued", None
                changed = True
            if changed:
                db.commit()
            return {"ok": True, "call_id": existing.id, "queued": changed}
        host = db.query(User).filter(User.rc_extension_id == ext_id).first() if ext_id else None
        call = Call(
            host_id=host.id if host else None,
            direction="outbound" if direction.startswith("out") else "inbound",
            activity_type=("Outbound - Acquisition" if direction.startswith("out")
                           else "Inbound - Call From Customer"),
            from_number=from_num, to_number=to_num,
            started_at=datetime.utcnow(), status="queued",
            rc_session_id=str(session_id), rc_recording_id=recording_id,
        )
        db.add(call)
        db.commit()
        return {"ok": True, "call_id": call.id}

    # ---- No recording yet ----
    if existing:
        return {"ok": True, "noop": True}              # already tracked
    # Show the call the moment it's answered (real conversations only — this naturally
    # skips ringing, no-answer and missed dials, which never reach "Answered").
    if status_code in ("Answered", "Connected") and not missed:
        host = db.query(User).filter(User.rc_extension_id == ext_id).first() if ext_id else None
        call = Call(
            host_id=host.id if host else None,
            direction="outbound" if direction.startswith("out") else "inbound",
            activity_type=("Outbound - Acquisition" if direction.startswith("out")
                           else "Inbound - Call From Customer"),
            from_number=from_num, to_number=to_num,
            started_at=datetime.utcnow(), status="awaiting_recording",
            rc_session_id=str(session_id),
        )
        db.add(call)
        db.commit()
        return {"ok": True, "placeholder": call.id}
    return {"ok": True, "ignored": True}
