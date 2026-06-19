"""Team Insights: activity over time, engagement stats, topics analytics, leaderboards."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import (Call, CallAnalysis, CallScore, CallTopic, ListenEvent, Topic, User)

router = APIRouter(prefix="/api/insights", tags=["insights"])


def _period(days: int | None, date_from: datetime | None, date_to: datetime | None):
    end = date_to or datetime.utcnow()
    start = date_from or (end - timedelta(days=days or 90))
    return start, end


def _call_filter(q, start, end, team_id, db):
    q = q.filter(Call.started_at >= start, Call.started_at <= end)
    if team_id:
        ids = [u.id for u in db.query(User).filter(User.team_id == team_id)]
        q = q.filter(Call.host_id.in_(ids))
    return q


@router.get("/activity")
def activity_over_time(db: Session = Depends(get_db), user: User = Depends(get_current_user),
                       days: int | None = 90, team_id: int | None = None,
                       date_from: datetime | None = None, date_to: datetime | None = None):
    """Daily call counts split by direction + headline totals."""
    start, end = _period(days, date_from, date_to)
    q = _call_filter(db.query(Call), start, end, team_id, db)
    calls = q.all()
    by_day: dict[str, dict] = {}
    d = start.date()
    while d <= end.date():
        by_day[d.isoformat()] = {"date": d.isoformat(), "outbound": 0, "inbound": 0}
        d += timedelta(days=1)
    totals = {"outbound": 0, "inbound": 0, "recorded": 0, "total_duration_sec": 0}
    for c in calls:
        key = c.started_at.date().isoformat()
        if key in by_day:
            by_day[key][c.direction] = by_day[key].get(c.direction, 0) + 1
        totals[c.direction] = totals.get(c.direction, 0) + 1
        if c.status == "completed":
            totals["recorded"] += 1
        totals["total_duration_sec"] += c.duration_sec
    return {"series": list(by_day.values()), "totals": totals}


@router.get("/engagement")
def engagement(db: Session = Depends(get_db), user: User = Depends(get_current_user),
               days: int | None = 90, team_id: int | None = None):
    """Org/team averages + per-rep engagement metrics."""
    start, end = _period(days, None, None)
    q = (db.query(Call, CallAnalysis).join(CallAnalysis, CallAnalysis.call_id == Call.id))
    q = _call_filter(q, start, end, team_id, db)
    rows = q.all()

    def summarise(items):
        n = len(items)
        if not n:
            return None
        return {
            "calls": n,
            "talk_ratio": round(sum(a.talk_ratio for _, a in items) / n, 1),
            "longest_monologue_sec": round(max(a.longest_monologue_sec for _, a in items), 1),
            "longest_customer_story_sec": round(max(a.longest_customer_story_sec for _, a in items), 1),
            "talking_speed_wpm": round(sum(a.talking_speed_wpm for _, a in items) / n),
            "patience_sec": round(sum(a.patience_sec for _, a in items) / n, 2),
            "question_rate": round(sum(a.question_rate for _, a in items) / n, 1),
        }

    by_rep: dict[int, list] = {}
    for c, a in rows:
        if c.host_id:
            by_rep.setdefault(c.host_id, []).append((c, a))
    reps = []
    for host_id, items in by_rep.items():
        u = db.get(User, host_id)
        if u:
            reps.append({"user": {"id": u.id, "name": u.name, "avatar_color": u.avatar_color,
                                  "active": u.active}, **(summarise(items) or {})})
    reps.sort(key=lambda r: r.get("calls", 0), reverse=True)
    return {"overall": summarise(rows), "reps": reps}


@router.get("/topics")
def topic_analytics(db: Session = Depends(get_db), user: User = Depends(get_current_user),
                    days: int | None = 90, team_id: int | None = None):
    """% of calls mentioning each topic, org-wide and per rep (Jiminny Topics tab)."""
    start, end = _period(days, None, None)
    call_q = _call_filter(db.query(Call.id, Call.host_id), start, end, team_id, db) \
        .filter(Call.status == "completed")
    call_rows = call_q.all()
    call_ids = [r[0] for r in call_rows]
    host_of = {r[0]: r[1] for r in call_rows}
    total_calls = len(call_ids) or 1

    topics = db.query(Topic).filter(Topic.active == True).all()  # noqa: E712
    ct_rows = db.query(CallTopic).filter(CallTopic.call_id.in_(call_ids)).all() if call_ids else []

    by_topic: dict[int, set] = {}
    by_topic_rep: dict[int, dict[int, set]] = {}
    calls_per_rep: dict[int, int] = {}
    for cid in call_ids:
        h = host_of.get(cid)
        if h:
            calls_per_rep[h] = calls_per_rep.get(h, 0) + 1
    for ct in ct_rows:
        by_topic.setdefault(ct.topic_id, set()).add(ct.call_id)
        h = host_of.get(ct.call_id)
        if h:
            by_topic_rep.setdefault(ct.topic_id, {}).setdefault(h, set()).add(ct.call_id)

    out = []
    for t in topics:
        mentioned = len(by_topic.get(t.id, set()))
        rep_breakdown = []
        for host_id, cids in by_topic_rep.get(t.id, {}).items():
            u = db.get(User, host_id)
            if u and calls_per_rep.get(host_id):
                rep_breakdown.append({
                    "user": {"id": u.id, "name": u.name, "avatar_color": u.avatar_color,
                             "active": u.active},
                    "percentage": round(100 * len(cids) / calls_per_rep[host_id]),
                    "calls": len(cids),
                })
        rep_breakdown.sort(key=lambda r: r["percentage"], reverse=True)
        out.append({"topic": {"id": t.id, "name": t.name, "color": t.color},
                    "percentage": round(100 * mentioned / total_calls),
                    "calls": mentioned,
                    "team_average": round(100 * mentioned / total_calls),
                    "reps": rep_breakdown})
    out.sort(key=lambda x: x["percentage"], reverse=True)
    return out


@router.get("/scores")
def score_analytics(db: Session = Depends(get_db), user: User = Depends(get_current_user),
                    days: int | None = 90, team_id: int | None = None):
    """Average AI call score per rep and per playbook criterion — rep skill analysis."""
    start, end = _period(days, None, None)
    q = db.query(Call, CallScore).join(CallScore, CallScore.call_id == Call.id)
    q = _call_filter(q, start, end, team_id, db)
    rows = q.all()

    by_rep: dict[int, list] = {}
    by_criterion: dict[str, list] = {}
    for c, s in rows:
        if c.host_id:
            by_rep.setdefault(c.host_id, []).append(s.overall)
        for crit in (s.criteria or []):
            by_criterion.setdefault(crit.get("name", "?"), []).append(crit.get("score", 0))

    reps = []
    for host_id, scores in by_rep.items():
        u = db.get(User, host_id)
        if u:
            reps.append({"user": {"id": u.id, "name": u.name, "avatar_color": u.avatar_color},
                         "avg_score": round(sum(scores) / len(scores), 1),
                         "scored_calls": len(scores)})
    reps.sort(key=lambda r: r["avg_score"], reverse=True)
    criteria = [{"name": k, "avg_score": round(sum(v) / len(v), 1), "n": len(v)}
                for k, v in by_criterion.items()]
    criteria.sort(key=lambda c: c["avg_score"])
    return {"reps": reps, "criteria": criteria}


@router.get("/coaching")
def coaching_activity(db: Session = Depends(get_db), user: User = Depends(get_current_user),
                      days: int | None = 90, team_id: int | None = None):
    """Listening activity as coaching proxy: self-coaching (own calls), manager-led, team."""
    start, end = _period(days, None, None)
    q = (db.query(ListenEvent).join(Call, ListenEvent.call_id == Call.id)
         .filter(ListenEvent.listened_at >= start, ListenEvent.listened_at <= end))
    events = q.all()
    self_c = manager = team = 0
    for e in events:
        listener = db.get(User, e.user_id)
        call = db.get(Call, e.call_id)
        if not listener or not call:
            continue
        if call.host_id == listener.id:
            self_c += 1
        elif listener.role in ("admin", "analyst"):
            manager += 1
        else:
            team += 1
    total = self_c + manager + team
    return {"total": total, "self_coaching": self_c, "manager_led": manager, "team_coaching": team}
