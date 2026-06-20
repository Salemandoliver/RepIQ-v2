"""HR documents service (brief §12 — Documents). Upload/list/download/delete employee documents
and file notes, with R2-or-DB storage and audit. Permission-gated by the caller's scopes."""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ...config import settings
from ...core import storage
from ...core.audit import record_audit
from ...models import User
from .models import EmployeeDocument, EmployeeDocumentBlob, EmployeeFileNote

# Categories offered in the UI (free text also allowed).
CATEGORIES = ["Contractual/General Employment", "Right to Work", "Policy", "Payroll",
              "Performance", "Training", "Other"]


def can_view(scopes: set[str]) -> bool:
    return bool({"self", "manager.team", "admin"} & scopes)


def can_manage(scopes: set[str]) -> bool:
    """Upload — admins and the person's team manager (HR-managed records)."""
    return bool({"admin", "manager.team"} & scopes)


def can_delete(scopes: set[str]) -> bool:
    return "admin" in scopes


def _name(db: Session, uid: int | None) -> str | None:
    if not uid:
        return None
    u = db.get(User, uid)
    return u.name if u else None


def list_documents(db: Session, emp, scopes: set[str]) -> list[dict]:
    if not can_view(scopes):
        raise HTTPException(403, "Not permitted")
    docs = (db.query(EmployeeDocument)
            .filter(EmployeeDocument.employee_id == emp.id, EmployeeDocument.deleted_at.is_(None))
            .order_by(EmployeeDocument.created_at.desc()).all())
    return [{
        "id": str(d.id), "filename": d.filename, "category": d.category,
        "contentType": d.content_type, "size": d.size_bytes, "notes": d.notes,
        "uploadedBy": _name(db, d.uploaded_by_id),
        "uploadedAt": d.created_at.isoformat() if d.created_at else None,
        "backend": d.backend,
    } for d in docs]


def upload_document(db: Session, emp, *, data: bytes, filename: str, content_type: str | None,
                    category: str | None, notes: str | None, scopes: set[str], actor, request) -> dict:
    if not can_manage(scopes):
        raise HTTPException(403, "Only a manager or admin can store documents")
    cap = settings.max_document_mb * 1024 * 1024
    if len(data) > cap:
        raise HTTPException(413, f"File too large — limit is {settings.max_document_mb} MB")
    if not data:
        raise HTTPException(400, "Empty file")
    key = storage.new_key(f"hr/{emp.id}", filename)
    backend = storage.save(key, data, content_type)
    doc = EmployeeDocument(employee_id=emp.id, filename=filename or "document",
                           category=category, content_type=content_type, size_bytes=len(data),
                           backend=backend, storage_key=key, notes=notes,
                           uploaded_by_id=getattr(actor, "id", None))
    db.add(doc)
    db.flush()
    if backend == storage.DB:
        db.add(EmployeeDocumentBlob(document_id=doc.id, data=data))
    record_audit(db, actor=actor, action="CREATE", entity_type="employee_document",
                 entity_id=emp.id, field="filename", new=doc.filename, request=request)
    db.commit()
    return {"id": str(doc.id), "filename": doc.filename}


def get_document(db: Session, emp, doc_id: str, scopes: set[str]):
    if not can_view(scopes):
        raise HTTPException(403, "Not permitted")
    doc = db.get(EmployeeDocument, doc_id)
    if not doc or doc.employee_id != emp.id or doc.deleted_at is not None:
        raise HTTPException(404, "Document not found")
    if doc.backend == storage.DB:
        blob = db.get(EmployeeDocumentBlob, doc.id)
        if not blob:
            raise HTTPException(404, "Document data missing")
        data = blob.data
    else:
        data = storage.load(doc.backend, doc.storage_key)
    return doc.filename, (doc.content_type or "application/octet-stream"), data


def delete_document(db: Session, emp, doc_id: str, scopes: set[str], actor, request) -> dict:
    if not can_delete(scopes):
        raise HTTPException(403, "Only an admin can delete documents")
    doc = db.get(EmployeeDocument, doc_id)
    if not doc or doc.employee_id != emp.id:
        raise HTTPException(404, "Document not found")
    if doc.backend == storage.DB:
        blob = db.get(EmployeeDocumentBlob, doc.id)
        if blob:
            db.delete(blob)
    else:
        storage.remove(doc.backend, doc.storage_key)
    db.delete(doc)
    record_audit(db, actor=actor, action="DELETE", entity_type="employee_document",
                 entity_id=emp.id, field="filename", old=doc.filename, request=request)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------- file notes
def list_file_notes(db: Session, emp, scopes: set[str]) -> list[dict]:
    if not ({"manager.team", "admin"} & scopes):
        return []
    notes = (db.query(EmployeeFileNote)
             .filter(EmployeeFileNote.employee_id == emp.id, EmployeeFileNote.deleted_at.is_(None))
             .order_by(EmployeeFileNote.created_at.desc()).all())
    return [{"id": str(n.id), "note": n.note, "by": _name(db, n.created_by_id),
             "at": n.created_at.isoformat() if n.created_at else None} for n in notes]


def add_file_note(db: Session, emp, note: str, scopes: set[str], actor, request) -> dict:
    if not ({"manager.team", "admin"} & scopes):
        raise HTTPException(403, "Only a manager or admin can add file notes")
    if not (note or "").strip():
        raise HTTPException(400, "Note is empty")
    n = EmployeeFileNote(employee_id=emp.id, note=note.strip(), created_by_id=getattr(actor, "id", None))
    db.add(n)
    record_audit(db, actor=actor, action="CREATE", entity_type="employee_file_note",
                 entity_id=emp.id, field="note", new=note[:80], request=request)
    db.commit()
    return {"id": str(n.id)}
