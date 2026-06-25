"""Feature 8 — AI Performance Videos (weekly rep/BC). Three stages:
  1. Data compilation — last week's performance into a payload.
  2. Script generation — Claude writes a short, positive, coaching script (Type 1 structure).
  3. Render — Higgsfield turns the script into a presenter video (when configured); otherwise
     the rep/manager sees the written weekly briefing (the brief's documented fallback).
The week's video is cached in the DB and stays available all week.
Monthly Achievement videos (Type 3) are intentionally NOT built yet."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, time, timedelta

from ...config import settings
from ...models import Call, PerformanceVideo, User
from ..salesiq.roles import role_for_user
from .common import averages, load_call_metrics
from .morning import _section_c

log = logging.getLogger("calliq.videos")


def _this_monday(asof: date) -> date:
    return asof - timedelta(days=asof.weekday())


def _gbp(n) -> str:
    return "£0" if not n else "£" + format(int(round(n)), ",")


def _reflection_commitments(db, user: User) -> list:
    """The rep's commitments from their most recent completed review reflection — so the next video
    can acknowledge how they're tracking, closing the coaching loop."""
    try:
        from ...modules.reflections import services as _rf
        return _rf.reflection_signal(db, user).get("openCommitments") or []
    except Exception:
        return []


def weekly_payload(db, user: User, role: str) -> dict:
    """Compile last week's performance for the script."""
    asof = date.today()
    this_mon = _this_monday(asof)
    lw_start = datetime.combine(this_mon - timedelta(days=7), time.min)
    lw_end = datetime.combine(this_mon, time.min)
    pw_start = lw_start - timedelta(days=7)

    rows = load_call_metrics(db, user.id, lw_start, lw_end)
    prior = load_call_metrics(db, user.id, pw_start, lw_start)
    agg, pagg = averages(rows), averages(prior)

    strengths, improvements, one_things = [], [], []
    if rows:
        for c in db.query(Call).filter(Call.id.in_([r["id"] for r in rows])).all():
            if c.analysis:
                strengths += (c.analysis.strengths or [])
                improvements += (c.analysis.improvements or [])
                if c.analysis.one_thing:
                    one_things.append(c.analysis.one_thing)

    from collections import Counter
    top_strength = Counter(strengths).most_common(1)
    top_focus = Counter(improvements).most_common(1)

    # a warm opportunity from last week (interested / callback)
    warm = (db.query(Call).filter(Call.host_id == user.id, Call.started_at >= lw_start,
                                   Call.started_at < lw_end,
                                   Call.outcome.in_(["interested", "callback"]))
            .order_by(Call.started_at.desc()).first())
    opportunity = (warm.customer_company or warm.customer_name) if warm else None

    mtd = _section_c(db, user, role)
    forecast = None
    try:
        from ...modules.forecast import services as _fc
        if _fc.is_rep(db, user):
            s = _fc.rep_signal(db, user)
            forecast = {"summary": s["summary"], "reliabilityScore": s["reliabilityScore"],
                        "weeksTracked": s["weeks"], "hits": s["hitCount"], "thisWeekPct": s["thisWeekPct"]}
    except Exception:
        pass
    return {
        "weekStart": this_mon.isoformat(),
        "reflectionCommitments": _reflection_commitments(db, user),
        "lastWeek": {
            "calls": agg["calls"], "priorCalls": pagg["calls"],
            "quality": agg["quality"], "priorQuality": pagg["quality"],
            "orders": agg["orders"], "closeRate": agg["closeRate"],
        },
        "topStrength": top_strength[0][0] if top_strength else None,
        "topFocus": top_focus[0][0] if top_focus else None,
        "oneThing": one_things[0] if one_things else None,
        "opportunity": opportunity,
        "forecast": forecast,
        "monthly": mtd,
    }


# ======================================================================================
# Monthly / quarterly performance REVIEW (Type 3). A deeper, intelligent look-back generated
# on the first Monday of each BT sales month (and a quarterly one at quarter start). Presented
# by Gary (the sales director's HeyGen avatar). Covers the period that just ENDED.
# ======================================================================================
def is_first_monday_of_sales_month(asof: date) -> bool:
    """True when ``asof`` is the BT sales-month start (which is always a Monday = the first
    Monday of that sales month)."""
    from ..salesiq import fincal
    return asof == fincal.current_sales_month(asof)["start"]


def _sales_month_before(sm: dict):
    from ..salesiq import fincal
    return fincal.current_sales_month(sm["start"] - timedelta(days=1))


def _month_metrics(db, user: User, role: str, sm: dict) -> dict:
    """Call activity + SOV/leads achievement for one finished sales month."""
    from ..salesiq.dashboard import bc_dashboard, rep_dashboard
    start = datetime.combine(sm["start"], time.min)
    end = datetime.combine(sm["end"] + timedelta(days=1), time.min)
    rows = load_call_metrics(db, user.id, start, end)
    agg = averages(rows)
    mkey = f"{sm['year']:04d}-{sm['month']:02d}"
    perf = {}
    try:
        perf = (bc_dashboard(db, user, month=mkey) if role == "bc"
                else rep_dashboard(db, user, role=role, month=mkey)).get("performance", {})
    except Exception:
        log.exception("review dashboard fetch failed for %s %s", user.id, mkey)
    return {"label": sm["label"], "calls": agg["calls"], "quality": agg["quality"],
            "talkRatio": agg["talk_ratio"], "questions": agg["questions"],
            "orders": agg["orders"], "perf": perf, "_ids": [r["id"] for r in rows]}


def review_payload(db, user: User, role: str, asof: date, period: str) -> dict:
    """Compile the just-ended month (or quarter) for the intelligent review script."""
    from collections import Counter
    from ..salesiq import fincal
    cur = fincal.current_sales_month(asof)
    prior = _sales_month_before(cur)               # the month that just ended
    if period == "quarter":
        sms = [prior]
        p = prior
        for _ in range(2):
            p = _sales_month_before(p)
            sms.insert(0, p)
        period_label = fincal.financial_quarter(date(prior["year"], prior["month"], 15))["label"]
        before = None
    else:
        sms = [prior]
        period_label = prior["label"]
        before = _month_metrics(db, user, role, _sales_month_before(prior))
    months = [_month_metrics(db, user, role, sm) for sm in sms]

    ids = [i for m in months for i in m["_ids"]]
    strengths, focus, one_things = [], [], []
    if ids:
        for c in db.query(Call).filter(Call.id.in_(ids)).all():
            if c.analysis:
                strengths += (c.analysis.strengths or [])
                focus += (c.analysis.improvements or [])
                if c.analysis.one_thing:
                    one_things.append(c.analysis.one_thing)
    top_strength = Counter(strengths).most_common(2)
    top_focus = Counter(focus).most_common(2)

    total_calls = sum(m["calls"] or 0 for m in months)
    total_orders = sum(m["orders"] or 0 for m in months)
    sov = sum((m["perf"].get("sovMTD") or 0) for m in months)
    sov_target = sum((m["perf"].get("sovTarget") or 0) for m in months)
    last_perf = months[-1]["perf"]
    return {
        "period": period, "periodLabel": period_label,
        "monthly": [{"label": m["label"], "calls": m["calls"], "quality": m["quality"],
                     "orders": m["orders"], "talkRatio": m["talkRatio"], "questions": m["questions"],
                     "sov": m["perf"].get("sovMTD"), "sovPct": m["perf"].get("sovPct"),
                     "leads": m["perf"].get("leadsMTD"), "gm": m["perf"].get("gmGenerated")}
                    for m in months],
        "totals": {"calls": total_calls, "orders": total_orders, "sov": round(sov),
                   "sovTarget": round(sov_target),
                   "sovPct": round(100 * sov / sov_target) if sov_target else None,
                   "leads": sum((m["perf"].get("leadsMTD") or 0) for m in months) if role == "bc" else None,
                   "gm": round(sum((m["perf"].get("gmGenerated") or 0) for m in months)) if role == "bc" else None,
                   "avgQuality": months[-1]["quality"]},
        "priorMonth": ({"calls": before["calls"], "quality": before["quality"], "orders": before["orders"]}
                       if before else None),
        "topStrengths": [s for s, _ in top_strength],
        "topFocus": [f for f, _ in top_focus],
        "coachingPoints": one_things[:3],
        "predictor": (last_perf.get("predictor") or {}),
        "forecast": _forecast_for_review(db, user),
        "reflectionCommitments": _reflection_commitments(db, user),
    }


def _forecast_for_review(db, user: User) -> dict | None:
    try:
        from ...modules.forecast import services as _fc
        if not _fc.is_rep(db, user):
            return None
        s = _fc.rep_signal(db, user)
        return {"summary": s["summary"], "reliabilityScore": s["reliabilityScore"],
                "band": s["reliabilityBand"], "weeksTracked": s["weeks"], "hits": s["hitCount"]}
    except Exception:
        return None


def _review_script_prompt(user: User, role: str, p: dict) -> tuple[str, str]:
    name = (user.name or "there").split()[0]
    period = "quarter" if p.get("period") == "quarter" else "month"
    t = p.get("totals") or {}
    months = p.get("monthly") or []
    trend = " → ".join(f"{m['label'].split()[0]}: q{m.get('quality')}, {m.get('orders')} orders"
                       for m in months)
    if role == "bc":
        ach = f"Leads: {t.get('leads')}; GM generated £{t.get('gm')}; {t.get('calls')} conversations."
    else:
        ach = (f"SOV £{t.get('sov'):,} of £{t.get('sovTarget'):,} target ({t.get('sovPct')}%); "
               f"{t.get('orders')} orders; {t.get('calls')} conversations; avg quality {t.get('avgQuality')}.")
    data = (
        f"Rep: {user.name} ({role}). Reviewing the {period} just ended: {p.get('periodLabel')}.\n"
        f"ACHIEVEMENT: {ach}\n"
        f"MONTH-BY-MONTH: {trend}\n"
        f"PRIOR MONTH (for trajectory): {p.get('priorMonth')}\n"
        f"RECURRING STRENGTHS: {', '.join(p.get('topStrengths') or []) or 'n/a'}\n"
        f"RECURRING FOCUS AREAS: {', '.join(p.get('topFocus') or []) or 'n/a'}\n"
        f"COACHING THEMES: {', '.join(p.get('coachingPoints') or []) or 'n/a'}\n"
        f"FORECAST RELIABILITY: {(p.get('forecast') or {}).get('summary') or 'n/a'}\n"
        f"THEIR LAST REFLECTION COMMITMENTS: {'; '.join(p.get('reflectionCommitments') or []) or 'n/a'}\n"
        f"PROJECTION: {p.get('predictor')}"
    )
    system = (
        "You are Gary, sales director at BT Local Business Oxford & Bucks (UK telecom), recording a "
        f"personal {period.upper()} performance REVIEW video for ONE rep. This is NOT a stats readout "
        "— the rep already knows their numbers. Be genuinely insightful: identify the ONE pattern or "
        "trajectory that matters most across the period, explain what's driving it, and give the single "
        "strategic shift that would change their next " + period + ". Use at most two numbers, only as "
        "evidence — never list figures. Tone: warm, direct, respectful — a sharp director who has "
        "studied their period and believes in them. Never punishing. UK English, second person. "
        "~120–170 words. Structure: greet by first name; the headline pattern (insight, not a number); "
        "why it's happening; the ONE thing to change; a motivating, forward-looking close into the new "
        + period + ". If THEIR LAST REFLECTION COMMITMENTS are present, acknowledge whether they "
        "followed through — it shows you heard what they committed to. Only use the data given — invent nothing. "
        "Return STRICT JSON: {\"title\":\"...\",\"headline\":\"one-line summary\",\"script\":\"the spoken script\"}."
    )
    user_msg = f"Write {name}'s {period} review script from this data:\n\n{data}"
    return system, user_msg


def _script_prompt(user: User, role: str, p: dict) -> tuple[str, str]:
    name = (user.name or "there").split()[0]
    m = p.get("monthly") or {}
    if role == "bc":
        target_line = (f"Leads this month: {m.get('leadsMTD')} of {m.get('leadTarget')} target; "
                       f"GM generated {_gbp(m.get('gmGenerated'))}.")
    else:
        target_line = (f"This month: SOV {_gbp(m.get('sovMTD'))} of {_gbp(m.get('sovTarget'))} "
                       f"({m.get('sovPct')}%), {m.get('ordersMTD')} orders, {m.get('daysRemaining')} "
                       f"selling days left; projected finish {((m.get('predictor') or {}).get('projectedFinishPct'))}%.")
    lw = p["lastWeek"]
    fc = p.get("forecast") or {}
    fc_line = f"\nWEEKLY FORECAST: {fc.get('summary')}" if fc else ""
    rc = p.get("reflectionCommitments") or []
    rc_line = ("\nTHEIR LAST REFLECTION COMMITMENTS: " + "; ".join(rc)) if rc else ""
    data = (
        f"Rep: {user.name} ({role}). Week beginning {p['weekStart']}.\n"
        f"LAST WEEK: {lw['calls']} conversations (prior week {lw['priorCalls']}); "
        f"call quality {lw['quality']} (prior {lw['priorQuality']}); {lw['orders']} orders won.\n"
        f"TOP STRENGTH: {p.get('topStrength')}\n"
        f"FOCUS AREA: {p.get('topFocus')}\n"
        f"COACHING POINT: {p.get('oneThing')}\n"
        f"WARM OPPORTUNITY: {p.get('opportunity')}\n"
        f"{target_line}{fc_line}{rc_line}"
    )
    system = (
        "You are Oliver, a warm, motivating sales coach at BT Local Business Oxford & Bucks (UK "
        "telecom). You write a short spoken script for a personalised weekly performance video for ONE rep. "
        "Tone: positive, specific, encouraging — NEVER punishing. Never say 'you underperformed' "
        "or 'you need to do better'. UK English, second person ('you'). 60–90 seconds = roughly "
        "130–190 words. Structure: 1) greet them by first name; 2) last week's headline result as "
        "one number, framed positively; 3) one specific win with evidence; 4) one specific focus "
        "area with a concrete, encouraging coaching tip (exactly ONE — not a list); 5) this "
        "month's target context as opportunity, not pressure; 6) the warm opportunity to chase; "
        "7) a brief energising close. If WEEKLY FORECAST data is present, weave in their forecast "
        "reliability — celebrate consistency, or gently encourage hitting the number they committed to. "
        "If THEIR LAST REFLECTION COMMITMENTS are present, briefly and warmly acknowledge them — it "
        "shows you listened to what they said they'd do. Only use the data given — invent nothing. "
        "Return STRICT JSON: {\"title\":\"...\",\"headline\":\"one-line summary\",\"script\":\"the spoken script\"}."
    )
    user_msg = f"Write {name}'s weekly video script from this data:\n\n{data}"
    return system, user_msg


def _validate(script: str, user: User) -> bool:
    first = (user.name or "").split()[0].lower()
    s = script.lower()
    if first and first not in s[:120]:
        return False
    if any(bad in s for bad in ("underperform", "you need to do better", "you failed", "disappoint")):
        return False
    wc = len(script.split())
    return 70 <= wc <= 260


def generate_script(user: User, role: str, payload: dict, prompt_fn=None) -> dict:
    from ...pipeline.analyzer import _claude, _extract_json
    system, user_msg = (prompt_fn or _script_prompt)(user, role, payload)
    raw = _claude(system, user_msg, settings.claude_report_model, max_tokens=1200)
    try:
        out = _extract_json(raw)
    except Exception:
        out = {"title": f"{user.name}'s week", "headline": "", "script": raw.strip()}
    script = str(out.get("script") or "").strip()
    if not _validate(script, user):
        log.info("weekly script for %s failed validation (kept anyway)", user.id)
    return {"title": str(out.get("title") or f"{user.name}'s week")[:200],
            "headline": str(out.get("headline") or "")[:300], "script": script}


def _video_enabled(user: User, role: str | None = None) -> bool:
    """Phased rollout — the configured team(s) plus all Business Creators get a rendered
    (credit-costing) video; everyone else still gets the free written briefing."""
    if role == "bc":
        return True                      # Business Creators always get the rendered video
    allow = [t.strip().lower() for t in (settings.video_teams or "").split(",") if t.strip()]
    if not allow:
        return True
    tname = (user.team.name if getattr(user, "team", None) else "") or ""
    return any(a in tname.lower() for a in allow)


def _submit_render(db, video: PerformanceVideo) -> None:
    """Stage 3 — submit the script to HeyGen to render a talking-presenter video. Active only
    when a HeyGen key is configured; otherwise the written briefing stands in. Guarded so a
    render failure never breaks the briefing. HeyGen is async — status is polled to 'ready'."""
    if not settings.heygen_api_key:
        video.status = "text_only"
        return
    # Monthly/quarterly reviews are presented by Gary (the director) — his own avatar + voice if set.
    is_review = video.video_type in ("monthly_review", "quarterly_review")
    avatar_id = (getattr(settings, "heygen_review_avatar_id", "") or settings.heygen_avatar_id) if is_review else settings.heygen_avatar_id
    voice_id = (getattr(settings, "heygen_review_voice_id", "") or settings.heygen_voice_id) if is_review else settings.heygen_voice_id
    try:
        import httpx
        r = httpx.post(
            f"{settings.heygen_api_base}/v2/video/generate",
            headers={"X-Api-Key": settings.heygen_api_key, "Content-Type": "application/json"},
            json={
                "video_inputs": [{
                    "character": {"type": "avatar", "avatar_id": avatar_id,
                                  "avatar_style": "normal"},
                    "voice": {"type": "text", "input_text": video.script,
                              "voice_id": voice_id},
                }],
                "dimension": {"width": 1280, "height": 720},
                "title": (video.title or "Weekly performance")[:100],
            },
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        vid = (data.get("data") or {}).get("video_id") or data.get("video_id")
        if vid:
            video.higgsfield_job_id = str(vid)     # external render job id
            video.status = "rendering"
        else:
            video.status, video.error = "text_only", f"no video_id: {str(data)[:300]}"
    except Exception as e:
        log.warning("HeyGen submit failed: %s", e)
        video.status, video.error = "text_only", str(e)[:500]


def _poll_render(db, video: PerformanceVideo) -> None:
    """Check HeyGen for a rendering video and flip it to ready / failed."""
    if video.status != "rendering" or not video.higgsfield_job_id or not settings.heygen_api_key:
        return
    try:
        import httpx
        r = httpx.get(
            f"{settings.heygen_api_base}/v1/video_status.get",
            params={"video_id": video.higgsfield_job_id},
            headers={"X-Api-Key": settings.heygen_api_key}, timeout=30,
        )
        if r.status_code >= 400:
            video.error = f"poll HTTP {r.status_code}: {r.text[:200]}"
            db.commit()
            return
        body = r.json() or {}
        d = body.get("data") or body
        st = (d.get("status") or "").lower()
        url = d.get("video_url") or d.get("url") or d.get("video_url_caption")
        if st in ("completed", "success", "done", "ready") and url:
            video.video_url, video.status, video.error = url, "ready", None
            db.commit()
        elif st in ("failed", "error"):
            video.status, video.error = "failed", str(d.get("error") or d.get("msg") or "render failed")[:500]
            db.commit()
        else:
            # still processing (or an unexpected shape) — record it so we can see why it's stuck
            video.error = f"HeyGen: status={st or 'none'}{' (no video_url)' if st in ('completed','success','done','ready') else ''}"
            db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        video.error = f"poll exception: {str(e)[:250]}"
        try:
            db.commit()
        except Exception:
            db.rollback()
        log.warning("HeyGen poll failed: %s", e)


def refresh_video(db, video: PerformanceVideo) -> PerformanceVideo:
    """Poll a still-rendering video so simply opening it updates its status."""
    _poll_render(db, video)
    return video


def _json_safe(obj) -> dict:
    """Coerce a payload to something the JSON column can always store (non-serializable values
    like Decimal/numpy/date become strings) — a serialization error here used to fail the commit
    and abort the whole DB transaction."""
    try:
        return json.loads(json.dumps(obj, default=str))
    except Exception:
        return {}


def ensure_weekly_video(db, user: User, regenerate: bool = False) -> PerformanceVideo:
    role = role_for_user(db, user) or "rep"
    wk = datetime.combine(_this_monday(date.today()), time.min)
    existing = (db.query(PerformanceVideo)
                .filter(PerformanceVideo.user_id == user.id,
                        PerformanceVideo.video_type == "weekly_rep",
                        PerformanceVideo.week_start == wk).first())
    if existing and not regenerate:
        return existing
    try:
        payload = weekly_payload(db, user, role)
        s = generate_script(user, role, payload)
    except Exception:
        log.exception("weekly script generation failed for user %s", user.id)
        payload, s = {}, {"title": f"{user.name}'s week", "headline": "",
                          "script": "Your weekly briefing couldn't be generated this week — "
                                    "please check back shortly."}
    v = existing or PerformanceVideo(user_id=user.id, video_type="weekly_rep", week_start=wk)
    v.title, v.headline, v.script = s["title"], s["headline"], s["script"]
    v.data_points, v.status, v.error, v.video_url, v.higgsfield_job_id = _json_safe(payload), "scripted", None, None, None
    if _video_enabled(user, role):
        _submit_render(db, v)        # Volume team + BCs → HeyGen render; others → briefing only
    else:
        v.status = "text_only"
    if not existing:
        db.add(v)
    try:
        db.commit()
    except Exception:
        db.rollback()
        log.exception("weekly video commit failed for user %s", user.id)
    return v


def ensure_review_video(db, user: User, period: str, asof: date | None = None,
                        regenerate: bool = False) -> PerformanceVideo:
    """Build (once) the monthly/quarterly REVIEW video for the period that just ended."""
    from ..salesiq import fincal
    role = role_for_user(db, user) or "rep"
    asof = asof or date.today()
    prior = _sales_month_before(fincal.current_sales_month(asof))
    vtype = "quarterly_review" if period == "quarter" else "monthly_review"
    pstart = datetime.combine(prior["start"], time.min)        # keyed by the reviewed month's start
    existing = (db.query(PerformanceVideo)
                .filter(PerformanceVideo.user_id == user.id, PerformanceVideo.video_type == vtype,
                        PerformanceVideo.week_start == pstart).first())
    if existing and not regenerate:
        return existing
    try:
        payload = review_payload(db, user, role, asof, period)
        s = generate_script(user, role, payload, prompt_fn=_review_script_prompt)
    except Exception:
        log.exception("review script generation failed for user %s", user.id)
        payload, s = {}, {"title": f"{user.name}'s {period} review", "headline": "",
                          "script": "Your performance review couldn't be generated — please check back shortly."}
    v = existing or PerformanceVideo(user_id=user.id, video_type=vtype, week_start=pstart)
    v.title, v.headline, v.script = s["title"], s["headline"], s["script"]
    v.data_points, v.status, v.error, v.video_url, v.higgsfield_job_id = _json_safe(payload), "scripted", None, None, None
    _submit_render(db, v)                  # reviews always render (Gary avatar) when HeyGen configured
    if not existing:
        db.add(v)
    try:
        db.commit()
    except Exception:
        db.rollback()
        log.exception("review video commit failed for user %s", user.id)
    return v


def generate_all_reviews(db, asof: date | None = None) -> dict:
    """Pre-generate monthly reviews for every active rep/BC (and quarterly when the new sales month
    starts a BT quarter: Apr/Jul/Oct/Jan). Idempotent. Run early on the first Monday of the month."""
    from ..salesiq.roles import role_for_user
    from ..salesiq import fincal
    asof = asof or date.today()
    do_quarter = fincal.current_sales_month(asof)["month"] in (4, 7, 10, 1)
    n, errors = 0, []
    for u in db.query(User).filter(User.active.is_(True)).all():
        try:
            if role_for_user(db, u) not in ("rep", "bc"):
                continue
            ensure_review_video(db, u, "month", asof)
            if do_quarter:
                ensure_review_video(db, u, "quarter", asof)
            n += 1
        except Exception as e:
            db.rollback()
            errors.append(f"{u.name}: {str(e)[:160]}")
            log.exception("review generation failed for user %s", u.id)
    log.info("Pre-generated %d performance reviews (quarter=%s, %d errors)", n, do_quarter, len(errors))
    return {"generated": n, "quarter": do_quarter, "errors": errors}


def latest_review(db, user: User):
    """The most recent monthly/quarterly review for a user (quarterly preferred when same month)."""
    return (db.query(PerformanceVideo)
            .filter(PerformanceVideo.user_id == user.id,
                    PerformanceVideo.video_type.in_(["monthly_review", "quarterly_review"]))
            .order_by(PerformanceVideo.week_start.desc(),
                      PerformanceVideo.video_type.desc()).first())


def generate_all_weekly(db) -> dict:
    """Pre-generate this week's videos for every video-enabled rep/BC (idempotent — skips any
    already made). Per-user isolation + rollback so one user's failure can't abort the
    transaction and poison the rest."""
    from ..salesiq.roles import role_for_user
    n, errors = 0, []
    for u in db.query(User).filter(User.active.is_(True)).all():
        try:
            r = role_for_user(db, u)
            if r in ("rep", "bc") and _video_enabled(u, r):
                ensure_weekly_video(db, u)
                n += 1
        except Exception as e:
            db.rollback()
            errors.append(f"{u.name}: {str(e)[:160]}")
            log.exception("weekly video generation failed for user %s", u.id)
    log.info("Pre-generated %d weekly videos (%d errors)", n, len(errors))
    return {"generated": n, "errors": errors}


def video_payload(v: PerformanceVideo) -> dict:
    return {
        "id": v.id, "userId": v.user_id, "type": v.video_type,
        "weekStart": v.week_start.isoformat() if v.week_start else None,
        "title": v.title, "headline": v.headline, "script": v.script,
        "status": v.status, "videoUrl": v.video_url, "error": v.error,
        "hasVideo": v.status == "ready" and bool(v.video_url),
        "createdAt": v.created_at.isoformat() + "Z" if v.created_at else None,
    }
