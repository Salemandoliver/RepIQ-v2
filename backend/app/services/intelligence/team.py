"""Feature 4 — Manager Team Command Centre (Phase 1 basics).

Rep grid (yesterday score, 7-day trend, calls vs avg, MTD achievement, alert badge),
team aggregate stats, and an auto-generated Smart Alerts panel. Drill-down to a rep
scorecard reuses the morning dashboard + coaching cards."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import func

from ...models import Call, CallAnalysis, User
from ..salesiq.dashboard import bc_dashboard, rep_dashboard
from ..salesiq.roles import role_for_user
from .common import averages, load_call_metrics, quality_100, rep_averages, _avg_scores


def _team_reps(db, team: str | None) -> list[User]:
    reps = []
    for u in db.query(User).filter(User.active.is_(True)).order_by(User.name).all():
        r = role_for_user(db, u)
        if r is None or r == "manager":
            continue
        if team and team.lower() not in ("all", ""):
            tname = (u.team.name if u.team else "") or ""
            if team.lower() not in tname.lower():
                continue
        reps.append(u)
    return reps


def _arrow(direction: str) -> str:
    return {"up": "improving", "down": "declining"}.get(direction, "flat")


def _mtd_achievement(db, user: User, role: str):
    try:
        if role == "bc":
            p = bc_dashboard(db, user).get("performance", {})
            return p.get("leadPct"), p.get("rag"), "leads"
        p = rep_dashboard(db, user, role=role).get("performance", {})
        return p.get("sovPct"), p.get("rag"), "sov"
    except Exception:
        return None, "none", None


def _rep_card(db, user: User, asof: date) -> dict:
    role = role_for_user(db, user) or "rep"
    yday = asof - timedelta(days=1)
    while yday.weekday() >= 5:
        yday -= timedelta(days=1)
    ys = datetime.combine(yday, time.min)
    y_rows = load_call_metrics(db, user.id, ys, ys + timedelta(days=1))
    y_agg = averages(y_rows)

    # 7-day vs prior-7-day quality trend
    now = datetime.combine(asof, time.min)
    recent = load_call_metrics(db, user.id, now - timedelta(days=7), now)
    prior = load_call_metrics(db, user.id, now - timedelta(days=14), now - timedelta(days=7))
    from .common import trend_direction
    direction = trend_direction(recent, prior, "quality", True)

    # Short "why" brief for the declining-quality alert: this week vs last + the likely drivers.
    # (trend_direction returns "up"/"down"/"flat" — "down" == quality declining.)
    decline_detail = None
    if direction == "down":
        ra, pa = averages(recent), averages(prior)
        if ra.get("quality") is not None and pa.get("quality") is not None:
            rq, pq = round(ra["quality"]), round(pa["quality"])
            parts = [f"Avg call quality {rq}/100 this week vs {pq} last week"
                     + (f" (down {pq - rq})." if pq > rq else ".")]
            drivers = []
            if ra.get("talk_ratio") and pa.get("talk_ratio") and ra["talk_ratio"] - pa["talk_ratio"] >= 3:
                drivers.append(f"talking more ({round(ra['talk_ratio'])}% vs {round(pa['talk_ratio'])}%)")
            if (ra.get("questions") is not None and pa.get("questions") is not None
                    and pa["questions"] - ra["questions"] >= 0.5):
                drivers.append(f"asking fewer questions ({round(ra['questions'], 1)} vs {round(pa['questions'], 1)}/call)")
            if (ra.get("interruptions") is not None and pa.get("interruptions") is not None
                    and ra["interruptions"] - pa["interruptions"] >= 1):
                drivers.append(f"interrupting more ({round(ra['interruptions'], 1)} vs {round(pa['interruptions'], 1)}/call)")
            if drivers:
                parts.append("Likely drivers: " + ", ".join(drivers) + ".")
            parts.append(f"Based on {len(recent)} call(s) this week. Open their scorecard for the calls behind it.")
            decline_detail = " ".join(parts)

    avg30 = rep_averages(db, user.id, days=30, asof=ys)
    start30 = now - timedelta(days=30)
    rows30 = load_call_metrics(db, user.id, start30, now)
    working_days = len({r["date"] for r in rows30}) or 1
    daily_avg = round(len(rows30) / working_days, 1)

    # today's calls so far (for the 0-calls alert)
    today_n = (db.query(func.count(Call.id))
               .filter(Call.host_id == user.id,
                       Call.started_at >= datetime.combine(asof, time.min)).scalar() or 0)

    pct, rag, _kind = _mtd_achievement(db, user, role)
    return {
        "userId": user.id, "name": user.name, "shortName": user.short_name,
        "avatarColor": user.avatar_color, "role": role,
        "yesterdayQuality": y_agg["quality"], "yesterdayCalls": y_agg["calls"],
        "dailyAvgCalls": daily_avg, "trend": _arrow(direction),
        "achievementPct": pct, "rag": rag,
        "callsToday": int(today_n),
        "declineDetail": decline_detail,
        "alerts": [],  # filled by _alerts
    }


def _alerts(db, cards: list[dict], asof: date) -> list[dict]:
    out = []
    now = datetime.utcnow()
    after_late_morning = now.hour >= 10  # ~11:30 BST
    is_working_day = asof.weekday() < 5  # don't flag 0-calls at weekends
    # Reps on leave today (annual/sick/etc.) must NOT be flagged for "0 calls" — respect HR leave.
    on_leave_today = set()
    try:
        from ...modules.hr import leave as hr_leave
        on_leave_today = {r["user_id"] for r in hr_leave.leave_rows(db, asof, asof)}
    except Exception:
        pass
    # Fallback / belt-and-braces: also honour the SharePoint Holiday Tracker (matched by name),
    # in case the in-app HR leave hasn't been synced. Code 'B' = company-wide bank holiday, skip.
    try:
        from ..salesiq import trackers
        from ..salesiq.roles import user_agent_match
        if trackers.holiday_configured():
            off_names = [h.get("name") for h in trackers.holiday_rows()
                         if h.get("date") == asof and str(h.get("code") or "").upper() != "B"]
            if off_names:
                for c in cards:
                    if c["userId"] in on_leave_today:
                        continue
                    u = db.get(User, c["userId"])
                    if u and any(user_agent_match(u, nm) for nm in off_names):
                        on_leave_today.add(c["userId"])
    except Exception:
        pass
    for c in cards:
        if (after_late_morning and is_working_day and c["callsToday"] == 0
                and (c["dailyAvgCalls"] or 0) >= 2 and c["userId"] not in on_leave_today):
            out.append({"userId": c["userId"], "severity": "warn", "type": "no_calls",
                        "text": f"{c['name']} has made 0 calls today.", "rep": c["name"]})
            c["alerts"].append("no_calls")
        if c["trend"] == "declining" and (c["yesterdayQuality"] is not None):
            out.append({"userId": c["userId"], "severity": "warn", "type": "declining",
                        "text": f"{c['name']}'s call quality has been declining this week — "
                                "worth a check-in.", "rep": c["name"],
                        "detail": c.get("declineDetail")})
            c["alerts"].append("declining")
        if c["trend"] == "improving" and (c["yesterdayQuality"] or 0) >= 65:
            out.append({"userId": c["userId"], "severity": "good", "type": "improving",
                        "text": f"{c['name']} is improving — recognition opportunity.",
                        "rep": c["name"]})
            c["alerts"].append("improving")
        if c["achievementPct"] is not None and c["achievementPct"] < 50 and (c["dailyAvgCalls"] or 0) > 0:
            out.append({"userId": c["userId"], "severity": "warn", "type": "behind_target",
                        "text": f"{c['name']} is at {c['achievementPct']}% of target this month.",
                        "rep": c["name"], "pct": c["achievementPct"]})
            c["alerts"].append("behind_target")
    # overdue callbacks across the team (logged 'callback' >7 days ago, no later call to that number)
    cutoff = datetime.combine(asof - timedelta(days=7), time.min)
    overdue = (db.query(func.count(Call.id))
               .filter(Call.outcome == "callback", Call.outcome_at < cutoff).scalar() or 0)
    if overdue:
        out.append({"severity": "warn", "type": "overdue_callbacks",
                    "text": f"{int(overdue)} callbacks logged over a week ago may now be overdue."})
    # severity order: warn first, then good
    out.sort(key=lambda a: 0 if a["severity"] == "warn" else 1)
    return out


def _team_aggregates(db, cards: list[dict], reps: list[User], asof: date) -> dict:
    yday = asof - timedelta(days=1)
    while yday.weekday() >= 5:
        yday -= timedelta(days=1)
    ys = datetime.combine(yday, time.min)
    ids = [u.id for u in reps]
    total_calls_yday = (db.query(func.count(Call.id))
                        .filter(Call.host_id.in_(ids), Call.started_at >= ys,
                                Call.started_at < ys + timedelta(days=1)).scalar() or 0) if ids else 0
    quals = [c["yesterdayQuality"] for c in cards if c["yesterdayQuality"] is not None]
    avg_quality = round(sum(quals) / len(quals), 1) if quals else None
    pcts = [c["achievementPct"] for c in cards if c["achievementPct"] is not None]
    team_pct = round(sum(pcts) / len(pcts)) if pcts else None
    # MTD orders from the Sales Tracker (the source of truth) — matched to this team's reps.
    # Call-outcome logging is brand new and still filling up, so it isn't used for this figure.
    orders_mtd = 0
    try:
        from ..salesiq import sales, fincal
        from ..salesiq.roles import user_agent_match
        if sales.configured():
            cur = fincal.current_sales_month(asof)
            placed = [o for o in sales.orders_for(cur["year"], cur["month"]) if o.get("placed")]
            orders_mtd = sum(1 for o in placed
                             if any(user_agent_match(u, o.get("agent")) for u in reps))
    except Exception:
        orders_mtd = 0
    return {
        "reps": len(reps),
        "totalCallsYesterday": int(total_calls_yday),
        "avgQualityYesterday": avg_quality,
        "teamAchievementPct": team_pct,
        "ordersMTD": int(orders_mtd),
    }


def _deals(db, reps: list[User], asof: date) -> list[dict]:
    """Open opportunities across the team the manager should help push to signing. Sourced from
    BOTH a logged warm outcome (interested / callback) AND AI signals on real conversations —
    positive customer sentiment or an extracted commitment (proposal / next step / callback /
    email promised) — so genuine warm calls surface even when the rep didn't log an outcome.
    (Lemlist/Apollo engagement enrichment is added in Stage 2.)"""
    from sqlalchemy.orm import joinedload
    from sqlalchemy import or_
    ids = [u.id for u in reps]
    if not ids:
        return []
    since = datetime.combine(asof - timedelta(days=21), time.min)
    calls = (db.query(Call).options(joinedload(Call.analysis), joinedload(Call.host))
             .outerjoin(CallAnalysis, CallAnalysis.call_id == Call.id)
             .filter(Call.host_id.in_(ids), Call.status == "completed", Call.started_at >= since,
                     or_(Call.outcome.in_(["interested", "callback"]),
                         CallAnalysis.sentiment == "positive"))
             .order_by(Call.started_at.desc()).all())
    seen, deals = set(), []
    for c in calls:
        # Skip voicemails / no-answers — a real warm conversation isn't tiny. Only drop calls whose
        # duration is KNOWN to be short (don't nuke calls that simply have no duration recorded).
        if c.duration_sec is not None and c.duration_sec < 45:
            continue
        fu = (c.analysis.followups or {}) if c.analysis else {}
        proposal = fu.get("proposal_needed") or ""
        commitment = proposal or fu.get("next_step") or fu.get("callback") or fu.get("email_promised")
        warm = (c.outcome in ("interested", "callback")
                or (c.analysis and c.analysis.sentiment == "positive") or bool(commitment))
        if not warm:
            continue
        co = (c.customer_company or c.customer_name or "Unknown").strip()
        key = (c.host_id, co.lower())
        if key in seen:
            continue
        seen.add(key)
        rep = c.host.name if c.host else "Rep"
        is_callback = c.outcome == "callback" or bool(fu.get("callback"))
        age = (asof - c.started_at.date()).days
        if proposal:
            tag, action, score = "Proposal due", f"Proposal outstanding — make sure {rep} builds and sends it.", 100
        elif is_callback:
            tag, action, score = "Callback owed", f"{rep} owes a callback — check it's booked.", 70
        else:
            tag, action, score = "Warm", f"{rep} should follow up to move this forward.", 60
        # Momentum: heating up if the warm signal is fresh, cooling if it's aging without progress.
        momentum = "up" if age <= 3 else ("down" if age >= 10 else "flat")
        deals.append({"company": co, "rep": rep, "userId": c.host_id, "callId": c.id,
                      "dealKey": f"{c.host_id}:{co.lower()}", "momentum": momentum,
                      "tag": tag, "action": action, "proposal": proposal, "ageDays": age,
                      "_score": score - age})
    deals.sort(key=lambda d: -d["_score"])
    for d in deals:
        d.pop("_score", None)
    deals = deals[:12]
    # Attach the persisted "Being Actioned — {manager}" highlights (visible to every manager).
    keys = [d["dealKey"] for d in deals]
    if keys:
        from ...models import DealHighlight
        hl = {h.deal_key: h for h in db.query(DealHighlight)
              .filter(DealHighlight.deal_key.in_(keys), DealHighlight.actioned.is_(True)).all()}
        for d in deals:
            h = hl.get(d["dealKey"])
            d["actioned"] = bool(h)
            d["actionedBy"] = h.actioned_by_name if h else None
    return deals


def _coaching_priority(db, asof: date):
    """The single team-wide skill that, if coached, would move the needle most — the metric
    furthest outside the winning-call band across the team's last 30 days."""
    from .common import team_averages, DNA_BANDS
    ta = team_averages(db, days=30, asof=datetime.combine(asof, time.min))
    cands = []
    q = ta.get("questions")
    if q is not None and q < DNA_BANDS["questions"][0]:
        cands.append(("asking more discovery questions", DNA_BANDS["questions"][0] - q,
                      f"the team averages {q} questions a call vs a {DNA_BANDS['questions'][0]}+ target"))
    t = ta.get("talk_ratio")
    if t is not None and t > DNA_BANDS["talk_ratio"][1]:
        cands.append(("listening more — talk ratio", t - DNA_BANDS["talk_ratio"][1],
                      f"the team talks {round(t)}% of the call vs a sub-{DNA_BANDS['talk_ratio'][1]}% target"))
    it = ta.get("interruptions")
    if it is not None and it > DNA_BANDS["interruptions"][1] + 0.5:
        cands.append(("interrupting prospects less", it - DNA_BANDS["interruptions"][1],
                      f"the team interrupts {it} times a call on average"))
    if not cands:
        return None
    cands.sort(key=lambda c: -c[1])
    label, _, why = cands[0]
    return {"skill": label, "detail": why,
            "action": f"A short group session on {label} this week would lift conversion most — {why}."}


def command_centre(db, manager: User, team: str | None = None) -> dict:
    asof = date.today()
    reps = _team_reps(db, team)
    cards = [_rep_card(db, u, asof) for u in reps]
    alerts = _alerts(db, cards, asof)
    aggregates = _team_aggregates(db, cards, reps, asof)
    deals = _deals(db, reps, asof)
    try:
        coaching_priority = _coaching_priority(db, asof)
    except Exception:
        coaching_priority = None
    # Latest monthly/quarterly review videos for the team (only when any exist — i.e. first week
    # of the month onward). Managers can watch each rep's intelligent review here.
    reviews = []
    try:
        from .videos import latest_review, video_payload
        for u in reps:
            v = latest_review(db, u)
            if v:
                reviews.append({**video_payload(v), "repName": u.short_name or u.name,
                                "avatarColor": getattr(u, "avatar_color", None)})
    except Exception:
        pass
    return {
        "meta": {"computedAt": datetime.utcnow().isoformat() + "Z",
                 "manager": manager.name, "team": team or "all",
                 "date": asof.strftime("%A %d %B %Y")},
        "aggregates": aggregates,
        "deals": deals,
        "alerts": alerts,
        "reviews": reviews,
        "coachingPriority": coaching_priority,
        "reps": cards,
    }
