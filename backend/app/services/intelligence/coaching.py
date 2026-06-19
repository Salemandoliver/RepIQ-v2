"""Feature 2 — Post-Call AI Coaching Card.

Assembles the card from the call's stored analysis (metrics + the analyzer's coaching
block) plus the rep's own 30-day averages as the benchmark. No new LLM call — the coaching
content was produced during pipeline analysis."""
from __future__ import annotations

from ...models import Call, User
from .common import (DNA_BANDS, OUTCOME_LABELS, OUTCOMES, quality_100,
                     rep_averages, _avg_scores)


def _delta(value, avg):
    if value is None or avg is None:
        return None
    return round(value - avg, 1)


def coaching_card(db, call: Call) -> dict:
    a = call.analysis
    host = call.host
    # This call's quality (avg of its playbook scores, 0–100).
    qmap = _avg_scores(db, [call.id])
    quality = quality_100(qmap.get(call.id)) if call.id in qmap else None
    avg = rep_averages(db, call.host_id, days=30, asof=call.started_at,
                       exclude_call_id=call.id) if call.host_id else {}

    talk = a.talk_ratio if a else None
    lo, hi = DNA_BANDS["talk_ratio"]
    talk_note = None
    if talk is not None and talk > hi:
        talk_note = (f"You talked {talk:.0f}% of this call — aim for under {hi}%. "
                     "Prospects who talk more, close more.")
    elif talk is not None and talk < lo:
        talk_note = (f"You talked {talk:.0f}% of this call — a touch low. "
                     "Make sure you're steering the conversation and landing the value.")

    inter = a.interruptions if a else None
    inter_avg = avg.get("interruptions")
    inter_tip = None
    if inter and inter_avg is not None and inter > max(2, inter_avg + 1):
        inter_tip = ("Try letting silence sit after a prospect pauses — they often continue "
                     "with valuable information.")

    qb = (a.question_breakdown if a and a.question_breakdown else {}) or {}
    questions_total = a.question_rate if a else None
    q_note = None
    disc_band_lo = DNA_BANDS["questions"][0]
    if questions_total is not None and questions_total < disc_band_lo:
        q_note = (f"You asked {int(questions_total)} questions on this call. Your strongest "
                  f"calls average {disc_band_lo}–{DNA_BANDS['questions'][1]}.")

    filler = a.filler_count if a else None
    filler_avg = avg.get("filler")
    show_filler = bool(filler and filler_avg is not None and filler > max(5, filler_avg * 1.3))

    bm = (a.best_moment if a and a.best_moment else {}) or {}

    return {
        "callId": call.id,
        "ready": call.status == "completed" and a is not None,
        "status": call.status,
        "header": {
            "company": call.customer_company or call.customer_name or "Unknown",
            "contact": call.customer_name,
            "repName": host.name if host else "Rep",
            "repId": call.host_id,
            "date": call.started_at.isoformat() if call.started_at else None,
            "activityType": call.activity_type,
            "durationSec": call.duration_sec,
            "quality": quality,
            "qualityVsAvg": _delta(quality, avg.get("quality")),
            "repAvgQuality": avg.get("quality"),
        },
        "talkListen": {
            "repPct": talk, "band": list(DNA_BANDS["talk_ratio"]),
            "repAvg": avg.get("talk_ratio"), "note": talk_note,
        },
        "interruptions": {
            "count": inter, "repAvg": inter_avg, "tip": inter_tip,
        },
        "questions": {
            "total": int(questions_total) if questions_total is not None else None,
            "breakdown": {"discovery": qb.get("discovery", 0),
                          "closing": qb.get("closing", 0),
                          "clarifying": qb.get("clarifying", 0)},
            "repAvg": avg.get("questions"), "note": q_note,
        },
        "objections": (a.objections if a and a.objections else []),
        "filler": {"count": filler, "repAvg": filler_avg, "show": show_filler,
                   "instances": []},
        "energyNote": (a.energy_note if a else "") or "",
        "bestMoment": ({"startSec": bm.get("start_sec"), "endSec": bm.get("end_sec"),
                        "quote": bm.get("quote"), "reason": bm.get("reason")}
                       if bm.get("quote") else None),
        "oneThing": (a.one_thing if a else "") or "",
        "strengths": (a.strengths if a and a.strengths else []),
        "improvements": (a.improvements if a and a.improvements else []),
        "outcome": {
            "value": call.outcome,
            "label": OUTCOME_LABELS.get(call.outcome),
            "options": OUTCOMES,
            "note": call.outcome_note,
            "loggedAt": call.outcome_at.isoformat() if call.outcome_at else None,
        },
    }


def log_outcome(db, call: Call, value: str, note: str | None, by_user: User) -> dict:
    from datetime import datetime
    valid = {o["value"] for o in OUTCOMES}
    if value not in valid:
        raise ValueError(f"Unknown outcome '{value}'")
    call.outcome = value
    call.outcome_note = (note or None)
    call.outcome_at = datetime.utcnow()
    call.outcome_by = by_user.id
    db.commit()
    return {"value": value, "label": OUTCOME_LABELS.get(value),
            "loggedAt": call.outcome_at.isoformat()}
