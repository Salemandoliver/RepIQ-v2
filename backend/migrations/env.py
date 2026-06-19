"""Alembic environment for RepIQ.

Targets the app's SQLAlchemy metadata and uses the app's configured database URL, so the same
models drive both runtime (`create_all`, for now) and migrations (going forward). Imports the
models + core.audit so `--autogenerate` sees every table.

Run from the backend/ directory:
    cd backend && alembic upgrade head        # apply migrations
    cd backend && alembic revision --autogenerate -m "hr schema"
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make the app package importable (backend/ on sys.path).
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.db import Base               # noqa: E402
from app import models               # noqa: E402,F401  (registers core models)
from app.core import audit           # noqa: E402,F401  (registers AuditLog)
from app.config import settings      # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Inject the real DB URL from app settings (never hard-coded in alembic.ini).
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
