"""Review Reflection services — lifecycle (get-or-create, run the dialogue, complete) plus the
``reflection_signal`` backbone that every intelligence surface reads, so the rep's reflection factors
into performance analysis, alerts, briefs and Ask/Oracle consistently.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from ...models import PerformanceVideo, User
from . import dialogue as dlg
from .models import ReviewReflection

# A weekly review is "fresh" (worth nudging on) for this many days; reviews use the current period.
WEEKLY_FRESH_DAYS = 10
FOLLOWTHROUGH_WINDOW = 6   # recent completed reflections used for commitment follow-through


# ============================================================ lifecycle
def get_reflection(db: Session, user_id: int, video_id: int) -> ReviewReflection | None:
    return (db.query(ReviewReflection)
            .filter(ReviewReflection.user_id == user_id, ReviewReflection.video_id == video_id).first())


def get_or_create(db: Session, user: User, video: PerformanceVideo) -> ReviewReflection:
    r = get_reflection(db, user.id, video.id)
    if not r:
        r = ReviewReflection(
            user_id=user.id, video_id=video.id,
            period_type=dlg.period_for(video.video_type),
            period_key=video.week_start.date().isoformat() if video.week_start else "",
        )
        db.add(r)
        db.commit()
    return r


def open_dialogue(db: Session, user: User, video: PerformanceVideo, reflection: ReviewReflection) -> ReviewReflection:
    """Ensure there's an opening message from the presenter."""
    if not reflection.turns:
        first = dlg.next_message(db, reflection, video, user)
        reflection.turns = [{"role": "ai", "text": first["message"], "at": dlg._now()}]
        reflection.status = "in_progress"
        reflection.started_at = datetime.utcnow()
        db.commit()
    return reflection


def add_rep_message(db: Session, user: User, video: PerformanceVideo,
                    reflection: ReviewReflection, text: str) -> dict:
    """Append the rep's message, generate the presenter's reply, and finalise if the dialogue is done."""
    if reflection.status == "complete":
        return {"message": "This reflection is already complete.", "done": True}
    turns = list(reflection.turns or [])
    turns.append({"role": "rep", "text": (text or "").strip(), "at": dlg._now()})
    reflection.turns = turns
    reflection.status = "in_progress"
    if reflection.started_at is None:
        reflection.started_at = datetime.utcnow()
    db.commit()

    reply = dlg.next_message(db, reflection, video, user)
    turns = list(reflection.turns or [])
    turns.append({"role": "ai", "text": reply["message"], "at": dlg._now()})
    reflection.turns = turns
    db.commit()

    if reply.get("done"):
        complete(db, user, video, reflection)
    return {"message": reply["message"], "done": bool(reply.get("done"))}


def complete(db: Session, user: User, video: PerformanceVideo, reflection: ReviewReflection) -> ReviewReflection:
    if reflection.status != "complete":
        dlg.extract(db, reflection, video, user)
        reflection.status = "complete"
        reflection.completed_at = datetime.utcnow()
        db.commit()
        # Close the loop: judge how last period's commitments went, from what they just said.
        try:
            dlg.assess_prior_commitments(db, reflection, video, user)
        except Exception:
            pass
    return reflection


def to_dict(r: ReviewReflection | None, *, full: bool = True) -> dict | None:
    if not r:
        return None
    out = {
        "id": str(r.id), "videoId": r.video_id, "periodType": r.period_type, "periodKey": r.period_key,
        "status": r.status, "summary": r.summary, "commitments": r.commitments or [],
        "blockers": r.blockers or [], "themes": r.themes or [],
        "understanding": r.understanding_score, "selfAwareness": r.self_awareness_gap,
        "selfAwarenessNote": r.self_awareness_note, "engagement": r.engagement_score,
        "askedForHelp": bool(r.asked_for_help),
        "completedAt": r.completed_at.isoformat() + "Z" if r.completed_at else None,
    }
    if full:
        out["turns"] = r.turns or []
        out["selfAssessment"] = r.self_assessment
    return out


# ============================================================ "what needs reflecting on?"
def _latest_videos(db: Session, user_id: int) -> list[PerformanceVideo]:
    """The candidate reviews a rep might reflect on: the latest weekly (if fresh) and the latest review."""
    out = []
    wk = (db.query(PerformanceVideo)
          .filter(PerformanceVideo.user_id == user_id, PerformanceVideo.video_type == "weekly_rep")
          .order_by(PerformanceVideo.week_start.desc()).first())
    if wk and wk.week_start and wk.week_start.date() >= date.today() - timedelta(days=WEEKLY_FRESH_DAYS):
        out.append(wk)
    rev = (db.query(PerformanceVideo)
           .filter(PerformanceVideo.user_id == user_id,
                   PerformanceVideo.video_type.in_(["monthly_review", "quarterly_review"]))
           .order_by(PerformanceVideo.week_start.desc()).first())
    if rev:
        out.append(rev)
    return out


def pending_reflection(db: Session, user: User) -> dict | None:
    """The most recent review the rep hasn't yet completed a reflection on (drives the nudge). None if
    nothing fresh is outstanding."""
    for v in sorted(_latest_videos(db, user.id), key=lambda x: x.week_start or datetime.min, reverse=True):
        r = get_reflection(db, user.id, v.id)
        if not (r and r.status == "complete"):
            return {"videoId": v.id, "videoType": v.video_type, "presenter": dlg.presenter_for(v.video_type),
                    "period": dlg.period_for(v.video_type), "title": v.title,
                    "started": bool(r and r.status == "in_progress")}
    return None


def reflection_streak(db: Session, user: User) -> int:
    """Consecutive most-recent reviews the rep has reflected on (stops at the first one they skipped)
    — a light habit indicator to reinforce reflecting."""
    vids = (db.query(PerformanceVideo.id)
            .filter(PerformanceVideo.user_id == user.id,
                    PerformanceVideo.video_type.in_(["weekly_rep", "monthly_review", "quarterly_review"]))
            .order_by(PerformanceVideo.week_start.desc()).limit(26).all())
    streak = 0
    for (vid,) in vids:
        r = get_reflection(db, user.id, vid)
        if r and r.status == "complete":
            streak += 1
        else:
            break
    return streak


# ============================================================ reflection signal (single source)
def _signal_summary(name, latest, eng, sa, blockers_help, open_commitments, pending) -> str:
    if pending:
        return f"{name} hasn't reflected on their latest {pending.get('period')} review yet."
    if not latest or latest.status != "complete":
        return f"{name} hasn't completed a review reflection yet."
    bits = []
    if eng is not None:
        bits.append("engaged thoughtfully" if eng >= 70 else "gave a brief reflection" if eng < 45 else "reflected")
    if open_commitments:
        bits.append(f"committed to: {open_commitments[0]}" + (f" (+{len(open_commitments) - 1} more)" if len(open_commitments) > 1 else ""))
    if blockers_help:
        bits.append(f"flagged a blocker for help: {blockers_help[0].get('text')}")
    if sa is not None and sa < 45:
        bits.append("self-view doesn't quite match the numbers")
    return f"{name}: " + ("; ".join(bits) if bits else "reflected on their review") + "."


def reflection_signal(db: Session, user: User) -> dict:
    """Compact reflection standing for a rep — the single source detectors, alerts, briefs and
    Ask/Oracle all read."""
    name = user.short_name or user.name
    latest = (db.query(ReviewReflection).filter(ReviewReflection.user_id == user.id)
              .order_by(ReviewReflection.created_at.desc()).first())
    recents = (db.query(ReviewReflection)
               .filter(ReviewReflection.user_id == user.id, ReviewReflection.status == "complete")
               .order_by(ReviewReflection.completed_at.desc()).limit(FOLLOWTHROUGH_WINDOW).all())
    pending = pending_reflection(db, user)

    complete_latest = latest if (latest and latest.status == "complete") else None
    eng = complete_latest.engagement_score if complete_latest else None
    sa = complete_latest.self_awareness_gap if complete_latest else None
    open_commitments = [c.get("text") for c in (complete_latest.commitments or []) if c.get("text")] if complete_latest else []
    blockers_help = [b for b in (complete_latest.blockers or []) if b.get("needsManager")] if complete_latest else []

    met = total = 0
    for r in recents:
        for c in (r.commitments or []):
            if c.get("met") is not None:
                total += 1
                met += 1 if c.get("met") else 0
    followthrough = round(met / total * 100) if total else None

    flags = {
        "notReflected": bool(pending),
        "blockerFlagged": bool(blockers_help),
        "lowSelfAwareness": bool(sa is not None and sa < 45),
        "growthMindset": bool(eng is not None and eng >= 75 and (followthrough is None or followthrough >= 50)),
        "disengaged": bool(complete_latest and eng is not None and eng < 40),
        "commitmentSlipping": bool(followthrough is not None and followthrough < 50),
    }
    total_reflected = (db.query(ReviewReflection)
                       .filter(ReviewReflection.user_id == user.id, ReviewReflection.status == "complete").count())
    return {
        "userId": user.id, "name": name,
        "status": latest.status if latest else "none",
        "pending": pending,
        "streak": reflection_streak(db, user), "totalReflected": total_reflected,
        "lastReflectedAt": complete_latest.completed_at.isoformat() + "Z" if complete_latest and complete_latest.completed_at else None,
        "summaryText": complete_latest.summary if complete_latest else None,
        "openCommitments": open_commitments,
        "blockersNeedingHelp": [b.get("text") for b in blockers_help],
        "engagement": eng, "selfAwareness": sa, "followThrough": followthrough,
        "flags": flags,
        "summary": _signal_summary(name, latest, eng, sa, blockers_help, open_commitments, pending),
    }


def team_reflection_summary(db: Session, team: str | None = None) -> dict:
    """Team-wide reflection standing — who's reflected, open blockers/commitments, recurring themes."""
    try:
        from ..forecast.services import eligible_reps
        reps = eligible_reps(db, team)
    except Exception:
        reps = []
    sigs = [reflection_signal(db, u) for u in reps]
    themes: dict[str, int] = {}
    for s in sigs:
        cl = db.query(ReviewReflection).filter(
            ReviewReflection.user_id == s["userId"], ReviewReflection.status == "complete"
        ).order_by(ReviewReflection.completed_at.desc()).first()
        for t in (cl.themes if cl else []) or []:
            themes[t] = themes.get(t, 0) + 1
    return {
        "notReflected": [s["name"] for s in sigs if s["flags"]["notReflected"]],
        "blockersForHelp": [{"name": s["name"], "blockers": s["blockersNeedingHelp"]}
                            for s in sigs if s["flags"]["blockerFlagged"]],
        "topThemes": sorted(themes, key=themes.get, reverse=True)[:6],
        "signals": sigs,
    }
