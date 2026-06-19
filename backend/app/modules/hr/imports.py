"""SafeHR import + Holiday Tracker sync (brief §13 — migration tooling).

These run RepIQ's HR module **alongside** the live systems — they read an admin-supplied SafeHR
export / the existing Holiday Tracker and upsert HR records. Nothing here writes back to SafeHR
or decommissions anything. Matching is by **company email** to an existing RepIQ user; rows with
no matching user are reported, never auto-created (account creation is out of scope here).

Idempotent: re-running overwrites the same fields / re-syncs leave records.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime

from sqlalchemy.orm import Session

from ...core.audit import record_audit
from ...models import User
from . import services as svc
from .models import EmployeeEmergencyContact, LeaveRecord


# --------------------------------------------------------------- parsing helpers
def _clean(v):
    if v is None:
        return None
    s = str(v).strip().strip(",").strip()
    return s or None


def _date(v):
    s = _clean(v)
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _allowance_days(v):
    s = _clean(v)
    if not s:
        return None
    num = "".join(c for c in s if c.isdigit() or c == ".")
    try:
        return float(num) if num else None
    except ValueError:
        return None


def _working_pattern(hours_structure):
    s = (hours_structure or "").lower()
    if "part" in s:
        return "Part-time"
    if "full" in s:
        return "Full-time"
    return _clean(hours_structure)


def _join(*parts):
    vals = [p for p in (_clean(x) for x in parts) if p]
    return ", ".join(vals) or None


def parse_staff_csv(text: str) -> list[dict]:
    """Parse a SafeHR StaffDetails export into normalised per-person dicts. Pure (no DB)."""
    _BOM = "﻿"
    reader = csv.DictReader(io.StringIO(text.lstrip(_BOM)))
    out: list[dict] = []
    for raw in reader:
        # Strip a UTF-8 BOM that SafeHR prepends to the first header (e.g. the first column
        # arrives as "﻿First Name"); plain .strip() does not remove U+FEFF.
        r = { (k or "").lstrip(_BOM).strip(): v for k, v in raw.items() }
        company_email = (_clean(r.get("Company Email")) or "").lower() or None
        personal_email = (_clean(r.get("Personal Email")) or "").lower() or None
        if not company_email and not personal_email:
            continue
        weekly = None
        try:
            weekly = float(_clean(r.get("Weekly Hours"))) if _clean(r.get("Weekly Hours")) else None
        except ValueError:
            weekly = None
        rec = {
            "company_email": company_email,
            "personal_email": personal_email,
            "manager_name": _clean(r.get("Manager's Full Name")),
            "display_name": _join(r.get("First Name"), r.get("Surname")),
            "personal": {
                "title": _clean(r.get("Title")),
                "first_name": _clean(r.get("First Name")),
                "middle_name": _clean(r.get("Middle Initial")),
                "last_name": _clean(r.get("Surname")),
                "dob": _date(r.get("Date of Birth")),
                "sex": _clean(r.get("Male/Female")),
                "ni_number": _clean(r.get("National Insurance No.")),
            },
            "contact": {
                "work_email": _clean(r.get("Company Email")),
                "work_phone": _clean(r.get("Work Telephone")),
                "personal_email": _clean(r.get("Personal Email")),
                "personal_mobile": _clean(r.get("Personal Mobile")) or _clean(r.get("Home Telephone")),
                "addr_line1": _clean(r.get("Address Line 1")),
                "addr_line2": _join(r.get("Address Line 2"), r.get("Address Line 3")),
                "town": _clean(r.get("Town")),
                "postcode": _clean(r.get("Postcode")),
                "country": _clean(r.get("Country")),
            },
            "role": {
                "department": _clean(r.get("Department")),
            },
            "contract": {
                "contract_type": _clean(r.get("Permanent / Fixed Term")),
                "working_pattern": _working_pattern(_clean(r.get("Hours Structure"))),
                "weekly_hours": weekly,
                "fte": round(weekly / 40.0, 2) if weekly else None,
                "start_date": _date(r.get("Employment Start Date")),
                "continuous_service_date": _date(r.get("Continuous Service Start Date")),
                "probation_end_date": _date(r.get("Probation End Date")),
                "notice_period": _clean(r.get("Employee Notice Period")),
                "work_location": _clean(r.get("Work Location")),
            },
            "emergency": {
                "full_name": _clean(r.get("Emergency Contact (EC) Name")),
                "relation": _clean(r.get("EC Relationship")),
                "phone_primary": _clean(r.get("EC Phone Number")),
                "phone_secondary": _clean(r.get("EC Mobile Number")),
                "email": _clean(r.get("EC Email Address")),
                "address": _join(r.get("EC Address Line 1"), r.get("EC Address Line 2"),
                                 r.get("EC Address Line 3"), r.get("EC Town"),
                                 r.get("EC Country"), r.get("EC Postcode")),
            },
            "holiday": {
                "allowance_days": _allowance_days(r.get("Holiday Allowance")),
                "includes_bank_holidays": (_clean(r.get("Includes Bank Holidays")) or "").lower() == "yes",
            },
        }
        out.append(rec)
    return out


# --------------------------------------------------------------- matching
def _user_by_email(db: Session, email: str | None):
    if not email:
        return None
    return db.query(User).filter(User.email.ilike(email)).first()


def _match_user(db: Session, rec: dict):
    return _user_by_email(db, rec["company_email"]) or _user_by_email(db, rec["personal_email"])


def _resolve_manager(db: Session, users: list[User], manager_name: str | None):
    """Find the RepIQ user a SafeHR 'Manager's Full Name' refers to (tolerant name match)."""
    if not manager_name:
        return None
    from ...services.salesiq.roles import user_agent_match
    for u in users:
        if user_agent_match(u, manager_name):
            return u
    return None


# --------------------------------------------------------------- preview / apply
def preview_import(db: Session, records: list[dict]) -> dict:
    matched, unmatched = [], []
    for rec in records:
        u = _match_user(db, rec)
        if u:
            matched.append({"userId": u.id, "name": u.name, "email": u.email,
                            "safehrName": rec["display_name"],
                            "hasEmergency": bool(rec["emergency"]["full_name"]),
                            "manager": rec["manager_name"],
                            "holidayAllowance": rec["holiday"]["allowance_days"]})
        else:
            unmatched.append({"safehrName": rec["display_name"],
                              "companyEmail": rec["company_email"]})
    return {"total": len(records), "matched": matched, "unmatched": unmatched,
            "matchedCount": len(matched), "unmatchedCount": len(unmatched)}


def _set_present(row, data: dict):
    """Set only the fields the export actually provided (don't wipe existing values with blanks)."""
    for k, v in data.items():
        if v is not None and v != "":
            setattr(row, k, v)


def apply_import(db: Session, records: list[dict], actor: User, request) -> dict:
    users = db.query(User).all()
    applied, skipped = [], []
    for rec in records:
        u = _match_user(db, rec)
        if not u:
            skipped.append(rec["display_name"])
            continue
        emp = svc.get_or_create_employee(db, u)

        if rec["contract"].get("start_date") and not emp.start_date:
            emp.start_date = rec["contract"]["start_date"]

        _set_present(emp.personal, rec["personal"])
        _set_present(emp.contact, rec["contact"])
        _set_present(emp.role, rec["role"])
        _set_present(emp.employment, rec["contract"])
        # Holiday entitlement
        if rec["holiday"].get("allowance_days") is not None:
            emp.holiday.allowance_days = rec["holiday"]["allowance_days"]
        emp.holiday.includes_bank_holidays = rec["holiday"]["includes_bank_holidays"]

        # Line manager (Employee.reports_to_id) from the SafeHR manager name.
        mgr = _resolve_manager(db, users, rec["manager_name"])
        if mgr and mgr.id != u.id:
            emp.reports_to_id = svc.get_or_create_employee(db, mgr).id

        # Emergency contact — upsert one (match existing by name, else add).
        ec = rec["emergency"]
        if ec.get("full_name"):
            existing = next((e for e in emp.emergency_contacts
                             if (e.full_name or "").lower() == ec["full_name"].lower()), None)
            target = existing or EmployeeEmergencyContact(employee_id=emp.id, priority=1)
            for k, v in ec.items():
                setattr(target, k, v)
            if existing is None:
                db.add(target)

        record_audit(db, actor=actor, action="IMPORT", entity_type="employee",
                     entity_id=emp.id, field="safehr_import", new=rec["display_name"], request=request)
        applied.append(u.name)
    db.commit()
    return {"appliedCount": len(applied), "applied": applied,
            "skippedCount": len(skipped), "skipped": skipped}


# --------------------------------------------------------------- holiday tracker sync
_LABEL_TO_TYPE = {
    "Holiday": "Holiday", "Half day": "Holiday", "Half day (am)": "Holiday", "Half day (pm)": "Holiday",
    "Sick": "Sick", "Sick (am)": "Sick", "Sick (pm)": "Sick",
    "Compassionate": "Compassionate", "Unpaid leave": "Unpaid", "Custom leave": "Custom",
}


def sync_holiday_from_tracker(db: Session, actor: User, request) -> dict:
    """Read the existing Holiday Tracker and mirror its marks into LeaveRecord rows
    (source='tracker'). Idempotent: replaces all tracker-sourced records per matched employee."""
    from ...services.salesiq import trackers
    from ...services.salesiq.roles import user_agent_match
    if not trackers.holiday_configured():
        return {"ok": False, "error": "Holiday Tracker is not configured (set its URL/path in Settings)."}

    rows = trackers.holiday_rows()
    if not rows:
        return {"ok": False, "error": "The Holiday Tracker returned no rows.", "rows": 0}

    users = [u for u in db.query(User).all() if u.active]
    # Group tracker rows by matched user.
    by_user: dict[int, list] = {}
    unmatched_names = set()
    for r in rows:
        nm = r.get("name")
        u = next((x for x in users if user_agent_match(x, nm)), None)
        if not u:
            unmatched_names.add(nm)
            continue
        by_user.setdefault(u.id, []).append(r)

    imported = 0
    people = 0
    for uid, urows in by_user.items():
        u = db.get(User, uid)
        emp = svc.get_or_create_employee(db, u)
        # wipe prior tracker-sourced records, then re-insert (idempotent)
        for lr in list(emp.leave_records):
            if lr.source == "tracker":
                db.delete(lr)
        for r in urows:
            db.add(LeaveRecord(
                employee_id=emp.id, leave_date=r["date"],
                portion=0.5 if r.get("half") else 1.0,
                leave_type=_LABEL_TO_TYPE.get(r.get("label"), "Holiday"),
                code=str(r.get("code") or "")[:10], source="tracker"))
            imported += 1
        people += 1
        record_audit(db, actor=actor, action="IMPORT", entity_type="employee_leave",
                     entity_id=emp.id, field="holiday_sync", new=str(len(urows)), request=request)
    db.commit()
    return {"ok": True, "rows": len(rows), "people": people, "imported": imported,
            "unmatched": sorted(n for n in unmatched_names if n)}
