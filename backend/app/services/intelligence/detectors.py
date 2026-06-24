"""Insight detectors (Intelligence Phase 3).

Pure, deterministic functions over the facts RepIQ already captures. Each detector emits fully-formed
candidate insights (title + body + recommendation + evidence + raw metrics) so the engine works even
with no LLM. The LLM pass later only *sharpens* them — it never invents the numbers.

Thresholds live here as constants (config, not code-per-insight): tune them, the engine gets smarter.
Every insight carries a stable ``dedupe_key`` so regeneration updates one living finding rather than
spamming duplicates, and so feedback/status survive.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from ...models import CallAnalysis, CampaignMention
from .common import DNA_BANDS, averages, load_call_metrics, team_averages

MIN_CALLS = 8            # don't judge a rep on too small a sample
STRONG_DELTA = 8         # quality points week-on-window for momentum/decline
WIN_RATE_FLOOR = 0.6     # rep close-rate this fraction of team → concern

# Coaching-theme keywords → a human label, for spotting a *recurring* coaching point.
THEME_KEYWORDS = {
    "discovery": ["discovery", "open question", "qualify", "qualifying", "needs", "uncover"],
    "budget/price": ["budget", "price", "pricing", "cost", "discount", "expensive"],
    "closing": ["close", "closing", "ask for the order", "next step", "commitment"],
    "objections": ["objection", "pushback", "concern", "incumbent", "competitor"],
    "listening": ["interrupt", "talk over", "let them finish", "listening", "monologue"],
    "value": ["value", "benefit", "outcome", "roi", "why bt"],
    "rapport": ["rapport", "tone", "energy", "rushed", "pace"],
}


def _mk(scope, category, severity, signal_key, title, body, recommendation, evidence, metrics,
        subject_type=None, subject_id=None, subject_key=None, subject_name=None, period_days=30) -> dict:
    sid = subject_id if subject_id is not None else subject_key
    return {
        "scope": scope, "subject_type": subject_type, "subject_id": subject_id,
        "subject_key": subject_key, "subject_name": subject_name,
        "category": category, "severity": severity, "signal_key": signal_key,
        "title": title, "body": body, "recommendation": recommendation,
        "evidence": evidence, "metrics": metrics, "period_days": period_days,
        "dedupe_key": f"{scope}:{sid}:{category}:{signal_key}",
    }


def _call_ev(rows, key, reverse=False, n=3):
    pts = [r for r in rows if r.get(key) is not None]
    pts.sort(key=lambda r: r[key], reverse=reverse)
    return [{"type": "call", "callId": r["id"], "label": f"{r[key]} {key} · {r['date']:%d/%m}"} for r in pts[:n]]


# ----------------------------------------------------------------- rep skill gaps
def _rep_skill_signals(uid, name, ravg, team, rows, days) -> list[dict]:
    out = []
    q, tq = ravg["questions"], team.get("questions")
    qlow, qhigh = DNA_BANDS["questions"]
    if q is not None and tq and q < qlow and q < tq * 0.8:
        out.append(_mk("rep", "skill_gap", "high" if q < tq * 0.6 else "medium", "low_questions",
            f"{name} is asking too few questions",
            f"{name} averages {q} discovery questions per call against the team's {tq} (healthy range {qlow}–{qhigh}). "
            "Thin discovery means weaker qualification and more price-led calls.",
            "Agree a floor of 5 open questions before pitching; listen back to one low-discovery call together in the 1-to-1.",
            [{"type": "metric", "label": f"{q} questions/call vs team {tq}"}] + _call_ev(rows, "questions"),
            {"questions": q, "team": tq, "band": [qlow, qhigh]},
            "user", uid, None, name, days))

    inter, ti = ravg["interruptions"], team.get("interruptions")
    ilow, ihigh = DNA_BANDS["interruptions"]
    if inter is not None and inter > ihigh and ti is not None and inter > ti * 1.5:
        out.append(_mk("rep", "skill_gap", "medium", "interruptions",
            f"{name} is interrupting customers",
            f"{name} interrupts {inter} times per call vs the team's {ti} (target ≤ {ihigh}). "
            "Talking over customers shuts down the very information that closes deals.",
            "Coach a one-beat pause before responding; replay a moment where an interruption cut off buying signals.",
            [{"type": "metric", "label": f"{inter} interruptions/call vs team {ti}"}] + _call_ev(rows, "interruptions", reverse=True),
            {"interruptions": inter, "team": ti, "band": [ilow, ihigh]},
            "user", uid, None, name, days))

    tr = ravg["talk_ratio"]
    tlow, thigh = DNA_BANDS["talk_ratio"]
    if tr is not None and tr > thigh + 8:
        out.append(_mk("rep", "skill_gap", "medium", "talk_ratio_high",
            f"{name} is dominating the conversation",
            f"{name} talks {round(tr)}% of the time (healthy range {tlow}–{thigh}%). High talk-ratio calls convert worse — the customer isn't being drawn out.",
            "Set a 'sell less, ask more' goal for the week; aim to land under {0}% talk time.".format(thigh),
            [{"type": "metric", "label": f"{round(tr)}% talk ratio vs target {tlow}–{thigh}%"}] + _call_ev(rows, "talk_ratio", reverse=True),
            {"talk_ratio": tr, "band": [tlow, thigh]},
            "user", uid, None, name, days))

    fl, tf = ravg["filler"], team.get("filler")
    if fl is not None and tf is not None and fl > tf * 1.6 and fl >= 10:
        out.append(_mk("rep", "skill_gap", "low", "filler",
            f"{name}: filler words are creeping in",
            f"{name} uses ~{fl} filler words per call vs the team's {tf}. It reads as less confident, especially around price.",
            "Practise the value + price lines until they're crisp; a short script drill usually fixes this fast.",
            [{"type": "metric", "label": f"{fl} fillers/call vs team {tf}"}],
            {"filler": fl, "team": tf},
            "user", uid, None, name, days))
    return out


# ----------------------------------------------------------------- momentum / risk
def _rep_momentum_signals(uid, name, rep, ravg, team, days) -> list[dict]:
    out = []
    d = rep.get("deltaQuality")
    quality = rep.get("quality")
    if d is not None and d >= STRONG_DELTA:
        out.append(_mk("rep", "win", "positive", "improving",
            f"{name} is on the up 📈",
            f"{name}'s call quality climbed {d} points versus the previous period (now {quality}). Worth recognising — and worth understanding what changed.",
            "Call it out publicly, and ask what they changed so the rest of the team can copy it.",
            [{"type": "metric", "label": f"+{d} quality vs prior period (now {quality})"}],
            {"deltaQuality": d, "quality": quality},
            "user", uid, None, name, days))
    elif d is not None and d <= -STRONG_DELTA:
        out.append(_mk("rep", "risk", "high", "declining",
            f"{name}'s call quality is slipping",
            f"{name}'s quality fell {abs(d)} points versus the previous period (now {quality}). Early intervention stops a slide becoming a slump.",
            "Make {0} the priority of your next 1-to-1; listen to a recent call together and find the one thing to reset.".format(name.split()[0]),
            [{"type": "metric", "label": f"−{abs(d)} quality vs prior period (now {quality})"}],
            {"deltaQuality": d, "quality": quality},
            "user", uid, None, name, days))
    if rep.get("rank") == 1 and quality:
        out.append(_mk("rep", "win", "positive", "top_of_league",
            f"{name} is topping the league 🥇",
            f"{name} has the highest call quality on the team this period ({quality}).",
            "Use {0} as the exemplar — pin one of their best calls for the team to learn from.".format(name.split()[0]),
            [{"type": "metric", "label": f"#1 on call quality ({quality})"}],
            {"quality": quality, "rank": 1},
            "user", uid, None, name, days))
    return out


# ----------------------------------------------------------------- outcomes / hygiene
def _rep_outcome_signals(uid, name, ravg, team, rows, days) -> list[dict]:
    out = []
    unlogged = sum(1 for r in rows if not r["outcome"])
    if unlogged >= max(5, round(0.35 * len(rows))):
        out.append(_mk("rep", "process", "low", "outcome_hygiene",
            f"{name}: outcomes missing on {unlogged} calls",
            f"{unlogged} of {name}'s {len(rows)} recent calls have no logged outcome. Without outcomes the close-rate, pipeline and DNA models can't see their real results.",
            "Nudge {0} to one-tap the outcome after each call — 10 seconds keeps their numbers honest.".format(name.split()[0]),
            [{"type": "metric", "label": f"{unlogged}/{len(rows)} calls unlogged"}],
            {"unlogged": unlogged, "calls": len(rows)},
            "user", uid, None, name, days))
    cr, tcr = ravg["closeRate"], team.get("closeRate")
    if cr is not None and tcr and cr < tcr * WIN_RATE_FLOOR and ravg["orders"] is not None:
        out.append(_mk("rep", "risk", "medium", "low_close_rate",
            f"{name}'s close rate is lagging",
            f"{name} closes {round(cr*100)}% of logged calls vs the team's {round(tcr*100)}%. The gap usually sits in discovery or the close itself, not effort.",
            "Pinpoint where deals stall for {0} — review two 'interested but no order' calls and rehearse the ask.".format(name.split()[0]),
            [{"type": "metric", "label": f"{round(cr*100)}% close vs team {round(tcr*100)}%"}],
            {"closeRate": cr, "team": tcr},
            "user", uid, None, name, days))
    return out


# ----------------------------------------------------------------- recurring coaching theme
def _rep_theme_signals(db, uid, name, rows, days) -> list[dict]:
    ids = [r["id"] for r in rows]
    if not ids:
        return []
    things = [t or "" for (t,) in db.query(CallAnalysis.one_thing)
              .filter(CallAnalysis.call_id.in_(ids)).all()]
    counts: dict[str, int] = {}
    for t in things:
        low = t.lower()
        for theme, kws in THEME_KEYWORDS.items():
            if any(k in low for k in kws):
                counts[theme] = counts.get(theme, 0) + 1
    if not counts:
        return []
    theme, n = max(counts.items(), key=lambda kv: kv[1])
    if n < 3:
        return []
    return [_mk("rep", "coaching", "medium", f"theme_{theme}",
        f"{name}: '{theme}' keeps coming up",
        f"The same coaching point — {theme} — has surfaced on {n} of {name}'s recent calls. A recurring theme is a focused, winnable improvement.",
        f"Make {theme} the single focus for {name.split()[0]} this week; set one concrete drill and check it on the next call.",
        [{"type": "metric", "label": f"'{theme}' flagged on {n} calls"}],
        {"theme": theme, "count": n},
        "user", uid, None, name, days)]


# ----------------------------------------------------------------- rep campaign misses
def _rep_campaign_signals(db, uid, name, days, asof) -> list[dict]:
    start = (asof or datetime.utcnow()) - timedelta(days=days)
    rows = (db.query(CampaignMention.campaign_id, CampaignMention.addressed)
            .filter(CampaignMention.host_id == uid, CampaignMention.call_date >= start.date()).all())
    from ...modules.campaigns.models import Campaign
    missed: dict[str, int] = {}
    for cid, addressed in rows:
        if addressed == "missed":
            missed[cid] = missed.get(cid, 0) + 1
    out = []
    for cid, n in missed.items():
        if n < 3:
            continue
        c = db.get(Campaign, cid)
        if not c or c.deleted_at is not None or c.archived:
            continue
        cname = c.name
        out.append(_mk("rep", "campaign", "medium", f"campaign_missed_{cid}",
            f"{name} keeps missing '{cname}'",
            f"{name} didn't raise the live campaign '{cname}' on {n} relevant calls. Every missed mention is lost upside on a deal that's already in front of them.",
            f"Remind {name.split()[0]} of the talking points for '{cname}' — it's a quick win on calls they're already having.",
            [{"type": "metric", "label": f"missed on {n} calls"}, {"type": "campaign", "label": cname}],
            {"missed": n, "campaign": cname},
            "user", uid, None, name, days))
    return out


# ----------------------------------------------------------------- team-level
def _team_signals(team, days) -> list[dict]:
    out = []
    q = team.get("questions")
    qlow, qhigh = DNA_BANDS["questions"]
    if q is not None and q < qlow and team.get("calls", 0) >= 20:
        out.append(_mk("team", "skill_gap", "medium", "team_low_questions",
            "The whole team is under-asking",
            f"Team-wide discovery is averaging {q} questions per call (healthy range {qlow}–{qhigh}). When it's everyone, it's a process gap, not a person.",
            "Run a team session on discovery; consider a shared opening question framework.",
            [{"type": "metric", "label": f"team avg {q} questions (target {qlow}+)"}],
            {"questions": q, "band": [qlow, qhigh]},
            "team", 0, None, "Team", days))
    return out


def _campaign_signals(db, days) -> list[dict]:
    from ...modules.campaigns.analytics import attention
    out = []
    for c in attention(db).get("items", []):
        sev = "high" if c.get("daysLeft", 99) <= 1 else "medium"
        flags = ", ".join(c.get("flags", []))
        adoption = f" at {c['rate']}% adoption" if c.get("rate") is not None else ""
        out.append(_mk("campaign", "campaign", sev, "laggard",
            f"Campaign '{c['name']}' needs a push",
            f"'{c['name']}' is flagged: {flags}. It tracked {c.get('calls', 0)} calls{adoption}.",
            "Nudge the team on the talking points, or extend/close the campaign if it's run its course.",
            [{"type": "campaign", "label": c["name"]}, {"type": "metric", "label": flags}],
            {"rate": c.get("rate"), "calls": c.get("calls"), "daysLeft": c.get("daysLeft")},
            "campaign", None, str(c["id"]), c["name"], days))
    return out


def _forecast_signals(db, asof) -> list[dict]:
    """Weekly-forecast signals — reliability is a first-class performance dimension, so it produces
    insights like every other facet. Not gated by call count (a rep can owe a forecast regardless)."""
    out: list[dict] = []
    try:
        from ...modules.forecast import services as fc
    except Exception:
        return out
    aod = asof.date() if hasattr(asof, "date") else asof
    try:
        reps = fc.eligible_reps(db)
    except Exception:
        return out
    for u in reps:
        try:
            sig = fc.rep_signal(db, u, aod)
        except Exception:
            continue
        uid, name = u.id, sig["name"]
        if sig["notSubmitted"]:
            out.append(_mk("rep", "process", "medium", "forecast_missing",
                f"{name} hasn't set this week's forecast",
                f"No Data/Cloud/Mobile forecast submitted for {sig['week']}.",
                "Nudge them to commit their weekly forecast — it drives their reliability and the team view.",
                [], {"week": sig["week"]}, subject_type="user", subject_id=uid, subject_name=name, period_days=7))
        if sig["chronicMiss"]:
            out.append(_mk("rep", "risk", "high", "forecast_chronic_miss",
                f"{name} is consistently missing forecast",
                f"Hit forecast in only {sig['hitCount']} of the last {sig['weeks']} weeks (reliability {sig['reliabilityScore']}/100).",
                "1-to-1 on forecasting: over-optimistic, sandbagged, or an activity gap? Agree a realistic, owned number.",
                [], {"reliability": sig["reliabilityScore"], "hits": sig["hitCount"], "weeks": sig["weeks"]},
                subject_type="user", subject_id=uid, subject_name=name))
        elif sig["strong"]:
            out.append(_mk("rep", "win", "positive", "forecast_reliable",
                f"{name} is a reliable forecaster",
                f"Reliability {sig['reliabilityScore']}/100 — hit forecast {sig['hitCount']} of the last {sig['weeks']} weeks.",
                "Recognise it; have them share how they forecast and pace the week.",
                [], {"reliability": sig["reliabilityScore"]},
                subject_type="user", subject_id=uid, subject_name=name))
        if sig["sandbagger"]:
            off = 100 - (sig["components"].get("accuracy") or 0)
            out.append(_mk("rep", "risk", "medium", "forecast_sandbagging",
                f"{name} may be sandbagging the forecast",
                f"Hits the number most weeks but lands ~{off}% off it — habitually under-forecasting.",
                "Coach toward an honest forecast: low-balling then beating it distorts the team view and dents accuracy.",
                [], {"accuracy": sig["components"].get("accuracy")},
                subject_type="user", subject_id=uid, subject_name=name))
        if sig["behindPace"] and sig["thisWeekPct"] is not None:
            out.append(_mk("rep", "risk", "medium", "forecast_behind_pace",
                f"{name} is behind forecast this week",
                f"At {round(sig['thisWeekPct'])}% with the week ~{sig['expectedPct']}% through.",
                "Check today's plan covers the gap — which warm Data/Cloud/Mobile deals can close it?",
                [], {"pct": sig["thisWeekPct"], "expected": sig["expectedPct"]},
                subject_type="user", subject_id=uid, subject_name=name, period_days=7))
    return out


def run_detectors(db, days: int = 30, asof: datetime | None = None) -> list[dict]:
    """Produce all candidate insights for the current window."""
    asof = asof or datetime.utcnow()
    from .benchmarks import league
    lg = league(db, days=days, asof=asof)
    team = team_averages(db, days=days, asof=asof)
    start = asof - timedelta(days=days)

    out: list[dict] = []
    out += _team_signals(team, days)
    out += _campaign_signals(db, days)
    out += _forecast_signals(db, asof)

    for rep in lg["reps"]:
        uid, name = rep["userId"], rep["name"] or "Rep"
        rows = load_call_metrics(db, uid, start, asof)
        if len(rows) < MIN_CALLS:
            continue
        ravg = averages(rows)
        out += _rep_skill_signals(uid, name, ravg, team, rows, days)
        out += _rep_momentum_signals(uid, name, rep, ravg, team, days)
        out += _rep_outcome_signals(uid, name, ravg, team, rows, days)
        out += _rep_theme_signals(db, uid, name, rows, days)
        out += _rep_campaign_signals(db, uid, name, days, asof)
    return out
