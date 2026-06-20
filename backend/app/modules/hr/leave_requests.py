"""Leave booking & approvals (brief §12). Employees request time off; their manager (or admin)
approves/declines. Approval materialises ``LeaveRecord`` rows (source='request') so approved
leave immediately shows in the balance, calendar and Holiday Coverage — RepIQ becomes the place
people book time off, replacing the holiday-tracker spreadsheet for booking."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ...core import rbac
from ...core.audit import record_audit
from ...models import User
from . import services as svc
from .models import Employee, LeaveRecord, LeaveRequest

_TYPES = {"Holiday", "Sick", "Compassionate", "Unpaid", "Custom", "Appointment", "Other"}


def working_days(start: date, end: date, start_half: bool, end_half: bool) -> float:
    """Mon–Fri days in the inclusive range, less half-days at the ends."""
    if end < start:
        return 0.0
    wd = [start + timedelta(days=i) for i in range((end - start).days + 1) if (start + timedelta(days=i)).weekday() < 5]
    if not wd:
        return 0.0
    if start == end:
        return 0.5 if (start_half or end_half) else 1.0
    total = float(len(wd))
    if start_half and start.weekday() < 5:
        total -= 0.5
    if end_half and end.weekday() < 5:
        total -= 0.5
    return max(total, 0.0)


def _parse(v):
    try:
        return date.fromisoformat(v)
    except (TypeError, ValueError):
        raise HTTPException(400, "Dates must be YYYY-MM-DD")


def _req_dict(db, r: LeaveRequest) -> dict:
    def nm(uid):
        u = db.get(User, uid) if uid else None
        return u.name if u else None
    emp = r.employee
    return {
        "id": str(r.id), "employeeUserId": emp.user_id if emp else None,
        "employeeName": (emp.user.name if emp and emp.user else None),
        "leaveType": r.leave_type, "startDate": r.start_date.isoformat(), "endDate": r.end_date.isoformat(),
        "startHalf": r.start_half, "endHalf": r.end_half, "days": r.days, "reason": r.reason,
        "status": r.status, "requestedBy": nm(r.requested_by_id), "decidedBy": nm(r.decided_by_id),
        "decidedAt": r.decided_at.isoformat() if r.decided_at else None, "decisionNote": r.decision_note,
        "createdAt": r.created_at.isoformat() if r.created_at else None,
    }


def create_request(db: Session, emp: Employee, data: dict, scopes: set[str], actor, request) -> dict:
    # Self can request own leave; a manager/admin can also raise it for a team member.
    if not ({"self", "manager.team", "admin"} & scopes):
        raise HTTPException(403, "Not permitted")
    ltype = (data or {}).get("leave_type") or "Holiday"
    if ltype not in _TYPES:
        raise HTTPException(400, "Invalid leave type")
    start = _parse((data or {}).get("start_date"))
    end = _parse((data or {}).get("end_date") or (data or {}).get("start_date"))
    if end < start:
        raise HTTPException(400, "End date can't be before the start date")
    sh, eh = bool((data or {}).get("start_half")), bool((data or {}).get("end_half"))
    days = working_days(start, end, sh, eh)
    if days <= 0:
        raise HTTPException(400, "That range has no working days")
    req = LeaveRequest(employee_id=emp.id, leave_type=ltype, start_date=start, end_date=end,
                       start_half=sh, end_half=eh, days=days, reason=(data or {}).get("reason"),
                       status="pending", requested_by_id=getattr(actor, "id", None))
    db.add(req)
    record_audit(db, actor=actor, action="CREATE", entity_type="leave_request",
                 entity_id=emp.id, field="leave", new=f"{ltype} {start}–{end} ({days}d)", request=request)
    db.commit()
    db.refresh(req)
    return _req_dict(db, req)


def list_for_employee(db: Session, emp: Employee, scopes: set[str]) -> list[dict]:
    if not ({"self", "manager.team", "admin"} & scopes):
        raise HTTPException(403, "Not permitted")
    rows = (db.query(LeaveRequest).filter(LeaveRequest.employee_id == emp.id, LeaveRequest.deleted_at.is_(None))
            .order_by(LeaveRequest.start_date.desc()).all())
    return [_req_dict(db, r) for r in rows]


def pending_for_approver(db: Session, approver: User) -> list[dict]:
    """All pending requests this approver may act on — their team (managers) or everyone (admin)."""
    role = rbac.platform_role(approver)
    q = (db.query(LeaveRequest).filter(LeaveRequest.status == "pending", LeaveRequest.deleted_at.is_(None))
         .order_by(LeaveRequest.start_date.asc()))
    out = []
    for r in q.all():
        emp = r.employee
        if not emp or not emp.user:
            continue
        if role == rbac.ADMIN or (role == rbac.MANAGER and getattr(approver, "team_id", None)
                                  and emp.user.team_id == approver.team_id and emp.user_id != approver.id):
            out.append(_req_dict(db, r))
    return out


def _materialise(db: Session, req: LeaveRequest) -> None:
    d = req.start_date
    while d <= req.end_date:
        if d.weekday() < 5:
            if req.start_date == req.end_date:
                half = req.start_half or req.end_half
            else:
                half = (d == req.start_date and req.start_half) or (d == req.end_date and req.end_half)
            db.add(LeaveRecord(employee_id=req.employee_id, leave_date=d,
                               portion=0.5 if half else 1.0, leave_type=req.leave_type, source="request"))
        d += timedelta(days=1)


def _clear_records(db: Session, req: LeaveRequest) -> None:
    for lr in (db.query(LeaveRecord).filter(LeaveRecord.employee_id == req.employee_id,
                                            LeaveRecord.source == "request",
                                            LeaveRecord.leave_date >= req.start_date,
                                            LeaveRecord.leave_date <= req.end_date).all()):
        db.delete(lr)


def decide(db: Session, req_id: str, approve: bool, note: str | None, approver: User, request) -> dict:
    req = db.get(LeaveRequest, req_id)
    if not req or req.deleted_at is not None:
        raise HTTPException(404, "Request not found")
    emp = req.employee
    scopes = svc.viewer_scopes(db, approver, emp)
    if not ({"manager.team", "admin"} & scopes):
        raise HTTPException(403, "Only a manager or admin can decide this request")
    if req.status != "pending":
        raise HTTPException(400, f"Request is already {req.status}")
    req.status = "approved" if approve else "declined"
    req.decided_by_id = approver.id
    req.decided_at = datetime.utcnow()
    req.decision_note = note
    if approve:
        _materialise(db, req)
    record_audit(db, actor=approver, action="UPDATE", entity_type="leave_request",
                 entity_id=emp.id, field="status", new=req.status, request=request)
    db.commit()
    db.refresh(req)
    return _req_dict(db, req)


def cancel(db: Session, req_id: str, actor: User, request) -> dict:
    req = db.get(LeaveRequest, req_id)
    if not req or req.deleted_at is not None:
        raise HTTPException(404, "Request not found")
    emp = req.employee
    scopes = svc.viewer_scopes(db, actor, emp)
    is_requester = emp and emp.user_id == actor.id
    if not (is_requester or ({"manager.team", "admin"} & scopes)):
        raise HTTPException(403, "Not permitted")
    if req.status == "cancelled":
        return _req_dict(db, req)
    if req.status == "approved":
        _clear_records(db, req)            # take the booked days back out of the calendar/balance
    req.status = "cancelled"
    record_audit(db, actor=actor, action="UPDATE", entity_type="leave_request",
                 entity_id=emp.id, field="status", new="cancelled", request=request)
    db.commit()
    db.refresh(req)
    return _req_dict(db, req)
