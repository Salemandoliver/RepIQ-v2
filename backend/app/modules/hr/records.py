"""Performance & reviews, Training & qualifications, and Goals (brief §12).

Per-employee record lists. Viewable by self / the team manager / admin; created and removed by
the team manager or admin (HR-managed). Goal progress can also be nudged by the same. Audited.
"""
from __future__ import annotations

from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ...core.audit import record_audit
from ...models import User
from .models import Goal, PerformanceReview, TrainingRecord


def can_view(scopes: set[str]) -> bool:
    return bool({"self", "manager.team", "admin"} & scopes)


def can_manage(scopes: set[str]) -> bool:
    return bool({"manager.team", "admin"} & scopes)


def _date(v):
    if not v:
        return None
    try:
        return date.fromisoformat(v)
    except (TypeError, ValueError):
        raise HTTPException(400, "Dates must be YYYY-MM-DD")


def _name(db, uid):
    u = db.get(User, uid) if uid else None
    return u.name if u else None


# --------------------------------------------------------------- reviews
def list_reviews(db: Session, emp, scopes) -> list[dict]:
    if not can_view(scopes):
        raise HTTPException(403, "Not permitted")
    rows = (db.query(PerformanceReview).filter(PerformanceReview.employee_id == emp.id,
            PerformanceReview.deleted_at.is_(None)).order_by(PerformanceReview.review_date.desc()).all())
    return [{"id": str(r.id), "date": r.review_date.isoformat(), "type": r.review_type,
             "rating": r.rating, "summary": r.summary,
             "nextDate": r.next_review_date.isoformat() if r.next_review_date else None,
             "reviewer": _name(db, r.reviewer_id)} for r in rows]


def add_review(db, emp, body, scopes, actor, request) -> dict:
    if not can_manage(scopes):
        raise HTTPException(403, "Only a manager or admin can add reviews")
    r = PerformanceReview(
        employee_id=emp.id, review_date=_date(body.get("date")) or date.today(),
        review_type=body.get("type") or "1-to-1", rating=body.get("rating"),
        summary=body.get("summary"), next_review_date=_date(body.get("next_date")),
        reviewer_id=getattr(actor, "id", None))
    db.add(r)
    record_audit(db, actor=actor, action="CREATE", entity_type="performance_review",
                 entity_id=emp.id, field="type", new=r.review_type, request=request)
    db.commit()
    return {"id": str(r.id)}


# --------------------------------------------------------------- training & qualifications
def list_training(db: Session, emp, scopes, kind: str | None = None) -> list[dict]:
    if not can_view(scopes):
        raise HTTPException(403, "Not permitted")
    q = db.query(TrainingRecord).filter(TrainingRecord.employee_id == emp.id, TrainingRecord.deleted_at.is_(None))
    if kind:
        q = q.filter(TrainingRecord.kind == kind)
    rows = q.order_by(TrainingRecord.completed_date.desc().nullslast()).all()
    return [{"id": str(t.id), "kind": t.kind, "name": t.name, "provider": t.provider,
             "completedDate": t.completed_date.isoformat() if t.completed_date else None,
             "expiryDate": t.expiry_date.isoformat() if t.expiry_date else None,
             "status": t.status, "notes": t.notes} for t in rows]


def add_training(db, emp, body, scopes, actor, request) -> dict:
    if not can_manage(scopes):
        raise HTTPException(403, "Only a manager or admin can add this")
    if not (body.get("name") or "").strip():
        raise HTTPException(400, "Name is required")
    t = TrainingRecord(
        employee_id=emp.id, kind=body.get("kind") or "Training", name=body["name"].strip(),
        provider=body.get("provider"), completed_date=_date(body.get("completed_date")),
        expiry_date=_date(body.get("expiry_date")), status=body.get("status"), notes=body.get("notes"))
    db.add(t)
    record_audit(db, actor=actor, action="CREATE", entity_type="training_record",
                 entity_id=emp.id, field="name", new=t.name, request=request)
    db.commit()
    return {"id": str(t.id)}


# --------------------------------------------------------------- goals
def list_goals(db: Session, emp, scopes) -> list[dict]:
    if not can_view(scopes):
        raise HTTPException(403, "Not permitted")
    rows = (db.query(Goal).filter(Goal.employee_id == emp.id, Goal.deleted_at.is_(None))
            .order_by(Goal.created_at.desc()).all())
    return [{"id": str(g.id), "title": g.title, "description": g.description,
             "targetDate": g.target_date.isoformat() if g.target_date else None,
             "status": g.status, "progress": g.progress, "notes": g.notes} for g in rows]


def add_goal(db, emp, body, scopes, actor, request) -> dict:
    if not can_manage(scopes):
        raise HTTPException(403, "Only a manager or admin can add goals")
    if not (body.get("title") or "").strip():
        raise HTTPException(400, "Title is required")
    g = Goal(employee_id=emp.id, title=body["title"].strip(), description=body.get("description"),
             target_date=_date(body.get("target_date")), status=body.get("status") or "In progress",
             progress=int(body.get("progress") or 0), notes=body.get("notes"),
             created_by_id=getattr(actor, "id", None))
    db.add(g)
    record_audit(db, actor=actor, action="CREATE", entity_type="goal",
                 entity_id=emp.id, field="title", new=g.title, request=request)
    db.commit()
    return {"id": str(g.id)}


def update_goal(db, emp, goal_id, body, scopes, actor, request) -> dict:
    if not can_manage(scopes):
        raise HTTPException(403, "Not permitted")
    g = db.get(Goal, goal_id)
    if not g or g.employee_id != emp.id:
        raise HTTPException(404, "Goal not found")
    if "status" in body:
        g.status = body["status"]
    if "progress" in body:
        g.progress = max(0, min(100, int(body["progress"] or 0)))
    record_audit(db, actor=actor, action="UPDATE", entity_type="goal",
                 entity_id=emp.id, field="status", new=f"{g.status} {g.progress}%", request=request)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------- generic delete
_MODELS = {"review": PerformanceReview, "training": TrainingRecord, "goal": Goal}


def delete_record(db, emp, kind: str, rec_id: str, scopes, actor, request) -> dict:
    if not can_manage(scopes):
        raise HTTPException(403, "Not permitted")
    model = _MODELS.get(kind)
    if not model:
        raise HTTPException(400, "Unknown record type")
    row = db.get(model, rec_id)
    if not row or row.employee_id != emp.id:
        raise HTTPException(404, "Not found")
    db.delete(row)
    record_audit(db, actor=actor, action="DELETE", entity_type=f"hr_{kind}",
                 entity_id=emp.id, field="id", old=str(rec_id), request=request)
    db.commit()
    return {"ok": True}
