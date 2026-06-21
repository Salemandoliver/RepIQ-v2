"""Insight engine (Intelligence Phase 3) — the brain that turns facts into a prioritised, evidence-
bound action list, and learns from feedback.

Flow: detectors emit candidate insights → optional Claude pass sharpens the wording (never the
numbers) → upsert by ``dedupe_key``. The upsert is what makes this a *living* feed rather than a
firehose: a finding that recurs updates one row; a dismissed insight stays dismissed; a finding that
stops holding is auto-resolved; a regression re-opens. That dismiss/resolve memory is the flywheel.
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from ...config import settings
from ...models import Insight, User
from .detectors import run_detectors

log = logging.getLogger("calliq.insights")

_SEVERITY_ORDER = {"high": 0, "medium": 1, "positive": 2, "low": 3}
_CONTENT_FIELDS = ("scope", "subject_type", "subject_id", "subject_key", "subject_name",
                   "category", "severity", "title", "body", "recommendation",
                   "evidence", "metrics", "signal_key", "period_days")


def _polish(candidates: list[dict]) -> dict[str, dict]:
    """Optional Claude sharpening. Returns {dedupe_key: {title, body, recommendation}}. Best-effort:
    on any error the templated wording stands. Numbers must be preserved exactly."""
    if not settings.anthropic_api_key or not candidates:
        return {}
    import json
    from ...pipeline.analyzer import _claude, _extract_json
    items = [{"key": c["dedupe_key"], "title": c["title"], "body": c["body"],
              "recommendation": c["recommendation"], "numbers": c["metrics"]}
             for c in candidates[:30]]
    system = (
        "You are the coaching-insights editor for a UK B2B telecoms sales floor (BT Local Business "
        "Oxford & Bucks). You receive draft manager insights and rewrite each to be sharper, warmer "
        "and more specific. STRICT RULES: keep every number EXACTLY as given (never invent or change "
        "figures or names); body ≤ 2 sentences; recommendation = one concrete action a manager can take "
        "this week; supportive, never harsh; UK English. Return STRICT JSON only."
    )
    user = ("Rewrite these insights. Return {\"insights\":[{\"key\":\"…\",\"title\":\"…\",\"body\":\"…\","
            "\"recommendation\":\"…\"}]} with one entry per key.\n\n" + json.dumps(items, indent=1))
    try:
        data = _extract_json(_claude(system, user, settings.claude_call_model, max_tokens=3000))
        return {i["key"]: i for i in data.get("insights", []) if i.get("key")}
    except Exception as e:
        log.warning("insight polish skipped: %s", e)
        return {}


def generate(db: Session, days: int = 30, asof: datetime | None = None, polish: bool = True) -> dict:
    """Regenerate the insight feed for the current window. Idempotent via dedupe_key."""
    candidates = run_detectors(db, days=days, asof=asof)
    edits = _polish(candidates) if polish else {}

    seen: set[str] = set()
    created = updated = reopened = 0
    for c in candidates:
        key = c["dedupe_key"]
        if key in seen:                       # collapse any same-run duplicates
            continue
        seen.add(key)
        e = edits.get(key)
        if e:
            c = {**c, "title": e.get("title") or c["title"], "body": e.get("body") or c["body"],
                 "recommendation": e.get("recommendation") or c["recommendation"]}
        row = db.query(Insight).filter(Insight.dedupe_key == key).first()
        if row is None:
            db.add(Insight(status="new", seen_count=1, **{k: c[k] for k in _CONTENT_FIELDS}))
            created += 1
            continue
        # Respect a manager's dismissal — refresh the data quietly but keep it hidden.
        if row.status == "dismissed":
            row.seen_count += 1
            row.metrics, row.evidence = c["metrics"], c["evidence"]
            continue
        # A finding that was actioned/resolved but is firing again = a regression → re-open.
        if row.status in ("actioned", "resolved"):
            row.status = "new"
            reopened += 1
        else:
            updated += 1
        for k in _CONTENT_FIELDS:
            setattr(row, k, c[k])
        row.seen_count += 1
        row.updated_at = datetime.utcnow()

    # Auto-resolve open findings that no longer hold this run (the condition cleared).
    resolved = 0
    for row in (db.query(Insight)
                .filter(Insight.status.in_(("new", "acknowledged")),
                        Insight.dedupe_key.notin_(seen) if seen else Insight.id.isnot(None)).all()):
        if row.dedupe_key not in seen:
            row.status = "resolved"
            row.updated_at = datetime.utcnow()
            resolved += 1
    db.commit()
    return {"candidates": len(candidates), "created": created, "updated": updated,
            "reopened": reopened, "resolved": resolved, "polished": bool(edits)}


# --------------------------------------------------------------------- queries
def _sort_key(row: Insight):
    return (_SEVERITY_ORDER.get(row.severity, 5), -(row.updated_at or datetime.min).timestamp())


def list_for(db: Session, viewer: User, is_manager: bool, scope: str | None = None,
             subject_id: int | None = None, status: str = "open") -> list[Insight]:
    q = db.query(Insight)
    if status == "open":
        q = q.filter(Insight.status.in_(("new", "acknowledged")))
    elif status and status != "all":
        q = q.filter(Insight.status == status)
    if not is_manager:
        # reps see only their own rep-scoped insights
        q = q.filter(Insight.scope == "rep", Insight.subject_id == viewer.id)
    else:
        if scope:
            q = q.filter(Insight.scope == scope)
        if subject_id is not None:
            q = q.filter(Insight.subject_id == subject_id)
    return sorted(q.all(), key=_sort_key)


def to_dict(i: Insight) -> dict:
    return {
        "id": i.id, "scope": i.scope, "category": i.category, "severity": i.severity,
        "title": i.title, "body": i.body, "recommendation": i.recommendation,
        "evidence": i.evidence or [], "metrics": i.metrics or {},
        "subjectType": i.subject_type, "subjectId": i.subject_id, "subjectName": i.subject_name,
        "status": i.status, "feedback": i.feedback, "seenCount": i.seen_count,
        "createdAt": i.created_at.isoformat() if i.created_at else None,
        "updatedAt": i.updated_at.isoformat() if i.updated_at else None,
    }


def apply_feedback(db: Session, i: Insight, user: User, status: str | None,
                   feedback: str | None, note: str | None) -> Insight:
    if status in ("acknowledged", "actioned", "dismissed", "new"):
        i.status = status
        if status == "actioned":
            i.actioned_by = user.id
    if feedback in ("helpful", "not_helpful"):
        i.feedback = feedback
    if note is not None:
        i.feedback_note = note
    i.updated_at = datetime.utcnow()
    db.commit()
    return i
