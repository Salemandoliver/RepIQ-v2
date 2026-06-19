"""HR API (brief §11) — Phase 1: own profile (self-service), personal/contact/emergency,
and manager/admin read of team/all employees. Every response is projected to the caller's
scopes; every sensitive write is audited."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ...auth import get_current_user
from ...core import rbac
from ...core.audit import record_audit
from ...db import get_db
from ...models import User
from . import imports as hr_imports
from . import services as svc
from .models import Employee, EmployeeEmergencyContact


def _require_admin(user: User):
    if rbac.platform_role(user) != rbac.ADMIN:
        raise HTTPException(403, "Admin access required")

router = APIRouter(prefix="/api/v1/hr", tags=["hr"])


# ----------------------------------------------------------------- self-service ("me")
@router.get("/me")
def my_profile(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    emp = svc.get_or_create_employee(db, user)
    return svc.composite(db, emp, {"self"})


@router.get("/me/personal")
def my_personal(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    emp = svc.get_or_create_employee(db, user)
    return svc.personal_view(emp, {"self"})


@router.put("/me/personal")
def update_my_personal(body: dict, request: Request, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    emp = svc.get_or_create_employee(db, user)
    svc.update_personal(db, emp, body or {}, {"self"}, user, request)
    db.refresh(emp)
    return svc.personal_view(emp, {"self"})


@router.get("/me/contact")
def my_contact(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    emp = svc.get_or_create_employee(db, user)
    return svc.contact_view(emp, {"self"})


@router.put("/me/contact")
def update_my_contact(body: dict, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    emp = svc.get_or_create_employee(db, user)
    svc.update_contact(db, emp, body or {}, {"self"}, user, request)
    db.refresh(emp)
    return svc.contact_view(emp, {"self"})


# ----------------------------------------------------------------- emergency contacts (self)
@router.get("/me/emergency-contacts")
def my_emergency(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    emp = svc.get_or_create_employee(db, user)
    return svc.emergency_view(emp, {"self"})


@router.post("/me/emergency-contacts")
def add_my_emergency(body: dict, request: Request, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    emp = svc.get_or_create_employee(db, user)
    ec = EmployeeEmergencyContact(
        employee_id=emp.id,
        full_name=(body or {}).get("full_name"), relation=(body or {}).get("relation"),
        phone_primary=(body or {}).get("phone_primary"), phone_secondary=(body or {}).get("phone_secondary"),
        email=(body or {}).get("email"), address=(body or {}).get("address"),
        priority=int((body or {}).get("priority") or 1), notes=(body or {}).get("notes"))
    db.add(ec)
    record_audit(db, actor=user, action="CREATE", entity_type="employee_emergency_contact",
                 entity_id=emp.id, field="full_name", new=ec.full_name, request=request)
    db.commit()
    return svc.emergency_view(emp, {"self"})


@router.put("/me/emergency-contacts/{ec_id}")
def update_my_emergency(ec_id: str, body: dict, request: Request, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    emp = svc.get_or_create_employee(db, user)
    ec = db.get(EmployeeEmergencyContact, ec_id)
    if not ec or ec.employee_id != emp.id or ec.deleted_at is not None:
        raise HTTPException(404, "Emergency contact not found")
    for f in ("full_name", "relation", "phone_primary", "phone_secondary", "email", "address", "notes"):
        if f in (body or {}):
            setattr(ec, f, body[f])
    if "priority" in (body or {}):
        ec.priority = int(body["priority"] or 1)
    record_audit(db, actor=user, action="UPDATE", entity_type="employee_emergency_contact",
                 entity_id=emp.id, field="full_name", new=ec.full_name, request=request)
    db.commit()
    return svc.emergency_view(emp, {"self"})


@router.delete("/me/emergency-contacts/{ec_id}")
def delete_my_emergency(ec_id: str, request: Request, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    from datetime import datetime
    emp = svc.get_or_create_employee(db, user)
    ec = db.get(EmployeeEmergencyContact, ec_id)
    if not ec or ec.employee_id != emp.id:
        raise HTTPException(404, "Emergency contact not found")
    ec.deleted_at = datetime.utcnow()
    record_audit(db, actor=user, action="DELETE", entity_type="employee_emergency_contact",
                 entity_id=emp.id, field="full_name", old=ec.full_name, request=request)
    db.commit()
    return {"ok": True}


# ----------------------------------------------------------------- directory (manager/admin)
@router.get("/employees")
def list_employees(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    role = rbac.platform_role(user)
    if role not in (rbac.MANAGER, rbac.ADMIN):
        raise HTTPException(403, "Manager or admin access required")
    q = db.query(User).filter(User.active.is_(True))
    if role == rbac.MANAGER and getattr(user, "team_id", None):
        q = q.filter(User.team_id == user.team_id)
    out = []
    for u in q.order_by(User.name).all():
        emp = svc.get_or_create_employee(db, u)
        out.append(svc.summary(db, emp))
    return {"employees": out}


# The {user_id} below is a USER id (the identifier the rest of the app uses); it resolves to
# that person's HR record. Every response is projected to the caller's scopes for the target.
@router.get("/employees/{user_id}")
def get_employee(user_id: int, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    emp = svc.employee_by_user(db, user_id)
    scopes = svc.viewer_scopes(db, user, emp)
    if not scopes:
        raise HTTPException(403, "Not permitted")
    return svc.composite(db, emp, scopes)


@router.put("/employees/{user_id}/personal")
def put_employee_personal(user_id: int, body: dict, request: Request,
                          db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    emp = svc.employee_by_user(db, user_id)
    scopes = svc.viewer_scopes(db, user, emp)
    svc.update_personal(db, emp, body or {}, scopes, user, request)
    db.refresh(emp)
    return svc.personal_view(emp, scopes)


@router.put("/employees/{user_id}/contact")
def put_employee_contact(user_id: int, body: dict, request: Request,
                         db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    emp = svc.employee_by_user(db, user_id)
    scopes = svc.viewer_scopes(db, user, emp)
    svc.update_contact(db, emp, body or {}, scopes, user, request)
    db.refresh(emp)
    return svc.contact_view(emp, scopes)


@router.put("/employees/{user_id}/role")
def put_employee_role(user_id: int, body: dict, request: Request,
                      db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    emp = svc.employee_by_user(db, user_id)
    scopes = svc.viewer_scopes(db, user, emp)
    svc.update_role(db, emp, body or {}, scopes, user, request)
    db.refresh(emp)
    return svc.role_view(db, emp, scopes)


@router.put("/employees/{user_id}/contract-details")
def put_employee_contract_details(user_id: int, body: dict, request: Request,
                                  db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    emp = svc.employee_by_user(db, user_id)
    scopes = svc.viewer_scopes(db, user, emp)
    svc.update_contract_details(db, emp, body or {}, scopes, user, request)
    db.refresh(emp)
    return svc.contract_details_view(emp, scopes)


@router.put("/employees/{user_id}/holiday")
def put_employee_holiday(user_id: int, body: dict, request: Request,
                         db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    emp = svc.employee_by_user(db, user_id)
    scopes = svc.viewer_scopes(db, user, emp)
    svc.update_holiday(db, emp, body or {}, scopes, user, request)
    db.refresh(emp)
    return svc.holiday_view(emp, scopes)


# ----------------------------------------------------------------- migration tooling (admin)
@router.post("/import/safehr/preview")
def safehr_preview(body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_admin(user)
    records = hr_imports.parse_staff_csv((body or {}).get("csv") or "")
    if not records:
        raise HTTPException(400, "No staff rows found — is this a SafeHR StaffDetails CSV export?")
    return hr_imports.preview_import(db, records)


@router.post("/import/safehr/apply")
def safehr_apply(body: dict, request: Request,
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_admin(user)
    records = hr_imports.parse_staff_csv((body or {}).get("csv") or "")
    if not records:
        raise HTTPException(400, "No staff rows found in the upload.")
    return hr_imports.apply_import(db, records, user, request)


@router.post("/import/holiday/sync")
def holiday_sync(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_admin(user)
    return hr_imports.sync_holiday_from_tracker(db, user, request)


@router.post("/employees/{user_id}/leave")
def add_leave(user_id: int, body: dict, request: Request,
              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    emp = svc.employee_by_user(db, user_id)
    scopes = svc.viewer_scopes(db, user, emp)
    return svc.record_leave(db, emp, body or {}, scopes, user, request)


@router.delete("/employees/{user_id}/leave/{leave_id}")
def remove_leave(user_id: int, leave_id: str, request: Request,
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    emp = svc.employee_by_user(db, user_id)
    scopes = svc.viewer_scopes(db, user, emp)
    return svc.delete_leave(db, emp, leave_id, scopes, user, request)


@router.get("/employees/{user_id}/history")
def employee_history(user_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    emp = svc.employee_by_user(db, user_id)
    scopes = svc.viewer_scopes(db, user, emp)
    return {"history": svc.history(db, emp, scopes)}


@router.put("/employees/{user_id}/emergency-contacts/{ec_id}")
def edit_employee_emergency(user_id: int, ec_id: str, body: dict, request: Request,
                            db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    emp = svc.employee_by_user(db, user_id)
    scopes = svc.viewer_scopes(db, user, emp)
    return svc.update_emergency(db, emp, ec_id, body or {}, scopes, user, request)


@router.post("/employees/{user_id}/emergency-contacts")
def add_employee_emergency(user_id: int, body: dict, request: Request,
                           db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from . import permissions as perms
    emp = svc.employee_by_user(db, user_id)
    scopes = svc.viewer_scopes(db, user, emp)
    if not perms.EMERGENCY.can_write("self.emergency", scopes):
        raise HTTPException(403, "Not permitted")
    ec = EmployeeEmergencyContact(
        employee_id=emp.id,
        full_name=(body or {}).get("full_name"), relation=(body or {}).get("relation"),
        phone_primary=(body or {}).get("phone_primary"), phone_secondary=(body or {}).get("phone_secondary"),
        email=(body or {}).get("email"), address=(body or {}).get("address"),
        priority=int((body or {}).get("priority") or 1), notes=(body or {}).get("notes"))
    db.add(ec)
    record_audit(db, actor=user, action="CREATE", entity_type="employee_emergency_contact",
                 entity_id=emp.id, field="full_name", new=ec.full_name, request=request)
    db.commit()
    return svc.emergency_view(emp, scopes)


@router.delete("/employees/{user_id}/emergency-contacts/{ec_id}")
def delete_employee_emergency(user_id: int, ec_id: str, request: Request,
                              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from datetime import datetime
    from . import permissions as perms
    emp = svc.employee_by_user(db, user_id)
    scopes = svc.viewer_scopes(db, user, emp)
    if not perms.EMERGENCY.can_write("self.emergency", scopes):
        raise HTTPException(403, "Not permitted")
    ec = db.get(EmployeeEmergencyContact, ec_id)
    if not ec or ec.employee_id != emp.id:
        raise HTTPException(404, "Emergency contact not found")
    ec.deleted_at = datetime.utcnow()
    record_audit(db, actor=user, action="DELETE", entity_type="employee_emergency_contact",
                 entity_id=emp.id, field="full_name", old=ec.full_name, request=request)
    db.commit()
    return {"ok": True}
