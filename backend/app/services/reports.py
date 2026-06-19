"""Coaching profile report generation (weekly or on demand)."""
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Call, CallAnalysis, CallScore, Report, Team, User

log = logging.getLogger("calliq.reports")


def _team_data(db: Session, start: datetime, end: datetime, team: Team) -> str:
    """Build a plain-text data block per team for the LLM."""
    lines = [f"TEAM: {team.name}"]
    for u in team.users:
        if not u.active:
            continue
        calls = (db.query(Call).filter(Call.host_id == u.id,
                                       Call.started_at >= start, Call.started_at <= end).all())
        if not calls:
            continue
        ids = [c.id for c in calls]
        analyses = db.query(CallAnalysis).filter(CallAnalysis.call_id.in_(ids)).all()
        scores = db.query(CallScore).filter(CallScore.call_id.in_(ids)).all()
        n = len(calls)
        avg = lambda xs: round(sum(xs) / len(xs), 1) if xs else 0  # noqa: E731
        crit_scores: dict[str, list] = {}
        for s in scores:
            for c in (s.criteria or []):
                crit_scores.setdefault(c.get("name", "?"), []).append(c.get("score", 0))
        weakest = sorted(((k, avg(v)) for k, v in crit_scores.items()), key=lambda x: x[1])[:3]
        lines.append(
            f"- {u.name} ({u.job_title}): {n} calls, "
            f"avg score {avg([s.overall for s in scores])}, "
            f"talk ratio {avg([a.talk_ratio for a in analyses])}%, "
            f"question rate {avg([a.question_rate for a in analyses])}, "
            f"weakest criteria: {', '.join(f'{k} ({v})' for k, v in weakest) or 'n/a'}"
        )
    return "\n".join(lines)


def generate_coaching_report(db: Session, start: datetime, end: datetime,
                             team_names: list[str] | None) -> Report:
    teams_q = db.query(Team)
    if team_names:
        teams_q = teams_q.filter(Team.name.in_(team_names))
    teams = teams_q.all()
    data = "\n\n".join(_team_data(db, start, end, t) for t in teams)
    period = f"{start.strftime('%-d %b' if hasattr(start, 'strftime') else '%d %b')}"
    try:
        period = f"{start.day} {start.strftime('%b')} - {end.day} {end.strftime('%b %Y')}"
    except Exception:
        pass

    if settings.anthropic_api_key:
        from ..pipeline.analyzer import generate_weekly_report_md
        content = generate_weekly_report_md(
            f"Period: {period}\n\n{data}")
    else:
        # Demo mode: deterministic data-driven report without LLM
        content = (f"# Weekly Coaching Profiles\n\n*Period: {period}*\n\n"
                   f"## Team data\n\n```\n{data}\n```\n\n"
                   "*(Connect an Anthropic API key for full AI-written coaching narratives.)*")

    r = Report(
        name=f"Coaching Profiles - {period} - "
             f"{', '.join(t.name for t in teams) if team_names else 'All Teams'}",
        report_type="coaching_profiles",
        frequency="weekly",
        period_start=start, period_end=end,
        team_names=[t.name for t in teams],
        content_md=content,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r
