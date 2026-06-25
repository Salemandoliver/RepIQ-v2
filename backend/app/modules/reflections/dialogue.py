"""The reflection dialogue engine.

- Persona: the same presenter as the review — Oliver (weekly) / Gary (monthly/quarterly) — continues
  the conversation as a warm, curious coach.
- Grounding: each turn is anchored in the rep's actual review (headline + script), their forecast
  standing, and last period's commitments, so questions reference real specifics.
- Turn loop: one question at a time; after ~4-7 exchanges (or once they've reflected well and named
  commitments) it wraps up. Graceful fallback to a fixed short script with no Anthropic key.
- Extraction: on completion, mine the transcript into structured signal, judging self-awareness by
  comparing the rep's self-view to the review's real numbers.

Voice is layered on in the frontend (speech-to-text in, TTS out) — this engine is text in/out, so the
data and intelligence are identical whether the rep spoke or typed.
"""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy.orm import Session

from ...config import settings
from ...models import PerformanceVideo, User
from .models import ReviewReflection

PRESENTER = {"weekly_rep": "Oliver", "monthly_review": "Gary", "quarterly_review": "Gary"}
PERIOD = {"weekly_rep": "weekly", "monthly_review": "monthly", "quarterly_review": "quarterly"}
MAX_EXCHANGES = 7   # presenter questions before it wraps up

_FALLBACK_QS = [
    "What's your honest read on this period — what went well, and what didn't?",
    "What got in the way of the things that didn't go to plan?",
    "What's the one change you'll make next period, and how will you make it stick?",
]


def presenter_for(video_type: str) -> str:
    return PRESENTER.get(video_type, "Oliver")


def period_for(video_type: str) -> str:
    return PERIOD.get(video_type, "weekly")


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def prior_reflection(db: Session, user: User, video: PerformanceVideo) -> ReviewReflection | None:
    """The rep's most recent COMPLETED reflection of the same cadence (for the 'how did last time go?'
    callback that closes the loop)."""
    pt = period_for(video.video_type)
    return (db.query(ReviewReflection)
            .filter(ReviewReflection.user_id == user.id, ReviewReflection.period_type == pt,
                    ReviewReflection.status == "complete", ReviewReflection.video_id != video.id)
            .order_by(ReviewReflection.completed_at.desc()).first())


def _context(db: Session, user: User, video: PerformanceVideo, prior: ReviewReflection | None) -> dict:
    ctx = {"reviewHeadline": video.headline or "", "reviewScript": (video.script or "")[:2500],
           "period": period_for(video.video_type)}
    try:
        from ..forecast import services as fc
        if fc.is_rep(db, user):
            ctx["forecastStanding"] = fc.rep_signal(db, user)["summary"]
    except Exception:
        pass
    if prior and prior.commitments:
        ctx["priorCommitments"] = [c.get("text") for c in prior.commitments if c.get("text")]
    return ctx


def _system(presenter: str, period: str) -> str:
    return (
        f"You are {presenter}, a warm, encouraging sales coach at BT Local Business Oxford & Bucks "
        f"(UK B2B telecoms). You are having a short, reflective one-to-one conversation with a rep about "
        f"their {period} performance review, which they have just received. Your aim is to deepen their "
        "understanding and help them own their improvement — NOT to lecture or judge. Be genuinely "
        "curious about what THEY think. Ask ONE question at a time, keep each turn to 1-3 sentences, and "
        "use their own words back to them. Ground your questions in the review they received (headline + "
        "script provided) and their numbers. Probe gently when an answer is vague; surface any blockers; "
        "and guide them to 1-3 concrete, owned commitments for next period. If prior commitments are "
        "provided, OPEN by warmly asking how those went. After about 4-7 exchanges, or once they've "
        "reflected well and named commitments, wrap up with a short, encouraging close. Never say things "
        "like 'you underperformed'. If the rep expresses real distress, be supportive and gently suggest "
        "they speak with their manager or HR rather than pushing performance talk. UK English, second "
        "person. Return STRICT JSON only: {\"message\":\"your next spoken line\",\"done\":true|false}."
    )


def _fallback_next(turns: list) -> dict:
    asked = sum(1 for t in turns if t.get("role") == "ai")
    if asked >= len(_FALLBACK_QS):
        return {"message": "Thank you for reflecting — I've captured that. Have a strong next period.", "done": True}
    return {"message": _FALLBACK_QS[asked], "done": False}


def next_message(db: Session, reflection: ReviewReflection, video: PerformanceVideo, user: User) -> dict:
    """The presenter's next line, given the transcript so far. Returns {message, done}."""
    turns = reflection.turns or []
    ai_count = sum(1 for t in turns if t.get("role") == "ai")
    if not settings.anthropic_api_key:
        return _fallback_next(turns)

    presenter = presenter_for(video.video_type)
    period = period_for(video.video_type)
    ctx = _context(db, user, video, prior_reflection(db, user, video))
    who = user.short_name or (user.name or "Rep").split()[0]
    convo = "\n".join(f"{presenter if t.get('role') == 'ai' else who}: {t.get('text', '')}" for t in turns)
    if not turns:
        instruction = "Open the reflection now (greet them by first name)."
    elif ai_count >= MAX_EXCHANGES:
        instruction = "Wrap up now: a short, encouraging summary that reflects back their commitments."
    else:
        instruction = "Continue — ask the next single, specific question."

    user_msg = (f"REVIEW CONTEXT:\n{json.dumps(ctx, default=str)}\n\n"
                f"CONVERSATION SO FAR:\n{convo or '(nothing yet)'}\n\n{instruction}")
    try:
        from ...pipeline.analyzer import _claude, _extract_json
        d = _extract_json(_claude(_system(presenter, period), user_msg, settings.claude_call_model, max_tokens=400))
        msg = (d.get("message") or "").strip()
        done = bool(d.get("done")) or ai_count >= MAX_EXCHANGES
        if not msg:
            return _fallback_next(turns)
        return {"message": msg, "done": done}
    except Exception:
        return _fallback_next(turns)


def _clamp(v) -> int | None:
    try:
        return max(0, min(100, int(round(float(v)))))
    except (TypeError, ValueError):
        return None


def extract(db: Session, reflection: ReviewReflection, video: PerformanceVideo, user: User) -> None:
    """Mine structured signal from a completed transcript (no-op-safe without the Anthropic key)."""
    turns = reflection.turns or []
    presenter = presenter_for(video.video_type)
    who = user.short_name or (user.name or "Rep").split()[0]
    convo = "\n".join(f"{presenter if t.get('role') == 'ai' else who}: {t.get('text', '')}" for t in turns)
    reflection.extracted_at = datetime.utcnow()

    rep_words = " ".join(t.get("text", "") for t in turns if t.get("role") == "rep").strip()
    if not settings.anthropic_api_key:
        reflection.summary = (rep_words[:280] + "…") if len(rep_words) > 280 else (rep_words or None)
        return

    dp = video.data_points or {}
    system = (
        "You analyse a sales rep's reflection on their performance review, for their manager. From the "
        "conversation AND the review's real numbers, extract structured insight. Judge self-awareness by "
        "comparing the rep's self-assessment to the actual numbers. Be fair and specific; never invent "
        "facts. UK English. Return STRICT JSON only."
    )
    user_msg = (
        f"REVIEW NUMBERS:\n{json.dumps(dp, default=str)[:3000]}\n\nCONVERSATION:\n{convo}\n\n"
        "Return JSON: {"
        "\"summary\":\"2-3 sentence manager-facing summary of what the rep said and means\","
        "\"selfAssessment\":\"the rep's own read of the period, paraphrased\","
        "\"blockers\":[{\"text\":\"...\",\"category\":\"lead_quality|time|product_knowledge|confidence|process|external|other\",\"needsManager\":true|false}],"
        "\"commitments\":[{\"text\":\"...\",\"category\":\"...\",\"target\":\"measurable target or null\"}],"
        "\"themes\":[\"short theme labels\"],"
        "\"understandingScore\":0-100,"
        "\"selfAwareness\":0-100,\"selfAwarenessNote\":\"how their self-view matches the data\","
        "\"engagementScore\":0-100,\"askedForHelp\":true|false}"
    )
    try:
        from ...pipeline.analyzer import _claude, _extract_json
        d = _extract_json(_claude(system, user_msg, settings.claude_call_model, max_tokens=900))
    except Exception:
        d = {}

    reflection.summary = d.get("summary") or reflection.summary
    reflection.self_assessment = d.get("selfAssessment")
    reflection.blockers = [b for b in (d.get("blockers") or []) if isinstance(b, dict)]
    reflection.commitments = [{**c, "met": None} for c in (d.get("commitments") or []) if isinstance(c, dict)]
    reflection.themes = [t for t in (d.get("themes") or []) if isinstance(t, str)]
    reflection.understanding_score = _clamp(d.get("understandingScore"))
    reflection.self_awareness_gap = _clamp(d.get("selfAwareness"))
    reflection.self_awareness_note = d.get("selfAwarenessNote")
    reflection.engagement_score = _clamp(d.get("engagementScore"))
    reflection.asked_for_help = bool(d.get("askedForHelp"))


def assess_prior_commitments(db: Session, reflection: ReviewReflection, video: PerformanceVideo, user: User) -> None:
    """Close the loop: in this new reflection the rep discussed how last period's commitments went —
    judge each prior commitment met/not and write it back, feeding the follow-through score."""
    prior = prior_reflection(db, user, video)
    if not prior or not prior.commitments:
        return
    pending = [c for c in prior.commitments if c.get("met") is None and c.get("text")]
    if not pending or not settings.anthropic_api_key:
        return
    turns = reflection.turns or []
    convo = "\n".join(t.get("text", "") for t in turns)
    system = ("You assess whether a sales rep met the commitments they made last period, based ONLY on "
              "what they say in this new reflection. Be fair; if it's genuinely unclear, mark met=false. "
              "UK English. Return STRICT JSON only.")
    user_msg = (f"COMMITMENTS FROM LAST PERIOD:\n{json.dumps([c['text'] for c in pending])}\n\n"
                f"THIS PERIOD'S REFLECTION:\n{convo}\n\n"
                "Return JSON: {\"results\":[{\"text\":\"the commitment text\",\"met\":true|false}]}")
    try:
        from ...pipeline.analyzer import _claude, _extract_json
        d = _extract_json(_claude(system, user_msg, settings.claude_call_model, max_tokens=400))
        verdict = {(r.get("text") or "").strip().lower(): r.get("met")
                   for r in (d.get("results") or []) if isinstance(r, dict)}
    except Exception:
        return
    changed, new_c = False, []
    for c in prior.commitments:
        if c.get("met") is None:
            v = verdict.get((c.get("text") or "").strip().lower())
            if v is not None:
                c = {**c, "met": bool(v)}
                changed = True
        new_c.append(c)
    if changed:
        prior.commitments = new_c   # reassign so the JSON column tracks the mutation
        db.commit()
