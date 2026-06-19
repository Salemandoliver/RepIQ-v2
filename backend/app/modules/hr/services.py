"""HR services — employee get-or-create, viewer-scope resolution, projection-aware reads, and
audited writes. Keeps the router thin."""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ...core import rbac
from ...core.audit import record_audit
from ...models import User
from . import permissions as perms
from .models import Employee, EmployeeContact, EmployeeEmergencyContact, EmployeePersonal

_PERSONAL_FIELDS = ["preferred_name", "profile_photo", "title", "first_name", "middle_name",
                    "last_name", "dob", "sex", "gender_identity", "nationality", "about", "ni_number"]
_CONTACT_FIELDS = ["personal_email", "personal_mobile", "addr_line1", "addr_line2", "town",
                   "county", "postcode", "country", "preferred_contact_method", "work_email", "work_phone"]
_EMERGENCY_FIELDS = ["full_name", "relation", "phone_primary", "phone_secondary", "email",
                     "address", "priority", "notes"]
_MAX_PHOTO_CHARS = 2_800_000          # ~2MB image as a base64 data URL


# --------------------------------------------------------------- employee lifecycle
def get_or_create_employee(db: Session, user: User) -> Employee:
    """Every user has exactly one HR record; create it (and its 1:1 child rows) on first access."""
    emp = db.query(Employee).filter(Employee.user_id == user.id).first()
    if emp is None:
        emp = Employee(user_id=user.id, status="active")
        db.add(emp)
        db.flush()
    if emp.personal is None:
        db.add(EmployeePersonal(employee_id=emp.id))
    if emp.contact is None:
        db.add(EmployeeContact(employee_id=emp.id))
    db.commit()
    db.refresh(emp)
    return emp


def employee_for(db: Session, employee_id) -> Employee:
    emp = db.get(Employee, employee_id)
    if not emp or emp.deleted_at is not None:
        raise HTTPException(404, "Employee not found")
    if emp.personal is None:
        db.add(EmployeePersonal(employee_id=emp.id))
    if emp.contact is None:
        db.add(EmployeeContact(employee_id=emp.id))
    db.commit()
    db.refresh(emp)
    return emp


# --------------------------------------------------------------- scopes
def viewer_scopes(db: Session, viewer: User, emp: Employee) -> set[str]:
    """Projection scope tokens the viewer holds for this employee record."""
    is_self = emp.user_id == viewer.id
    manages = False
    if rbac.platform_role(viewer) == rbac.MANAGER and not is_self:
        tv = getattr(viewer, "team_id", None)
        tt = emp.user.team_id if emp.user else None
        manages = bool(tv and tt and tv == tt)
    return rbac.projection_scopes(viewer, is_self=is_self, manages_target_team=manages)


# --------------------------------------------------------------- serialisation
def _row_dict(row, fields):
    return {f: getattr(row, f, None) for f in fields} if row else {f: None for f in fields}


def summary(db: Session, emp: Employee) -> dict:
    u = emp.user
    pers = emp.personal
    return {
        "employeeId": str(emp.id), "userId": emp.user_id,
        "name": u.name if u else None,
        "preferredName": (pers.preferred_name if pers else None),
        "knownAs": (pers.preferred_name or (u.name if u else None)) if pers else (u.name if u else None),
        "photo": (pers.profile_photo if pers else None),
        "email": u.email if u else None,
        "jobTitle": u.job_title if u else None,
        "teamId": u.team_id if u else None,
        "employeeCode": emp.employee_code,
        "startDate": emp.start_date.isoformat() if emp.start_date else None,
        "status": emp.status,
        "platformRole": rbac.platform_role(u) if u else None,
    }


def personal_view(emp: Employee, scopes: set[str]) -> dict:
    data = _row_dict(emp.personal, _PERSONAL_FIELDS)
    if data.get("dob"):
        data["dob"] = data["dob"].isoformat()
    return perms.PERSONAL.project_flat(data, scopes)


def contact_view(emp: Employee, scopes: set[str]) -> dict:
    return perms.CONTACT.project_flat(_row_dict(emp.contact, _CONTACT_FIELDS), scopes)


def emergency_view(emp: Employee, scopes: set[str]) -> list[dict]:
    if not perms.EMERGENCY.can_read("self.emergency", scopes):
        return []
    out = []
    for ec in emp.emergency_contacts:
        out.append({"id": str(ec.id), **_row_dict(ec, _EMERGENCY_FIELDS)})
    return out


def composite(db: Session, emp: Employee, scopes: set[str]) -> dict:
    out = {"summary": summary(db, emp)}
    if perms.PERSONAL.readable_group_names(scopes):
        out["personal"] = personal_view(emp, scopes)
    if perms.CONTACT.readable_group_names(scopes):
        out["contact"] = contact_view(emp, scopes)
    if perms.EMERGENCY.can_read("self.emergency", scopes):
        out["emergencyContacts"] = emergency_view(emp, scopes)
    return out


# --------------------------------------------------------------- audited writes
def _coerce(field, value):
    if field == "dob" and value:
        from datetime import date
        try:
            return date.fromisoformat(value)
        except (TypeError, ValueError):
            raise HTTPException(400, "dob must be YYYY-MM-DD")
    return value


def update_personal(db, emp, changes: dict, scopes, actor, request):
    if changes.get("profile_photo"):
        photo = changes["profile_photo"]
        if not isinstance(photo, str) or not photo.startswith("data:image/"):
            raise HTTPException(400, "profile_photo must be an image data URL")
        if len(photo) > _MAX_PHOTO_CHARS:
            raise HTTPException(413, "Photo too large — please use an image under ~2MB")
    allowed, denied = perms.PERSONAL.filter_writes(changes, scopes)
    if denied:
        raise HTTPException(403, f"Not permitted to edit: {', '.join(denied)}")
    row = emp.personal
    for field, value in allowed.items():
        old = getattr(row, field, None)
        new = _coerce(field, value)
        if old != new:
            setattr(row, field, new)
            record_audit(db, actor=actor, action="UPDATE", entity_type="employee_personal",
                         entity_id=emp.id, field=field, old=old, new=new, request=request)
    db.commit()


def update_contact(db, emp, changes: dict, scopes, actor, request):
    allowed, denied = perms.CONTACT.filter_writes(changes, scopes)
    if denied:
        raise HTTPException(403, f"Not permitted to edit: {', '.join(denied)}")
    row = emp.contact
    for field, value in allowed.items():
        old = getattr(row, field, None)
        if old != value:
            setattr(row, field, value)
            record_audit(db, actor=actor, action="UPDATE", entity_type="employee_contact",
                         entity_id=emp.id, field=field, old=old, new=value, request=request)
    db.commit()
