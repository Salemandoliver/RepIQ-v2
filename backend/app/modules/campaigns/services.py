"""Campaigns service — status derivation, the 'what's live' query, and serialisation."""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from .models import Campaign


def status_of(c: Campaign, today: date | None = None) -> str:
    today = today or date.today()
    if c.archived:
        return "archived"
    if today < c.start_date:
        return "scheduled"
    if today > c.end_date:
        return "expired"
    return "live"


def applies_to_team(c: Campaign, team_id: int | None) -> bool:
    if not c.teams:                      # empty / null = all teams
        return True
    return team_id in c.teams


def live_campaigns(db: Session, team_id: int | None = None, on_date: date | None = None,
                   ctype: str | None = None) -> list[Campaign]:
    """Campaigns that are live on ``on_date`` (default today), optionally for a team / type."""
    on_date = on_date or date.today()
    q = (db.query(Campaign)
         .filter(Campaign.deleted_at.is_(None), Campaign.archived.is_(False),
                 Campaign.start_date <= on_date, Campaign.end_date >= on_date))
    if ctype:
        q = q.filter(Campaign.type == ctype)
    return [c for c in q.order_by(Campaign.end_date.asc()).all() if applies_to_team(c, team_id)]


def to_dict(c: Campaign, today: date | None = None) -> dict:
    return {
        "id": str(c.id), "type": c.type, "name": c.name, "description": c.description,
        "template": c.template, "status": status_of(c, today),
        "startDate": c.start_date.isoformat(), "endDate": c.end_date.isoformat(),
        "teams": c.teams or [], "productIds": c.product_ids or [],
        "talkingPoints": c.talking_points, "archived": c.archived,
        # promotion
        "offer": c.offer, "sovMultiplier": c.sov_multiplier, "customerSegments": c.customer_segments,
        # incentive
        "rewardAmount": c.reward_amount, "rewardBasis": c.reward_basis,
        "qualifyingRule": c.qualifying_rule, "targetPerRep": c.target_per_rep, "teamTarget": c.team_target,
        "createdAt": c.created_at.isoformat() if c.created_at else None,
    }
