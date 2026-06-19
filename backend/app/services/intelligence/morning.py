"""Feature 1 — Rep Morning Intelligence Dashboard.

Section A: yesterday's performance summary.   Section B: skill trend charts (30/60/90d).
Section C: month-to-date snapshot + achievement predictor (reuses SalesIQ).
Section D: today's priority call list (Phase-2 stub — Prospect Readiness Score)."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta

from ...models import User
from ..salesiq.dashboard import bc_dashboard, rep_dashboard
from ..salesiq.roles import role_for_user
from .common import (DNA_BANDS, SKILLS, load_call_metrics, averages,
                     rep_averages, team_averages, trend_direction, weekly_series)


def _yesterday_bounds(asof: date):
    y = asof - timedelta(days=1)
    # walk back over the weekend so Monday compares to Friday
    while y.weekday() >= 5:
        y -= timedelta(days=1)
    start = datetime.combine(y, time.min)
    return y, start, start + timedelta(days=1)


def _section_a(db, user: User, asof: date) -> dict:
    yday, ys, ye = _yesterday_bounds(asof)
    rows = load_call_metrics(db, user.id, ys, ye)
    agg = averages(rows)
    avg30 = rep_averages(db, user.id, days=30, asof=ys)  # excludes yesterday

    # daily call average over 30 days (working days only)
    start30 = datetime.combine(asof - timedelta(days=30), time.min)
    rows30 = load_call_metrics(db, user.id, start30, datetime.combine(asof, time.min))
    working_days = len({r["date"] for r in rows30}) or 1
    daily_avg_calls = round(len(rows30) / working_days, 1)

    # strength / improvement / coaching focus — from yesterday's coaching cards
    from ...models import Call
    strengths, improvements = [], []
    ana = (db.query(Call).filter(Call.id.in_([r["id"] for r in rows])).all()) if rows else []
    qmap = {r["id"]: (r["quality"] if r["quality"] is not None else 999) for r in rows}
    focus = []
    for c in ana:
        if c.analysis:
            strengths += (c.analysis.strengths or [])
            improvements += (c.analysis.improvements or [])
            if c.analysis.one_thing:
                focus.append((qmap.get(c.id, 999), c.analysis.one_thing))
    top_strength = Counter(strengths).most_common(1)
    top_improve = Counter(improvements).most_common(1)
    # The single coaching focus = the "one thing" from yesterday's most coachable (lowest-scoring) call.
    coaching_focus = sorted(focus, key=lambda x: x[0])[0][1] if focus else None

    quality = agg["quality"]
    q30 = avg30.get("quality")
    if quality is None or q30 is None:
        trend = "flat"
    elif quality - q30 >= 2:
        trend = "improving"
    elif q30 - quality >= 2:
        trend = "declining"
    else:
        trend = "flat"

    top_imp = top_improve[0][0] if top_improve else None
    # When the trend is declining, say WHAT needs attention + WHAT to do about it.
    attention_reason = None
    if trend == "declining":
        if quality is not None and q30 is not None:
            attention_reason = (f"Your call quality averaged {round(quality)} yesterday vs "
                                f"{round(q30)} over the last 30 days.")
        if top_imp:
            attention_reason = (attention_reason + " " if attention_reason else "") + f"Focus: {top_imp}"

    return {
        "date": yday.isoformat(),
        "calls": agg["calls"], "dailyAvgCalls": daily_avg_calls,
        "quality": quality, "quality30dAvg": q30,
        "qualityDelta": (round(quality - q30, 1) if quality is not None and q30 is not None else None),
        "trend": trend,
        "attentionReason": attention_reason,
        "talkTimeSec": int(sum((r["length_min"] or 0) for r in rows) * 60),
        "topStrength": top_strength[0][0] if top_strength else None,
        "topImprovement": top_imp,
        "coachingFocus": coaching_focus,
        "ordersYesterday": agg["orders"],
    }


def _section_b(db, user: User, asof: date) -> dict:
    """13 weeks (~90d) of weekly skill points + personal-best & team-average ref lines."""
    weeks = 13
    start = datetime.combine(asof - timedelta(weeks=weeks), time.min)
    rows = load_call_metrics(db, user.id, start, datetime.combine(asof + timedelta(days=1), time.min))
    series = weekly_series(rows, weeks, asof)
    team = team_averages(db, days=90, asof=datetime.combine(asof, time.min))
    skills = []
    for s in SKILLS:
        vals = [p[s["key"]] for p in series if p[s["key"]] is not None]
        if s["higherBetter"] is False:
            best = min(vals) if vals else None
        else:
            best = max(vals) if vals else None
        skills.append({
            "key": s["key"], "label": s["label"], "higherBetter": s["higherBetter"],
            "band": list(s["band"]) if s.get("band") else None,
            "personalBest": best, "teamAvg": team.get(s["key"]),
        })
    return {"weeks": weeks, "series": series, "skills": skills}


def _predictor(perf: dict, days_remaining: int) -> dict:
    """Lightweight Achievement Predictor (Feature 3) from MTD run-rate vs target."""
    sov, target = perf.get("sovMTD") or 0, perf.get("sovTarget") or 0
    run_rate = perf.get("runRate")
    proj_pct = round(run_rate / target * 100) if (run_rate and target) else perf.get("sovPct")
    gap = round(max(0, target - sov), 2)
    rag = "green" if (proj_pct or 0) >= 100 else "amber" if (proj_pct or 0) >= 75 else "red"
    return {
        "projectedFinishPct": proj_pct, "gapToTarget": gap,
        "daysRemaining": days_remaining, "rag": rag,
        "onTrack": (proj_pct or 0) >= 100,
    }


def _days_left_after_leave(db, user: User, today: date) -> tuple:
    """Selling days remaining in the sales month, minus the user's booked annual leave."""
    from ..salesiq import fincal
    from ...modules.hr import leave as hr_leave
    base = fincal.days_remaining(today)
    leave = 0.0
    try:
        end = fincal.current_sales_month(today)["end"]
        for r in hr_leave.user_leave(db, user.id, today, end):
            d = r["date"]
            if d.weekday() < 5:
                leave += 0.5 if r["half"] else 1.0
    except Exception:
        leave = 0.0
    return base, round(leave, 1), max(0, int(round(base - leave)))


def _section_c(db, user: User, role: str) -> dict:
    today = date.today()
    try:
        base_days, leave_days, days_left = _days_left_after_leave(db, user, today)
        if role == "bc":
            d = bc_dashboard(db, user)
            perf = d.get("performance", {})
            return {"type": "bc", "leadsMTD": perf.get("leadsMTD"),
                    "leadTarget": perf.get("leadTarget"), "leadPct": perf.get("leadPct"),
                    "gmGenerated": perf.get("gmGenerated"), "rag": perf.get("rag"),
                    "f2f": perf.get("f2f"), "ordersSigned": perf.get("won"),
                    "daysRemaining": days_left, "daysRemainingRaw": base_days, "leaveDays": leave_days,
                    "predictor": None, "salesMonthLabel": d.get("meta", {}).get("salesMonthLabel")}
        d = rep_dashboard(db, user, role=role)
        perf = d.get("performance", {})
        sov = perf.get("sovMTD") or 0
        tgt = perf.get("sovTarget") or 0
        pending_sov = perf.get("pendingValueSov") or 0
        run_rate = perf.get("runRate") or sov
        # Finish % if they keep their current pace AND close the pending pipeline on top — so
        # this is always the projected pace plus pending, i.e. higher than pace alone.
        with_pending_pct = round((run_rate + pending_sov) / tgt * 100) if tgt else None
        return {
            "type": "rep",
            "sovMTD": perf.get("sovMTD"), "sovTarget": perf.get("sovTarget"),
            "sovPct": perf.get("sovPct"), "rag": perf.get("rag"),
            "dataSov": (perf.get("connectivity") or {}).get("mtd"),
            "cloudSov": (perf.get("cloud") or {}).get("mtd"),
            "mobileSov": (perf.get("mobile") or {}).get("mtd"),
            "gmMTD": perf.get("gmMTD"), "ordersMTD": perf.get("ordersMTD"),
            "pendingCount": perf.get("pendingCount"), "pendingSov": pending_sov,
            "withPendingPct": with_pending_pct,
            "daysRemaining": days_left, "daysRemainingRaw": base_days, "leaveDays": leave_days,
            "salesMonthLabel": d.get("meta", {}).get("salesMonthLabel"),
            "predictor": _predictor(perf, days_left),
        }
    except Exception:
        return {"type": role, "unavailable": True}


def morning_dashboard(db, user: User) -> dict:
    asof = date.today()
    role = role_for_user(db, user) or "rep"
    return {
        "meta": {
            "userId": user.id, "name": user.name, "role": role,
            "greetingDate": asof.strftime("%A %d %B %Y"),
            "computedAt": datetime.utcnow().isoformat() + "Z",
        },
        "yesterday": _section_a(db, user, asof),
        "skills": _section_b(db, user, asof),
        "monthToDate": _section_c(db, user, role),
        "priorityCalls": {
            "available": False,
            "message": "Today's Priority Call List arrives with the AI Prospect Readiness "
                       "Score (Phase 2) — ranking every prospect by Apollo intent, email "
                       "engagement and recency.",
            "items": [],
        },
    }
