"""Immutable audit log (brief §8).

Every write to a sensitive entity — and every *read* of financial data — produces an append-only
``audit_log`` row: who, what, when, which field, old/new value, role, IP, session. The table is
never updated or deleted through any application path (GDPR erasure anonymises *referenced* PII
elsewhere but preserves the audit chain).

Service-layer code calls ``record_audit(...)``. Models may also set ``__audited__ = True`` and be
wired to the optional ``before_flush`` listener (added when Phase 0 lands) for automatic field
diffing so a developer can't forget.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, Uuid
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..db import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    actor_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    action: Mapped[str] = mapped_column(String(16))            # CREATE | UPDATE | DELETE | READ
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    field: Mapped[str | None] = mapped_column(String(96), nullable=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


_REDACTED = "•••"
# Fields whose values are never written to the audit log in clear (only that they changed).
_SENSITIVE_FIELDS = {"bank_account", "sort_code", "iban", "ni_number", "password", "salary"}


def _val(field: str | None, value) -> str | None:
    if value is None:
        return None
    if field and field.lower() in _SENSITIVE_FIELDS:
        return _REDACTED
    s = str(value)
    return s if len(s) <= 4000 else s[:4000]


def record_audit(db: Session, *, actor=None, action: str, entity_type: str,
                 entity_id: str | None = None, field: str | None = None,
                 old=None, new=None, request=None, commit: bool = False) -> AuditLog:
    """Append one audit row. Safe to call within an existing transaction; pass commit=True to
    flush immediately (e.g. financial reads outside a write transaction)."""
    from .rbac import platform_role           # local import avoids any import cycle
    ip = session_id = None
    if request is not None:
        ip = getattr(getattr(request, "client", None), "host", None)
        session_id = request.headers.get("x-session-id") if hasattr(request, "headers") else None
    row = AuditLog(
        actor_user_id=getattr(actor, "id", None),
        actor_role=platform_role(actor) if actor is not None else None,
        action=action, entity_type=entity_type, entity_id=(str(entity_id) if entity_id else None),
        field=field, old_value=_val(field, old), new_value=_val(field, new),
        ip=ip, session_id=session_id,
    )
    db.add(row)
    if commit:
        db.commit()
    return row


def record_changes(db: Session, *, actor, action: str, entity_type: str, entity_id,
                   changes: dict, request=None) -> None:
    """Convenience: one audit row per changed field. ``changes`` maps field -> (old, new)."""
    for field, (old, new) in (changes or {}).items():
        record_audit(db, actor=actor, action=action, entity_type=entity_type,
                     entity_id=entity_id, field=field, old=old, new=new, request=request)
