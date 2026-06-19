"""Shared helpers for the Intelligence Layer: per-call metric loading, rep averages,
trend series, and team reference lines. Everything derives from completed calls
(CallAnalysis + CallScore + Call.outcome), so it stays in sync with the pipeline."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from ...models import Call, CallAnalysis, CallScore, User

# Outcome vocabulary (the one-tap keystone). `order_placed` is the close.
OUTCOMES = [
    {"value": "order_placed", "label": "Order placed", "tone": "win"},
    {"value": "callback", "label": "Callback scheduled", "tone": "warm"},
    {"value": "interested", "label": "Interested — follow up", "tone": "warm"},
    {"value": "not_interested", "label": "Not interested", "tone": "cold"},
    {"value": "wrong_number", "label": "Wrong number", "tone": "neutral"},
    {"value": "no_answer", "label": "No answer", "tone": "neutral"},
]
OUTCOME_LABELS = {o["value"]: o["label"] for o in OUTCOMES}

# Winning-Call-DNA target bands (Feature 5). Static defaults until the DNA engine
# (Phase 3, needs 500+ outcome-logged calls) computes team-specific ranges.
DNA_BANDS = {
    "talk_ratio": (38, 45),       # rep talk %
    "questions": (5, 7),          # discovery+ questions per call
    "interruptions": (0, 1),
    "length_min": (9, 14),
    "filler_per_10": (0, 8),
    "quality": (70, 100),
}


def quality_100(score_overall: float | None) -> float | None:
    """CallScore.overall is 0–5; coaching cards speak in 0–100."""
    if score_overall is None:
        return None
    return round(float(score_overall) * 20, 1)


def _avg_scores(db, call_ids: list[int]) -> dict[int, float]:
    if not call_ids:
        return {}
    rows = (db.query(CallScore.call_id, func.avg(CallScore.overall))
            .filter(CallScore.call_id.in_(call_ids))
            .group_by(CallScore.call_id).all())
    return {cid: float(avg or 0) for cid, avg in rows}


def load_call_metrics(db, user_id: int, start: datetime, end: datetime,
                      exclude_call_id: int | None = None) -> list[dict]:
    """Per-call metrics for a rep in [start, end). Only completed calls (the ones with
    analysis). Returns lightweight dicts used by every downstream view."""
    q = (db.query(Call).options(joinedload(Call.analysis))
         .filter(Call.host_id == user_id, Call.started_at >= start,
                 Call.started_at < end, Call.status == "completed"))
    if exclude_call_id:
        q = q.filter(Call.id != exclude_call_id)
    calls = q.all()
    qmap = _avg_scores(db, [c.id for c in calls])
    out = []
    for c in calls:
        a = c.analysis
        out.append({
            "id": c.id,
            "started_at": c.started_at,
            "date": c.started_at.date(),
            "quality": quality_100(qmap[c.id]) if c.id in qmap else None,
            "talk_ratio": (a.talk_ratio if a and a.talk_ratio else None),
            "interruptions": (a.interruptions if a is not None else None),
            "questions": (a.question_rate if a is not None else None),
            "filler": (a.filler_count if a is not None else None),
            "length_min": round((c.duration_sec or 0) / 60, 1),
            "outcome": c.outcome,
            "is_order": c.outcome == "order_placed",
        })
    return out


def _mean(vals):
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def averages(rows: list[dict]) -> dict:
    """Aggregate per-call rows into mean metrics + close rate + volume."""
    n = len(rows)
    orders = sum(1 for r in rows if r["is_order"])
    logged = sum(1 for r in rows if r["outcome"])
    return {
        "calls": n,
        "quality": _mean([r["quality"] for r in rows]),
        "talk_ratio": _mean([r["talk_ratio"] for r in rows]),
        "interruptions": _mean([r["interruptions"] for r in rows]),
        "questions": _mean([r["questions"] for r in rows]),
        "filler": _mean([r["filler"] for r in rows]),
        "length_min": _mean([r["length_min"] for r in rows]),
        "orders": orders,
        "closeRate": round(orders / logged, 3) if logged else None,
    }


def rep_averages(db, user_id: int, days: int = 30, asof: datetime | None = None,
                 exclude_call_id: int | None = None) -> dict:
    asof = asof or datetime.utcnow()
    start = asof - timedelta(days=days)
    rows = load_call_metrics(db, user_id, start, asof, exclude_call_id=exclude_call_id)
    a = averages(rows)
    a["days"] = days
    return a


def team_averages(db, days: int = 30, asof: datetime | None = None) -> dict:
    """Team-wide reference line for trend charts."""
    asof = asof or datetime.utcnow()
    start = asof - timedelta(days=days)
    q = (db.query(Call).options(joinedload(Call.analysis))
         .filter(Call.started_at >= start, Call.started_at < asof,
                 Call.status == "completed"))
    calls = q.all()
    qmap = _avg_scores(db, [c.id for c in calls])
    rows = []
    for c in calls:
        a = c.analysis
        rows.append({
            "quality": quality_100(qmap[c.id]) if c.id in qmap else None,
            "talk_ratio": a.talk_ratio if a and a.talk_ratio else None,
            "interruptions": a.interruptions if a is not None else None,
            "questions": a.question_rate if a is not None else None,
            "filler": a.filler_count if a is not None else None,
            "length_min": round((c.duration_sec or 0) / 60, 1),
            "is_order": c.outcome == "order_placed",
            "outcome": c.outcome,
        })
    return averages(rows)


# Metrics shown on skill trend charts (key → label + whether higher is better).
SKILLS = [
    {"key": "quality", "label": "Call quality", "higherBetter": True, "max": 100},
    {"key": "talk_ratio", "label": "Talk ratio %", "higherBetter": None, "band": DNA_BANDS["talk_ratio"]},
    {"key": "questions", "label": "Questions asked", "higherBetter": True, "band": DNA_BANDS["questions"]},
    {"key": "interruptions", "label": "Interruptions", "higherBetter": False, "band": DNA_BANDS["interruptions"]},
    {"key": "filler", "label": "Filler words", "higherBetter": False},
    {"key": "length_min", "label": "Call length (min)", "higherBetter": None, "band": DNA_BANDS["length_min"]},
]


def weekly_series(rows: list[dict], weeks: int, asof: date) -> list[dict]:
    """Bin per-call rows into weekly averages for each skill metric."""
    buckets: dict[int, list[dict]] = {}
    for r in rows:
        wk = (asof - r["date"]).days // 7
        if 0 <= wk < weeks:
            buckets.setdefault(wk, []).append(r)
    series = []
    for wk in range(weeks - 1, -1, -1):  # oldest → newest
        wk_rows = buckets.get(wk, [])
        wk_start = asof - timedelta(days=(wk + 1) * 7 - 1)
        point = {"label": wk_start.strftime("%d %b"), "calls": len(wk_rows)}
        for s in SKILLS:
            point[s["key"]] = _mean([r[s["key"]] for r in wk_rows])
        series.append(point)
    return series


def trend_direction(rows_recent: list[dict], rows_prior: list[dict], key: str,
                    higher_better) -> str:
    """improving / declining / flat by comparing a recent window to the prior one."""
    a = _mean([r[key] for r in rows_recent])
    b = _mean([r[key] for r in rows_prior])
    if a is None or b is None:
        return "flat"
    diff = a - b
    thresh = max(1.0, abs(b) * 0.05)
    if abs(diff) < thresh or higher_better is None:
        return "flat" if abs(diff) < thresh else ("up" if diff > 0 else "down")
    if higher_better:
        return "up" if diff > 0 else "down"
    return "up" if diff < 0 else "down"  # fewer is better → improvement shows "up"
