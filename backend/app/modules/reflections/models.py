"""Review Reflection data model.

One ``ReviewReflection`` per (rep, review video). It holds the full dialogue transcript plus the
structured signal extracted from it when the conversation completes — the rep's self-assessment,
blockers, commitments, themes, and the understanding / self-awareness / engagement reads. Visible to
managers (full transcript + summary) per the agreed design.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ...core.mixins import JSON_B, DomainBase
from ...db import Base


class ReviewReflection(DomainBase, Base):
    """A rep's guided reflection dialogue on one performance review."""
    __tablename__ = "review_reflections"
    __table_args__ = (UniqueConstraint("user_id", "video_id", name="uq_reflection_user_video"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("performance_videos.id"), index=True)
    period_type: Mapped[str] = mapped_column(String(16), default="weekly")    # weekly | monthly | quarterly
    period_key: Mapped[str] = mapped_column(String(40), default="")           # the period it covers

    status: Mapped[str] = mapped_column(String(16), default="not_started")    # not_started | in_progress | complete
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # The conversation: ordered list of {role: "ai" | "rep", text, at}
    turns: Mapped[list] = mapped_column(JSON_B, default=list)

    # ---- Structured signal, mined when the reflection completes ----
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)           # manager-facing summary
    self_assessment: Mapped[str | None] = mapped_column(Text, nullable=True)   # the rep's own read
    blockers: Mapped[list] = mapped_column(JSON_B, default=list)               # [{text, category, needsManager}]
    commitments: Mapped[list] = mapped_column(JSON_B, default=list)            # [{text, category, target, met}]
    themes: Mapped[list] = mapped_column(JSON_B, default=list)
    understanding_score: Mapped[int | None] = mapped_column(Integer, nullable=True)   # 0-100, grasp of the coaching
    self_awareness_gap: Mapped[int | None] = mapped_column(Integer, nullable=True)    # 0-100, self-view vs the data
    self_awareness_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    engagement_score: Mapped[int | None] = mapped_column(Integer, nullable=True)      # 0-100, depth/openness
    asked_for_help: Mapped[bool] = mapped_column(Boolean, default=False)
    shared: Mapped[bool] = mapped_column(Boolean, default=True)                # transcript shared with manager
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
