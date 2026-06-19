"""baseline — the pre-v2 schema (managed by create_all + _ensure_columns)

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-19

This is an intentional **no-op baseline**. The existing RepIQ schema (users, calls, teams,
settings, performance_videos, …) is created and maintained at runtime by the app's
``Base.metadata.create_all`` + ``_ensure_columns`` during the transition to Alembic.

Adoption / cutover procedure (run once, deliberately — NOT auto-flipped on deploy):
  1. Deploy the app with Alembic present (this baseline + env.py).
  2. Bring the live database onto Alembic without running any DDL:
         cd backend && alembic stamp 0001_baseline
     (writes the alembic_version marker; executes nothing.)
  3. From then on, author every NEW schema change (HR, Orders, audit_log, the platform_role
     columns, …) as a migration chained after this baseline and apply with `alembic upgrade head`.
  4. Once Alembic is the sole migration path, retire `_ensure_columns` (and, for new tables,
     create_all) in a controlled change.
"""
from typing import Sequence, Union

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # No-op: pre-v2 schema is managed by the app during the Alembic transition.
    pass


def downgrade() -> None:
    pass
