"""Weekly Forecast data model.

- ``WeeklyForecast``       — a rep's committed Data/Cloud/Mobile SOV (£) for one BT financial week.
                            Locks once the rep submits; only a manager can edit/unlock afterward.
- ``WeeklyForecastResult`` — an immutable weekly snapshot written at week close. This is the stable
                            history the Forecast Reliability Score is built from, so later edits to
                            the live Sales Tracker can't retroactively change a rep's record.

"Data SOV" maps to the Sales Tracker's *connectivity* column; Cloud and Mobile map directly; the
tracker's *other* column is excluded (matches the rep dashboard's SOV = connectivity + cloud + mobile).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ...core.mixins import DomainBase
from ...db import Base


class WeeklyForecast(DomainBase, Base):
    """A Sales Rep's committed forecast for one BT financial week (Mon–Sun)."""
    __tablename__ = "weekly_forecasts"
    __table_args__ = (
        UniqueConstraint("user_id", "week_year", "week_number", name="uq_forecast_user_week"),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    week_year: Mapped[int] = mapped_column(Integer, index=True)      # BT FY-start year
    week_number: Mapped[int] = mapped_column(Integer, index=True)    # BT financial week number

    # The committed figures, in £ SOV.
    data_sov: Mapped[float] = mapped_column(Float, default=0.0)      # = Connectivity
    cloud_sov: Mapped[float] = mapped_column(Float, default=0.0)
    mobile_sov: Mapped[float] = mapped_column(Float, default=0.0)

    # Submission / lock lifecycle. A rep submits once; thereafter `locked` blocks rep edits and only
    # a manager may change it (stamped in the edited_* fields).
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    submitted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    on_time: Mapped[bool] = mapped_column(Boolean, default=True)     # submitted by Mon 11:00
    locked: Mapped[bool] = mapped_column(Boolean, default=False)

    edited_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    edit_note: Mapped[str | None] = mapped_column(String(300), nullable=True)

    @property
    def total_sov(self) -> float:
        return round((self.data_sov or 0.0) + (self.cloud_sov or 0.0) + (self.mobile_sov or 0.0), 2)


class WeeklyForecastResult(DomainBase, Base):
    """Immutable weekly snapshot (written at week close) — the consistency history."""
    __tablename__ = "weekly_forecast_results"
    __table_args__ = (
        UniqueConstraint("user_id", "week_year", "week_number", name="uq_forecast_result_user_week"),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    week_year: Mapped[int] = mapped_column(Integer, index=True)
    week_number: Mapped[int] = mapped_column(Integer, index=True)

    forecast_data: Mapped[float] = mapped_column(Float, default=0.0)
    forecast_cloud: Mapped[float] = mapped_column(Float, default=0.0)
    forecast_mobile: Mapped[float] = mapped_column(Float, default=0.0)
    actual_data: Mapped[float] = mapped_column(Float, default=0.0)
    actual_cloud: Mapped[float] = mapped_column(Float, default=0.0)
    actual_mobile: Mapped[float] = mapped_column(Float, default=0.0)

    achievement_pct: Mapped[float] = mapped_column(Float, default=0.0)   # overall: actual/forecast×100
    hit: Mapped[bool] = mapped_column(Boolean, default=False)            # achievement ≥ 100%
    submitted: Mapped[bool] = mapped_column(Boolean, default=False)      # a forecast was entered
    on_time: Mapped[bool] = mapped_column(Boolean, default=True)         # entered by Mon 11:00
    excused: Mapped[bool] = mapped_column(Boolean, default=False)        # whole-week leave → not scored
