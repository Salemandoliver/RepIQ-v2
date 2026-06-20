"""The rep/BC co-pilot — an action-first daily plan built from yesterday's calls.

Fast: the AI extraction (coaching + commitments) already ran in the pipeline, so this is
just aggregation. Service calls and voicemails are excluded from coaching/commitments."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import joinedload

from ...models import Call, User
from ..salesiq.roles import role_for_user
from .common import _avg_scores, quality_100
from .morning import _section_c


def _yesterday(asof: date):
    y = asof - timedelta(days=1)
    while y.weekday() >= 5:          # Monday looks back to Friday
        y -= timedelta(days=1)
    s = datetime.combine(y, time.min)
    return s, s + timedelta(days=1), y


def _is_non_sales(activity_type: str | None) -> bool:
    at = (activity_type or "").lower()
    return "service" in at or "voicemail" in at or "voice mail" in at


def daily_plan(db, user: User) -> dict:
    asof = date.today()
    role = role_for_user(db, user) or "rep"
    ys, ye, yday = _yesterday(asof)

    calls = (db.query(Call).options(joinedload(Call.analysis))
             .filter(Call.host_id == user.id, Call.started_at >= ys, Call.started_at < ye,
                     Call.status == "completed")
             .order_by(Call.started_at.desc()).all())
    sales_calls = [c for c in calls if not _is_non_sales(c.activity_type)]
    qmap = _avg_scores(db, [c.id for c in sales_calls])

    promises, missing, proposals, focus_pool, improvements = [], [], [], [], []
    orders = 0
    for c in sales_calls:
        co = c.customer_company or c.customer_name or "Unknown"
        if c.outcome == "order_placed":
            orders += 1
        a = c.analysis
        if not a:
            continue
        f = a.followups or {}
        if f.get("callback"):
            promises.append({"type": "callback", "company": co, "callId": c.id,
                             "text": f["callback"], "toNumber": c.to_number})
        if f.get("email_promised"):
            promises.append({"type": "email", "company": co, "callId": c.id,
                             "text": f["email_promised"]})
        if f.get("missing_info"):
            missing.append({"company": co, "callId": c.id, "text": f["missing_info"]})
        if f.get("proposal_needed"):
            proposals.append({"company": co, "callId": c.id, "text": f["proposal_needed"]})
        q = quality_100(qmap[c.id]) if c.id in qmap else None
        if a.one_thing:
            focus_pool.append((q if q is not None else 999, a.one_thing))
        improvements += (a.improvements or [])

    coaching_focus = sorted(focus_pool, key=lambda x: x[0])[0][1] if focus_pool else None
    quick_wins = list(dict.fromkeys(improvements))[:2]

    best = None
    if qmap:
        bid = max(qmap, key=qmap.get)
        bc = next((c for c in sales_calls if c.id == bid), None)
        if bc:
            best = {"company": bc.customer_company or bc.customer_name or "a call",
                    "score": round(quality_100(qmap[bid]))}

    first = (user.name or "there").split()[0]
    try:                                       # prefer the person's "known as" name
        from ...modules.hr.services import display_first_name
        first = display_first_name(db, user)
    except Exception:
        pass
    n = len(sales_calls)
    on_leave_yday = []
    try:
        from ...modules.hr import leave as hr_leave
        on_leave_yday = hr_leave.user_leave(db, user.id, yday, yday)
    except Exception:
        on_leave_yday = []
    if on_leave_yday and n == 0:
        lt = (on_leave_yday[0].get("type") or "leave").lower()
        brief = (f"Good morning, {first}. You were on {lt} on {yday.strftime('%a %d %b')} — "
                 "nothing to review from yesterday. Welcome back; here's your plan for today.")
    elif n == 0:
        brief = (f"Good morning, {first}. No sales calls logged yesterday — a clean slate "
                 "today. Start with your priority list below.")
    else:
        bits = [f"{n} conversation" + ("" if n == 1 else "s")]
        if orders:
            bits.append(f"{orders} order" + ("" if orders == 1 else "s") + " won")
        if promises:
            bits.append(f"{len(promises)} follow-up" + ("" if len(promises) == 1 else "s") + " to keep")
        brief = f"Good morning, {first}. Yesterday: " + ", ".join(bits) + "."
        if proposals:
            brief += f" {len(proposals)} proposal" + ("" if len(proposals) == 1 else "s") + " to build."
        if best:
            brief += f" Your strongest call was {best['company']} ({best['score']}/100)."

    return {
        "meta": {"userId": user.id, "name": user.name, "role": role,
                 "date": asof.strftime("%A %d %B %Y"), "yesterday": yday.isoformat(),
                 "computedAt": datetime.utcnow().isoformat() + "Z"},
        "brief": brief,
        "yesterdayCalls": n, "ordersYesterday": orders,
        "promises": promises, "missingInfo": missing, "proposals": proposals,
        "coachingFocus": coaching_focus, "quickWins": quick_wins,
        "momentum": _section_c(db, user, role),
        "priorityCalls": {
            "available": False,
            "message": ("Your priority call list — prospects assigned round-robin and ranked "
                        "by Apollo buying intent, Lemlist engagement and Companies House "
                        "triggers — is being wired up next."),
            "items": [],
        },
    }


# --------------------------------------------------------------- Ask CallIQ (dashboard)
def _window_bounds(scope: str, asof: date):
    """(start, end, label) for the Ask scope: yesterday | week | month."""
    if scope == "month":
        start = datetime.combine(asof.replace(day=1), time.min)
        return start, datetime.combine(asof + timedelta(days=1), time.min), "this month"
    if scope == "week":
        monday = asof - timedelta(days=asof.weekday())
        return (datetime.combine(monday, time.min),
                datetime.combine(asof + timedelta(days=1), time.min), "this week")
    ys, ye, _ = _yesterday(asof)
    return ys, ye, "yesterday"


def _calls_context(db, user_ids, start, end, label, limit=50, team=False) -> str:
    calls = (db.query(Call).options(joinedload(Call.analysis), joinedload(Call.host))
             .filter(Call.host_id.in_(user_ids), Call.started_at >= start, Call.started_at < end,
                     Call.status == "completed")
             .order_by(Call.started_at.desc()).limit(limit).all())
    lines = []
    for c in calls:
        a = c.analysis
        co = c.customer_company or c.customer_name or "Unknown"
        who = (c.host.name + ": ") if (team and c.host) else ""
        bits = [f"- {who}{co} ({c.activity_type})"]
        if a:
            if a.summary_intro:
                bits.append(f"summary: {a.summary_intro}")
            f = a.followups or {}
            fu = [f"{k}: {v}" for k, v in f.items() if v]
            if fu:
                bits.append("commitments: " + "; ".join(fu))
            if a.one_thing:
                bits.append(f"coaching: {a.one_thing}")
        if c.outcome:
            bits.append(f"outcome: {c.outcome}")
        lines.append(" | ".join(bits))
    return f"CALLS ({label}, {len(calls)} shown):\n" + ("\n".join(lines) if lines else "(none)")


def _trackers_context(db, user: User, role: str) -> str:
    """The user's sales / activity / leads / holiday numbers from the trackers, so Ask CallIQ
    can answer across all of them at once (not just calls)."""
    from ..salesiq.dashboard import bc_dashboard, rep_dashboard
    from ..salesiq import trackers
    from ..salesiq.roles import user_agent_match
    out = []
    try:
        if role == "bc":
            p = bc_dashboard(db, user).get("performance", {})
            out.append(f"LEADS (you, this month): {p.get('leadsMTD')} created of {p.get('leadTarget')} target; "
                       f"{p.get('won')} signed; {p.get('f2f')} F2F; GM generated £{p.get('gmGenerated')}.")
        else:
            d = rep_dashboard(db, user, role=role)
            p = d.get("performance", {})
            out.append(f"SALES (this month): SOV £{p.get('sovMTD')} of £{p.get('sovTarget')} ({p.get('sovPct')}%); "
                       f"GM £{p.get('gmMTD')}; {p.get('ordersMTD')} orders; {p.get('pendingCount')} pending "
                       f"(£{p.get('pendingValueSov')}). Pillars — data £{(p.get('connectivity') or {}).get('mtd')}, "
                       f"cloud £{(p.get('cloud') or {}).get('mtd')}, mobile £{(p.get('mobile') or {}).get('mtd')}.")
            a = d.get("activity", {})
            if a.get("connected"):
                out.append(f"ACTIVITY (this month): {a.get('dialsMTD')} dials (today {a.get('dialsToday')}); "
                           f"talk {round((a.get('talkTimeMTDSec') or 0) / 3600, 1)}h; conv→order {a.get('convToOrderRate')}.")
            lg = d.get("leads", {})
            if lg.get("connected"):
                b = lg.get("statusBreakdown", {})
                out.append(f"LEADS RECEIVED (this month): {lg.get('totalReceived')} — {b.get('won')} won, "
                           f"{b.get('inProgress')} in progress, {b.get('rejected')} rejected.")
            op = d.get("opps", {})
            if op.get("connected"):
                out.append(f"OPPORTUNITIES (this month): {op.get('oppsMTD')} of {op.get('target')} target; "
                           f"{op.get('f2fMTD')} F2F.")
        from ...modules.hr import leave as hr_leave
        today = date.today()
        mine = sorted({r["date"] for r in hr_leave.user_leave(db, user.id, start=today)})
        if mine:
            out.append("YOUR BOOKED LEAVE (upcoming): "
                       + ", ".join(x.strftime("%a %d %b") for x in mine[:14]) + ".")
    except Exception:
        pass
    return "\n".join(out)


def _team_holiday_context(db) -> str:
    from ...modules.hr import leave as hr_leave
    try:
        today = date.today()
        wk_end = today + timedelta(days=6)
        week_rows = hr_leave.leave_rows(db, today, wk_end)
        off_today = sorted({r["name"] for r in week_rows if r["date"] == today})
        off_week: dict = {}
        for r in week_rows:
            off_week[r["name"]] = off_week.get(r["name"], 0) + 1
        lines = []
        if off_today:
            lines.append("OFF TODAY: " + ", ".join(off_today) + ".")
        if off_week:
            lines.append("OFF THIS WEEK: " + ", ".join(f"{n} ({c}d)" for n, c in off_week.items()) + ".")
        return "\n".join(lines)
    except Exception:
        return ""


def _manager_ask_context(cc: dict) -> str:
    ag = cc.get("aggregates", {})
    lines = [f"TEAM TODAY: {ag.get('reps')} reps · team achievement {ag.get('teamAchievementPct')}% · "
             f"{ag.get('ordersMTD')} orders this month · {ag.get('totalCallsYesterday')} calls yesterday · "
             f"avg quality {ag.get('avgQualityYesterday')}."]
    if cc.get("deals"):
        lines.append("DEALS TO PUSH:")
        for d in cc["deals"][:10]:
            lines.append(f"- {d['company']} ({d['rep']}) — {d['tag']}: {d['action']}")
    if cc.get("alerts"):
        lines.append("ALERTS:")
        lines += [f"- {a['text']}" for a in cc["alerts"][:12]]
    if cc.get("coachingPriority"):
        lines.append("TEAM COACHING PRIORITY: " + cc["coachingPriority"]["action"])
    lines.append("REPS: " + "; ".join(
        f"{r['name']} (quality {r.get('yesterdayQuality')}, {r.get('achievementPct')}% target, {r.get('trend')})"
        for r in cc.get("reps", [])))
    return "\n".join(lines)


def ask_copilot(db, user: User, question: str, scope: str = "yesterday") -> str:
    from ...pipeline.analyzer import _claude
    from ...config import settings
    role = role_for_user(db, user) or "rep"
    start, end, label = _window_bounds(scope, date.today())
    if role == "manager":
        from .team import command_centre, _team_reps
        ids = [u.id for u in _team_reps(db, None)] or [user.id]
        calls_ctx = _calls_context(db, ids, start, end, label, limit=70, team=True)
        parts = [_manager_ask_context(command_centre(db, user)), _team_holiday_context(db), calls_ctx]
        context = "\n\n".join(p for p in parts if p)
        system = (
            "You are CallIQ, a co-pilot for a sales manager at BT Local Business Oxford & Bucks "
            "(UK telecom: broadband, phone lines, mobile, cloud). You answer the manager's "
            "questions about the team — performance, sales numbers, leads, activity, who's on "
            "leave, who needs help, which deals to push to signing, and where to focus coaching. "
            "You have the team's calls, sales tracker, leads, activity and holiday data. Be "
            "brief, concrete and action-oriented. UK English. If the answer isn't in the data, "
            "say so. No preamble."
        )
        user_msg = f"MANAGER: {user.name} · scope: {label}\n\n{context}\n\nQUESTION: {question}"
    else:
        parts = [_trackers_context(db, user, role), _calls_context(db, [user.id], start, end, label)]
        context = "\n\n".join(p for p in parts if p)
        system = (
            "You are CallIQ, a personal sales co-pilot for a rep at BT Local Business Oxford & "
            "Bucks (UK telecom: broadband, phone lines, mobile, cloud). You answer the rep's "
            "questions about their own work — their calls, who to call back, what they promised, "
            "prospects, their sales numbers, leads, activity (dials/opps) and booked leave. You "
            "have their calls, sales tracker, leads, activity and holiday data — use whichever "
            "the question needs. Be brief, concrete and encouraging. UK English. If the answer "
            "isn't in the data, say so. No preamble."
        )
        user_msg = f"REP: {user.name} (role: {role}) · scope: {label}\n\n{context}\n\nQUESTION: {question}"
    return _claude(system, user_msg, settings.claude_call_model, max_tokens=900)
