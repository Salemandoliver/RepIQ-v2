"""SalesIQ Manager Intelligence view — team performance digest.

Period: week | month | quarter (default month). Assembles, from the live trackers + CallIQ:
  1. KPI strip (team GM, calls this week, BC leads, reps off pace)
  2. Sales performance vs target, grouped by team, with per-pillar attainment + pace status
  3. BC lead conversion (leads / F2F / won vs target)
  4. Activity — CallIQ daily team totals (this week) + per-rep tracker daily averages
  5/6. AI insights + coaching spotlight (Claude, cached; rule-based fallback)
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import date, datetime, timedelta

from sqlalchemy import func

from ...config import settings
from ...models import Call, Team, User
from . import fincal, sales, trackers
from .roles import role_for_user, targets_for, user_agent_match

log = logging.getLogger("calliq.salesiq.manager")

# Monthly lead target for a Business Creator (from the pay plan: 40 leads/month).
BC_MONTHLY_LEAD_TARGET = 40


# --------------------------------------------------------------- period window
def _weeks_in_month(cur: dict) -> float:
    return max(1.0, ((cur["end"] - cur["start"]).days + 1) / 7.0)


def _period_window(period: str, today: date) -> dict:
    cur = fincal.current_sales_month(today)
    anchor = date(cur["year"], cur["month"], 15)
    if period == "quarter":
        months = fincal.quarter_months(anchor)
        start = fincal.sales_month_start(*months[0])
        end = fincal.sales_month(*months[-1])["end"]
        # Full-quarter target (3 months) regardless of how far we are into it.
        factor, bc_factor = 3.0, 3.0
        label = fincal.financial_quarter(anchor)["label"] + " (QTD)"
    elif period == "week":
        wk = (today - cur["start"]).days // 7
        start = cur["start"] + timedelta(days=wk * 7)
        end = min(start + timedelta(days=6), cur["end"])
        weeks = _weeks_in_month(cur)
        factor = bc_factor = 1.0 / weeks
        months = [(cur["year"], cur["month"])]
        label = f"Week {wk + 1} · {cur['label']}"
        return {"key": "week", "label": label, "months": months, "start": start, "end": end,
                "weekTag": f"week {wk + 1}", "factor": factor, "bcFactor": bc_factor,
                "elapsedFrac": _elapsed(start, end, today), "salesMonth": cur}
    else:  # month
        months = [(cur["year"], cur["month"])]
        start, end = cur["start"], cur["end"]
        factor = bc_factor = 1.0
        label = cur["label"] + " (MTD)"
    return {"key": period if period in ("month", "quarter") else "month", "label": label,
            "months": months, "start": start, "end": end, "weekTag": None,
            "factor": factor, "bcFactor": bc_factor,
            "elapsedFrac": _elapsed(start, end, today), "salesMonth": cur}


def _elapsed(start: date, end: date, today: date) -> float:
    if today >= end:
        return 1.0
    if today < start:
        return 0.0
    return round(((today - start).days + 1) / ((end - start).days + 1), 3)


# --------------------------------------------------------------- helpers
def _pct(actual, target):
    return round(actual / target * 100) if target else None


def _pace_status(weighted_pct, elapsed_frac, sov, gm) -> dict:
    """A human pace label from weighted attainment vs how far into the period we are."""
    if sov <= 0 and gm <= 0:
        return {"label": "No orders", "tone": "zero", "icon": "🚨"}
    pace = max(0.05, elapsed_frac)
    ratio = (weighted_pct / 100) / pace if weighted_pct is not None else 0
    if ratio >= 1.0:
        return {"label": "On pace", "tone": "green", "icon": "✅"}
    if ratio >= 0.6:
        return {"label": "Below pace", "tone": "amber", "icon": "⚠"}
    if ratio >= 0.25:
        return {"label": "Off pace", "tone": "red", "icon": "🔴"}
    return {"label": "Critical", "tone": "red", "icon": "🚨"}


def _team_label(name: str | None) -> str:
    return (name or "Unassigned").strip()


_TEAM_ORDER = {"value": 0, "senior": 0, "volume": 1, "bdm": 2, "field": 2}


def _team_sort_key(label: str):
    low = label.lower()
    for k, v in _TEAM_ORDER.items():
        if k in low:
            return (v, label)
    return (5, label)


# --------------------------------------------------------------- sections
def _sales_performance(db, win: dict) -> dict:
    reps = [u for u in db.query(User).filter(User.active.is_(True)).order_by(User.name).all()
            if role_for_user(db, u) == "rep"]
    factor, elapsed, week_tag = win["factor"], win["elapsedFrac"], win["weekTag"]
    all_orders = {ym: sales.orders_for(*ym) for ym in win["months"]}

    groups: dict[str, list] = {}
    team_gm = 0.0
    off_pace = 0
    for rep in reps:
        tg = targets_for(db, rep, "rep")
        connT, cloudT, mobileT = tg["connectivity"] * factor, tg["cloud"] * factor, tg["mobile"] * factor
        totalT = connT + cloudT + mobileT
        conn = cloud = mobile = gm = 0.0
        for ym, orders in all_orders.items():
            for o in orders:
                if not o["placed"] or not user_agent_match(rep, o["agent"]):
                    continue
                if week_tag and str(o.get("week") or "").strip().lower() != week_tag:
                    continue
                conn += o["connectivity"]; cloud += o["cloud"]; mobile += o["mobile"]; gm += o["gm"]
        sov = conn + cloud + mobile
        weighted = _pct(sov, totalT)
        status = _pace_status(weighted, elapsed, sov, gm)
        if status["tone"] in ("red", "zero"):
            off_pace += 1
        team_gm += gm
        team = _team_label(rep.team.name if rep.team else None)
        groups.setdefault(team, []).append({
            "rep": rep.name, "userId": rep.id, "team": team,
            "dataPct": _pct(conn, connT), "cloudPct": _pct(cloud, cloudT),
            "mobilePct": _pct(mobile, mobileT), "weightedPct": weighted,
            "gm": round(gm, 2), "sov": round(sov, 2), "status": status,
        })
    out_groups = []
    for team in sorted(groups, key=_team_sort_key):
        rows = sorted(groups[team], key=lambda r: -(r["gm"] or 0))
        out_groups.append({"team": team, "reps": rows,
                           "gm": round(sum(r["gm"] for r in rows), 2)})
    return {"groups": out_groups, "teamGm": round(team_gm, 2), "offPace": off_pace,
            "repCount": len(reps)}


_CO_STOP = re.compile(r"\b(limited|ltd|llp|plc|uk|co|company|group|services|holdings|the|and)\b")


def _norm_co(s: str | None) -> str:
    s = re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())
    s = _CO_STOP.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def _bc_conversion(db, win: dict) -> list[dict]:
    if not trackers.leads_configured():
        return []
    start, end = win["start"], win["end"]
    lead_target = round(BC_MONTHLY_LEAD_TARGET * win["bcFactor"])
    f2f_target = max(1, round(lead_target / 5))

    # GM attribution: map placed-order company -> GM, then credit a BC for any of their
    # lead companies that matches an order (the BC sourced that deal).
    order_gm: dict[str, float] = {}
    for (y, m) in win["months"]:
        for o in sales.orders_for(y, m):
            if o.get("placed") and o.get("company"):
                k = _norm_co(o["company"])
                if k:
                    order_gm[k] = order_gm.get(k, 0.0) + o["gm"]

    agg: dict[str, dict] = {}
    for l in trackers.lead_rows():
        d = l.get("date")
        if not d or not (start <= d <= end):
            continue
        bc = l.get("bc") or "Unknown"
        e = agg.setdefault(bc, {"bc": bc, "leads": 0, "f2f": 0, "won": 0, "_cos": set()})
        e["leads"] += 1
        if l.get("f2f"):
            e["f2f"] += 1
        if l.get("signed"):
            e["won"] += 1
        co = _norm_co(l.get("company"))
        if co:
            e["_cos"].add(co)
    rows = []
    for e in agg.values():
        gm = round(sum(order_gm.get(co, 0.0) for co in e["_cos"]), 2)
        rows.append({"bc": e["bc"], "leads": e["leads"], "f2f": e["f2f"], "won": e["won"],
                     "gm": gm, "leadTarget": lead_target, "f2fTarget": f2f_target,
                     "leadPct": _pct(e["leads"], lead_target),
                     "f2fPct": _pct(e["f2f"], f2f_target),
                     "wonPct": _pct(e["won"], e["leads"])})
    rows.sort(key=lambda r: -r["leads"])
    return rows


def _activity(db, win: dict) -> dict:
    today = date.today()
    cur = win["salesMonth"]
    rep_ids = [u.id for u in db.query(User).filter(User.active.is_(True)).all()
               if role_for_user(db, u) == "rep"]

    # --- CallIQ daily team totals for the current week ---
    wk = (today - cur["start"]).days // 7
    wstart = cur["start"] + timedelta(days=wk * 7)
    # YTD-ish daily average (this sales month so far, weekdays only)
    mstart_dt = datetime(cur["start"].year, cur["start"].month, cur["start"].day)
    m_calls, m_secs = (db.query(func.count(Call.id), func.coalesce(func.sum(Call.duration_sec), 0))
                       .filter(Call.host_id.in_(rep_ids or [0]), Call.started_at >= mstart_dt).one())
    wd_elapsed = max(1, fincal.weekdays_between(cur["start"], min(today, cur["end"])))
    avg_calls = (m_calls or 0) / wd_elapsed
    daily = []
    for i in range(7):
        d = wstart + timedelta(days=i)
        if d > today or d > cur["end"]:
            break
        d0 = datetime(d.year, d.month, d.day)
        n, secs = (db.query(func.count(Call.id), func.coalesce(func.sum(Call.duration_sec), 0))
                   .filter(Call.host_id.in_(rep_ids or [0]),
                           Call.started_at >= d0, Call.started_at < d0 + timedelta(days=1)).one())
        n = int(n or 0); mins = int((secs or 0) / 60)
        vs = _pct(n, avg_calls) if avg_calls else None
        daily.append({"date": d.isoformat(), "label": d.strftime("%a %d %b"),
                      "calls": n, "talkMins": mins,
                      "vsAvgPct": (vs - 100) if vs is not None else None})

    # --- Per-rep tracker daily averages over the period months ---
    months = set(win["months"])
    per: dict[str, dict] = {}
    for r in trackers.activity_rows():
        if (r["year"], r["month"]) not in months:
            continue
        worked = bool(r.get("atWork")) or (r["dials"] or r["talkMins"] or r["opps"])
        if not worked:
            continue
        a = per.setdefault(r["agent"].lower(), {"agent": r["agent"], "team": r.get("team"),
                           "days": 0, "dials": 0.0, "talkMins": 0.0, "opps": 0.0})
        a["days"] += 1
        a["dials"] += r["dials"] or 0
        a["talkMins"] += r["talkMins"] or 0
        a["opps"] += r["opps"] or 0
    reps = []
    for a in per.values():
        d = max(1, a["days"])
        dpd, mpd, opd = a["dials"] / d, a["talkMins"] / d, a["opps"] / d
        reps.append({"agent": a["agent"], "team": a["team"], "days": a["days"],
                     "dialsPerDay": round(dpd, 1), "minsPerDay": round(mpd, 1),
                     "oppsPerDay": round(opd, 2), "profile": _profile(dpd, mpd, opd, a["days"])})
    reps.sort(key=lambda r: -r["minsPerDay"])
    return {"daily": daily, "avgCallsPerDay": round(avg_calls, 1), "reps": reps}


def _profile(dpd, mpd, opd, days) -> str:
    if days < 4:
        return "Low sample"
    if opd >= 1.8 and mpd >= 75:
        return "Strong"
    if dpd >= 25 and mpd < 55:
        return "Efficient"
    if mpd >= 70:
        return "Consistent"
    if opd < 0.6:
        return "Volatile"
    return "Developing"


def _holiday_coverage(today: date) -> dict:
    """Who's off during the upcoming working week (next Mon–Fri), from the Holiday Tracker."""
    if not trackers.holiday_configured():
        return {"connected": False}
    days_to_mon = (7 - today.weekday()) % 7 or 7
    start = today + timedelta(days=days_to_mon)
    end = start + timedelta(days=4)                       # Mon..Fri
    rows = [h for h in trackers.holiday_rows() if start <= h["date"] <= end]
    by: dict[str, dict] = {}
    for h in rows:
        e = by.setdefault(h["name"], {"name": h["name"].title(), "days": [], "fullDays": 0})
        e["days"].append({"date": h["date"].isoformat(), "label": h["date"].strftime("%a %d %b"),
                          "absence": h["label"], "half": h["half"]})
        if not h["half"]:
            e["fullDays"] += 1
    people = sorted(by.values(), key=lambda p: (-p["fullDays"], p["name"]))
    for p in people:
        kinds = {d["absence"] for d in p["days"]}
        p["absence"] = next(iter(kinds)) if len(kinds) == 1 else "Mixed"
        p["dates"] = ", ".join(d["label"] for d in p["days"])
        p["impact"] = "Full day(s) — check open opps/leads" if p["fullDays"] else "Half day — minimal impact"
    span = f"{start.strftime('%d %b')}–{end.strftime('%d %b')}"
    note = (f"{len(people)} team member(s) off next week ({span})." if people
            else f"Full team available next week ({span}).")
    return {"connected": True, "weekStart": start.isoformat(), "weekEnd": end.isoformat(),
            "span": span, "people": people, "count": len(people), "note": note}


# --------------------------------------------------------------- AI section
_ai_lock = threading.Lock()
_ai_cache: dict[str, tuple[float, dict]] = {}
_AI_TTL = 60 * 60  # 1h


def _ai_insights(win: dict, perf: dict, bc: list, activity: dict, cache_suffix: str = "all") -> dict:
    key = f"{win['key']}:{cache_suffix}:{date.today().isoformat()}"
    with _ai_lock:
        hit = _ai_cache.get(key)
        if hit and time.time() - hit[0] < _AI_TTL:
            return hit[1]
    summary = _ai_summary(win, perf, bc, activity)
    result = _ai_rule_based(win, perf, bc, activity)  # default / fallback
    if settings.anthropic_api_key:
        try:
            from ...pipeline.analyzer import _claude, _extract_json
            raw = _claude(_AI_SYSTEM, _AI_USER + "\n\nDATA:\n" + json.dumps(summary),
                          settings.claude_report_model, max_tokens=1600)
            parsed = _extract_json(raw)
            if isinstance(parsed, dict) and parsed.get("insights"):
                result = {"source": "ai",
                          "paceNote": parsed.get("paceNote") or result["paceNote"],
                          "insights": parsed.get("insights")[:5],
                          "coaching": parsed.get("coaching") or result["coaching"]}
        except Exception as e:
            log.warning("Manager AI insights failed: %s", e)
    with _ai_lock:
        _ai_cache[key] = (time.time(), result)
    return result


def _ai_summary(win, perf, bc, activity) -> dict:
    return {
        "period": win["label"], "elapsedFraction": win["elapsedFrac"],
        "teamGm": perf["teamGm"], "repsOffPace": perf["offPace"], "repCount": perf["repCount"],
        "performanceByTeam": [{"team": g["team"], "gm": g["gm"],
                               "reps": [{"rep": r["rep"], "weightedPct": r["weightedPct"],
                                         "gm": r["gm"], "status": r["status"]["label"]}
                                        for r in g["reps"]]} for g in perf["groups"]],
        "bcConversion": [{"bc": r["bc"], "leads": r["leads"], "leadPct": r["leadPct"],
                          "f2f": r["f2f"], "f2fPct": r["f2fPct"], "won": r["won"]} for r in bc],
        "activityReps": [{"agent": r["agent"], "dialsPerDay": r["dialsPerDay"],
                          "minsPerDay": r["minsPerDay"], "oppsPerDay": r["oppsPerDay"],
                          "profile": r["profile"]} for r in activity["reps"]],
    }


_AI_SYSTEM = (
    "You are a sharp UK B2B telecoms sales director analysing a team performance digest for "
    "BT Local Business Oxford & Bucks. Be specific, use the names and numbers given, and surface "
    "non-obvious patterns a manager would miss. British English. Money in GBP. No preamble.")
_AI_USER = (
    "From the DATA, return STRICT JSON only, shape:\n"
    '{"paceNote": "<=60 words on overall attainment vs pace>",\n'
    ' "insights": ["5 short, non-obvious, specific insights"],\n'
    ' "coaching": {"rep":"name","role":"team","diagnosis":"<=50 words","interventions":["2-4 actions"]}}\n'
    "Pick the coaching rep where a clear, fixable gap exists (e.g. high opps but low conversion).")


def _ai_rule_based(win, perf, bc, activity) -> dict:
    insights, paceNote = [], ""
    pace = round(win["elapsedFrac"] * 100)
    paceNote = (f"At {win['label']}, expected pace is ~{pace}%. Team GM is "
                f"£{perf['teamGm']:,.0f} with {perf['offPace']} of {perf['repCount']} reps off pace.")
    # zero reps
    zeros = [r["rep"] for g in perf["groups"] for r in g["reps"] if r["status"]["tone"] == "zero"]
    if zeros:
        insights.append(f"{len(zeros)} rep(s) have zero orders this period: {', '.join(zeros[:5])}.")
    # top GM
    allreps = [r for g in perf["groups"] for r in g["reps"]]
    if allreps:
        top = max(allreps, key=lambda r: r["gm"] or 0)
        insights.append(f"{top['rep']} leads on GM (£{top['gm']:,.0f}).")
    # BC with leads but no won
    dead = [r["bc"] for r in bc if r["leads"] >= 8 and r["won"] == 0]
    if dead:
        insights.append(f"Leads not converting for: {', '.join(dead[:4])} (8+ leads, 0 won).")
    # high opps low... (activity)
    if activity["reps"]:
        hi = max(activity["reps"], key=lambda r: r["oppsPerDay"])
        insights.append(f"{hi['agent']} creates the most opps/day ({hi['oppsPerDay']}).")
    f2f_zero = [r["bc"] for r in bc if r["f2f"] == 0 and r["leads"] > 0]
    if f2f_zero:
        insights.append(f"{len(f2f_zero)} BC(s) booked zero F2F meetings this period.")
    coach = None
    if activity["reps"]:
        cand = max(activity["reps"], key=lambda r: r["oppsPerDay"])
        coach = {"rep": cand["agent"], "role": cand.get("team") or "Sales",
                 "diagnosis": f"High opp creation ({cand['oppsPerDay']}/day) — review whether these convert to orders.",
                 "interventions": ["Review 5 most recent opps — where do they stall?",
                                   "Check proposal quality and follow-up cadence",
                                   "Shadow a top closer for contrast"]}
    return {"source": "rules", "paceNote": paceNote, "insights": insights[:5], "coaching": coach}


# --------------------------------------------------------------- entry point
def match_debug(db) -> dict:
    """Diagnose name matching: every distinct Sales-Tracker / Activity agent, which CallIQ
    rep(s) it maps to, and which reps/agents have no match (the cause of 'no orders')."""
    reps = [u for u in db.query(User).filter(User.active.is_(True)).all()
            if role_for_user(db, u) == "rep"]

    sales_agents: dict[str, int] = {}
    for orders in (sales.orders_for(y, m) for (y, m) in
                   [tuple(mn["period"]) for mn in sales.status().get("months", [])]):
        for o in orders:
            if o.get("agent"):
                sales_agents[o["agent"]] = sales_agents.get(o["agent"], 0) + 1
    sales_map = [{"agent": a, "orders": n,
                  "matchesRep": [u.name for u in reps if user_agent_match(u, a)]}
                 for a, n in sorted(sales_agents.items(), key=lambda x: -x[1])]

    act_agents = sorted({r["agent"] for r in trackers.activity_rows()}) \
        if trackers.activity_configured() else []
    act_map = [{"agent": a, "matchesRep": [u.name for u in reps if user_agent_match(u, a)]}
               for a in act_agents]

    matched_reps = {rn for row in sales_map for rn in row["matchesRep"]}
    return {
        "reps": [{"name": u.name, "shortName": getattr(u, "short_name", None),
                  "jobTitle": u.job_title, "team": (u.team.name if u.team else None),
                  "matchedSalesAgent": next((row["agent"] for row in sales_map
                                             if u.name in row["matchesRep"]), None)} for u in reps],
        "repsWithNoOrders": [u.name for u in reps if u.name not in matched_reps],
        "salesAgents": sales_map,
        "salesAgentsUnmatched": [r["agent"] for r in sales_map if not r["matchesRep"]],
        "activityAgents": act_map,
    }


def holiday_calendar_view(db, year: int, month: int, team: str | None = None) -> dict:
    """Holiday calendar grid filtered to registered (active) app users only — leavers and
    non-app names are dropped — with each person's team, plus an optional team filter."""
    grid = trackers.holiday_calendar(year, month)
    if not grid.get("connected") or not grid.get("found"):
        return {**grid, "teamsAvailable": [], "team": "all"}
    users = db.query(User).filter(User.active.is_(True)).all()
    people = []
    for p in grid.get("people", []):
        u = next((u for u in users if user_agent_match(u, p["name"])), None)
        if not u:
            continue                                  # leaver / not registered in the app
        people.append({**p, "name": u.name, "team": (u.team.name if u.team else "No team")})
    teams_available = sorted({p["team"] for p in people})
    team_l = (team or "").strip().lower()
    if team_l and team_l not in ("", "all", "all teams"):
        people = [p for p in people if p["team"].lower() == team_l]
    return {**grid, "people": people, "teamsAvailable": teams_available, "team": team_l or "all"}


def manager_dashboard(db, period: str = "month", team: str | None = None) -> dict:
    period = period if period in ("week", "month", "quarter") else "month"
    today = date.today()
    win = _period_window(period, today)
    perf = _sales_performance(db, win)
    bc = _bc_conversion(db, win)
    activity = _activity(db, win)

    # --- team filter (All / Business Creators / Value / Volume / BDM) ---
    team_l = (team or "").strip().lower()
    is_bc_view = "creator" in team_l or team_l in ("bc", "business creators")
    teams_available = sorted({g["team"] for g in perf["groups"]}, key=_team_sort_key)
    if team_l and team_l not in ("", "all", "all teams"):
        if is_bc_view:
            perf = {**perf, "groups": [], "teamGm": round(sum(r.get("gm", 0) for r in bc), 2),
                    "offPace": 0, "repCount": len(bc)}
            activity = {**activity, "reps": []}
        else:
            groups = [g for g in perf["groups"] if team_l in g["team"].lower()]
            reps_in = [r for g in groups for r in g["reps"]]
            perf = {**perf, "groups": groups,
                    "teamGm": round(sum(g["gm"] for g in groups), 2),
                    "offPace": sum(1 for r in reps_in if r["status"]["tone"] in ("red", "zero")),
                    "repCount": len(reps_in)}
            activity = {**activity,
                        "reps": [r for r in activity["reps"]
                                 if r.get("team") and team_l in r["team"].lower()]}
            bc = []  # BC conversion only shown in All / Business Creators views

    ai = _ai_insights(win, perf, bc, activity, cache_suffix=(team_l or "all"))
    calls_week = sum(d["calls"] for d in activity["daily"])
    bc_leads = sum(r["leads"] for r in bc)
    return {
        "meta": {"view": "manager", "period": win["key"], "periodLabel": win["label"],
                 "team": team_l or "all", "teamsAvailable": teams_available,
                 "elapsedPct": round(win["elapsedFrac"] * 100),
                 "financialQuarter": fincal.financial_quarter(date(win["salesMonth"]["year"],
                                                                   win["salesMonth"]["month"], 15))["label"],
                 "computedAt": datetime.utcnow().isoformat() + "Z",
                 "salesConfigured": sales.configured(),
                 "leadsConfigured": trackers.leads_configured(),
                 "activityConfigured": trackers.activity_configured(),
                 "holidayConfigured": trackers.holiday_configured()},
        "kpis": {"teamGm": perf["teamGm"], "callsThisWeek": calls_week,
                 "bcLeads": bc_leads, "repsOffPace": perf["offPace"], "repCount": perf["repCount"]},
        "performance": perf,
        "bcConversion": bc,
        "activity": activity,
        "holiday": _holiday_coverage(today),
        "intelligence": ai,
    }
