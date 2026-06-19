"""In-app leave source of truth — reads HR ``LeaveRecord`` rows (populated by the Holiday Tracker
sync + manual Sick & Absence entry) so the rest of the app no longer reads the external tracker
directly. Holiday Coverage, the Holiday Calendar, the morning dashboards and Ask RepIQ all go
through here, querying RepIQ's own data.

The Holiday Tracker remains the upstream *feed* (via ``imports.sync_holiday_from_tracker``); these
functions only read what's already in the database.
"""
from __future__ import annotations

import calendar as _cal
from datetime import date

from sqlalchemy.orm import Session

from ...models import User
from .models import Employee, LeaveRecord

# All leave types we recognise (matches the record form + tracker sync mapping).
LEAVE_TYPES = ("Holiday", "Sick", "Compassionate", "Unpaid", "Custom", "Appointment", "Other")


def leave_rows(db: Session, start: date | None = None, end: date | None = None) -> list[dict]:
    """Every active employee's leave days in [start, end], shaped like the old tracker rows
    ({name, date, label, half, type, code}) plus a real ``user_id``."""
    q = (db.query(LeaveRecord, User)
         .join(Employee, LeaveRecord.employee_id == Employee.id)
         .join(User, Employee.user_id == User.id)
         .filter(User.active.is_(True)))
    if start is not None:
        q = q.filter(LeaveRecord.leave_date >= start)
    if end is not None:
        q = q.filter(LeaveRecord.leave_date <= end)
    out = []
    for lr, u in q.all():
        out.append({
            "user_id": u.id, "name": u.name, "short_name": u.short_name,
            "date": lr.leave_date, "type": lr.leave_type, "label": lr.leave_type,
            "half": (lr.portion or 1.0) == 0.5, "code": lr.code,
        })
    return out


def user_leave(db: Session, user_id: int, start: date | None = None, end: date | None = None) -> list[dict]:
    return [r for r in leave_rows(db, start, end) if r["user_id"] == user_id]


def has_any(db: Session) -> bool:
    return db.query(LeaveRecord.id).first() is not None


def _cell_code(leave_type: str, half: bool) -> str:
    """Map a leave type to the single-letter code the calendar UI understands."""
    t = (leave_type or "").lower()
    if t == "holiday":
        return "HD" if half else "H"
    if t == "sick":
        return "S1" if half else "S"
    if t == "compassionate":
        return "C"
    return "N"          # unpaid / custom / appointment / other → generic "Leave"


def leave_calendar(db: Session, year: int, month: int, team: str | None = None) -> dict:
    """Month grid (all active users × days) for the calendar popup, built from in-app leave."""
    ndays = _cal.monthrange(year, month)[1]
    days = []
    for d in range(1, ndays + 1):
        dt = date(year, month, d)
        days.append({"day": d, "weekday": dt.strftime("%a"), "weekend": dt.weekday() >= 5})

    rows = leave_rows(db, date(year, month, 1), date(year, month, ndays))
    by_user: dict[int, dict] = {}
    for r in rows:
        by_user.setdefault(r["user_id"], {})[r["date"].day] = _cell_code(r["type"], r["half"])

    users = db.query(User).filter(User.active.is_(True)).order_by(User.name).all()
    people = []
    for u in users:
        team_name = (u.team.name if getattr(u, "team", None) else "No team")
        people.append({"name": u.name, "team": team_name, "cells": by_user.get(u.id, {})})

    teams_available = sorted({p["team"] for p in people})
    team_l = (team or "").strip().lower()
    if team_l and team_l not in ("", "all", "all teams"):
        people = [p for p in people if p["team"].lower() == team_l]
    return {"connected": True, "found": True, "year": year, "month": month, "days": days,
            "people": people, "teamsAvailable": teams_available, "team": team_l or "all"}
