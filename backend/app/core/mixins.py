"""Reusable SQLAlchemy mixins for every new domain entity (HR, Orders).

- UUID primary keys (no enumeration, safe in URLs/exports)
- created_at / updated_at timestamps
- soft delete (records are immutable; "delete" = archive/anonymise)
- a JSONB ``metadata`` extension column (add attributes without a migration, graduate to a
  real column when they stabilise — brief §3.1)

Note: SQLAlchemy reserves the attribute name ``metadata`` on declarative classes, so the
extension column is exposed in Python as ``.extra`` while living in the DB column ``metadata``.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# JSONB on Postgres, plain JSON on SQLite (dev/test).
JSON_B = JSON().with_variant(JSONB, "postgresql")


class UUIDPkMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class MetadataMixin:
    # DB column is "metadata"; Python attribute is "extra" (metadata is reserved).
    extra: Mapped[dict] = mapped_column("metadata", JSON_B, default=dict)


class DomainBase(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, MetadataMixin):
    """Convenience base — UUID pk + timestamps + soft delete + metadata. New HR/Order models
    inherit (DomainBase, Base)."""
    __abstract__ = True
