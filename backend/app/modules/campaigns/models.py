"""Campaigns — BT Promotions + Sales Incentives, one backbone, two types (Roadmap Phase 1).

A promotion is customer‑facing (the rep should *introduce* it); an incentive is rep‑facing (the rep
should *pitch the qualifying product* — never disclose the bonus). Both are time‑bound, link to
catalogue products, and are detected in calls by the analyser (Phase 2).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...core.mixins import DomainBase
from ...db import Base

PROMOTION, INCENTIVE = "promotion", "incentive"
TEMPLATES = {  # type -> templates (UI presets)
    PROMOTION: ["launch", "discount", "bundle", "sov_boost", "custom"],
    INCENTIVE: ["attach_bonus", "per_sale_bonus", "threshold_bonus", "custom"],
}


class Campaign(DomainBase, Base):
    __tablename__ = "campaigns"

    type: Mapped[str] = mapped_column(String(20), index=True)          # promotion | incentive
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    template: Mapped[str | None] = mapped_column(String(30), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[date] = mapped_column(Date, index=True)
    teams: Mapped[list | None] = mapped_column(JSON, default=list)     # team ids; [] / null = all teams
    product_ids: Mapped[list | None] = mapped_column(JSON, default=list)   # catalog product uuids (str)
    talking_points: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived: Mapped[bool] = mapped_column(default=False)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    # --- promotion (customer‑facing) ---
    offer: Mapped[str | None] = mapped_column(Text, nullable=True)         # discount / price / bundle terms
    sov_multiplier: Mapped[float | None] = mapped_column(Float, nullable=True)   # extra SOV weight on the product
    customer_segments: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- incentive (rep‑facing) ---
    reward_amount: Mapped[float | None] = mapped_column(Float, nullable=True)    # £ per qualifying sale (or per tier)
    reward_basis: Mapped[str | None] = mapped_column(String(20), nullable=True)  # per_sale | threshold | tiered
    qualifying_rule: Mapped[str | None] = mapped_column(Text, nullable=True)     # what counts (free text + products)
    target_per_rep: Mapped[float | None] = mapped_column(Float, nullable=True)
    team_target: Mapped[float | None] = mapped_column(Float, nullable=True)


class CampaignMention(DomainBase, Base):
    """One row per call × live campaign — the analyser's verdict (Phase 2). For promotions:
    did the rep introduce it and how did the customer react. For incentives: was the qualifying
    product pitched."""
    __tablename__ = "campaign_mentions"

    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), index=True)
    call_id: Mapped[int] = mapped_column(Integer, index=True)
    host_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    call_date: Mapped[date | None] = mapped_column(Date, index=True, nullable=True)
    addressed: Mapped[str] = mapped_column(String(10), default="missed")   # yes | weak | missed
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_reaction: Mapped[str | None] = mapped_column(String(20), nullable=True)  # positive|neutral|objection|n/a
    outcome: Mapped[str | None] = mapped_column(String(40), nullable=True)

    campaign = relationship("Campaign")
