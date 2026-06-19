# Database migrations (Alembic)

RepIQ is moving to **Alembic** for schema changes (RepIQ v2). This directory holds the Alembic
environment and migration scripts.

## Status during the transition
- The **existing** schema is still created/maintained at runtime by `app/main.py`
  (`Base.metadata.create_all` + `_ensure_columns`). This stays in place until Alembic is
  cut over deliberately — so deploys remain safe.
- **All new v2 schema** (HR, Orders, `audit_log`, the platform RBAC columns, …) will be written
  as Alembic migrations chained after `0001_baseline`.

## One-time cutover (run together, not auto-on-deploy)
```bash
cd backend
alembic stamp 0001_baseline      # mark the live DB as at baseline (no DDL runs)
alembic upgrade head             # apply any migrations authored after baseline
```
After cutover, the container start command switches from `_ensure_columns` to
`alembic upgrade head`, and `_ensure_columns` is retired.

## Everyday use
```bash
cd backend
alembic revision --autogenerate -m "hr schema"   # author a migration from model changes
alembic upgrade head                              # apply
alembic downgrade -1                              # roll back one
alembic history                                   # list revisions
```

The DB URL comes from the app's settings (`DATABASE_URL`); it is **not** stored in `alembic.ini`.
`env.py` imports the app models + `core.audit` so autogenerate sees every table.
