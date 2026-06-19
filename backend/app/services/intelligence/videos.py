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
    return {
        "weekStart": this_mon.isoformat(),
        "lastWeek": {
            "calls": agg["calls"], "priorCalls": pagg["calls"],
            "quality": agg["quality"], "priorQuality": pagg["quality"],
            "orders": agg["orders"], "closeRate": agg["closeRate"],
        },
        "topStrength": top_strength[0][0] if top_strength else None,
        "topFocus": top_focus[0][0] if top_focus else None,
        "oneThing": one_things[0] if one_things else None,
        "opportunity": opportunity,
        "monthly": mtd,
    }


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
    data = (
        f"Rep: {user.name} ({role}). Week beginning {p['weekStart']}.\n"
        f"LAST WEEK: {lw['calls']} conversations (prior week {lw['priorCalls']}); "
        f"call quality {lw['quality']} (prior {lw['priorQuality']}); {lw['orders']} orders won.\n"
        f"TOP STRENGTH: {p.get('topStrength')}\n"
        f"FOCUS AREA: {p.get('topFocus')}\n"
        f"COACHING POINT: {p.get('oneThing')}\n"
        f"WARM OPPORTUNITY: {p.get('opportunity')}\n"
        f"{target_line}"
    )
    system = (
        "You are a warm, motivating sales coach at BT Local Business Oxford & Bucks (UK telecom). "
        "You write a short spoken script for a personalised weekly performance video for ONE rep. "
        "Tone: positive, specific, encouraging — NEVER punishing. Never say 'you underperformed' "
        "or 'you need to do better'. UK English, second person ('you'). 60–90 seconds = roughly "
        "130–190 words. Structure: 1) greet them by first name; 2) last week's headline result as "
        "one number, framed positively; 3) one specific win with evidence; 4) one specific focus "
        "area with a concrete, encouraging coaching tip (exactly ONE — not a list); 5) this "
        "month's target context as opportunity, not pressure; 6) the warm opportunity to chase; "
        "7) a brief energising close. Only use the data given — invent nothing. "
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


def generate_script(user: User, role: str, payload: dict) -> dict:
    from ...pipeline.analyzer import _claude, _extract_json
    system, user_msg = _script_prompt(user, role, payload)
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
    try:
        import httpx
        r = httpx.post(
            f"{settings.heygen_api_base}/v2/video/generate",
            headers={"X-Api-Key": settings.heygen_api_key, "Content-Type": "application/json"},
            json={
                "video_inputs": [{
                    "character": {"type": "avatar", "avatar_id": settings.heygen_avatar_id,
                                  "avatar_style": "normal"},
                    "voice": {"type": "text", "input_text": video.script,
                              "voice_id": settings.heygen_voice_id},
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
