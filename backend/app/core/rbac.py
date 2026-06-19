"""RBAC — the platform role + scope model (brief §4).

Two layers:

* **platform_role** — one of ``employee | manager | operations | admin``. The authoritative
  role for HR, Orders, and admin features. ``admin`` is the super-role. All managers are equal
  and always team-scoped. Operations is distinct (engine room) — *not* a manager.

* **scopes** — fine-grained capability grants layered on top, so we never explode roles:
  ``financial`` (admin account only), ``ops.orders``, ``ops.schedule5``, ``ops.commission``,
  ``calliq.dispute`` (Operations may access call recordings for disputes — never coaching).

The ``platform_role`` and ``scopes`` are columns on ``User`` added by the Phase-0 migration.
Until that migration runs, this module derives them with safe fallbacks (admins keep working;
nobody is over-granted), so importing/using it now is harmless and changes no live behaviour.

This module also produces **projection scope tokens** for ``core.projection`` — the relationship
of a viewer to a target record (``self`` / ``manager.team`` / ``admin`` / ``admin.financial``).
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status

from ..auth import get_current_user
from ..models import User

# ----------------------------------------------------------------- roles / scopes
EMPLOYEE, MANAGER, OPERATIONS, ADMIN = "employee", "manager", "operations", "admin"
PLATFORM_ROLES = (EMPLOYEE, MANAGER, OPERATIONS, ADMIN)

FINANCIAL = "financial"
OPS_ORDERS, OPS_SCHEDULE5, OPS_COMMISSION = "ops.orders", "ops.schedule5", "ops.commission"
CALLIQ_DISPUTE = "calliq.dispute"

# Scopes implied purely by holding a role (financial is NEVER implied — it is an explicit
# grant on the single admin account, per brief §4.3).
_ROLE_IMPLIED_SCOPES: dict[str, set[str]] = {
    OPERATIONS: {OPS_ORDERS, OPS_SCHEDULE5, OPS_COMMISSION, CALLIQ_DISPUTE},
    MANAGER: set(),
    ADMIN: set(),
    EMPLOYEE: set(),
}


def platform_role(user: User) -> str:
    """The user's platform role. Uses the explicit column once the Phase-0 migration adds it;
    otherwise falls back conservatively (admins -> admin, everyone else -> employee; managers
    and operations are set explicitly by the migration)."""
    pr = getattr(user, "platform_role", None)
    if pr in PLATFORM_ROLES:
        return pr
    if getattr(user, "role", None) == "admin":
        return ADMIN
    return EMPLOYEE


def granted_scopes(user: User) -> set[str]:
    """All capability scopes the user holds: explicit grants + role-implied."""
    explicit = set(getattr(user, "scopes", None) or [])
    return explicit | _ROLE_IMPLIED_SCOPES.get(platform_role(user), set())


def has_role(user: User, *roles: str) -> bool:
    pr = platform_role(user)
    return pr == ADMIN or pr in roles


def has_scope(user: User, scope: str) -> bool:
    return scope in granted_scopes(user)


# ----------------------------------------------------------------- FastAPI dependencies
def require_role(*roles: str):
    """Dependency: caller must hold one of ``roles`` (admin always passes)."""
    def dep(user: User = Depends(get_current_user)) -> User:
        if has_role(user, *roles):
            return user
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
    return dep


def require_scope(scope: str):
    """Dependency: caller must hold ``scope``. Financial endpoints use require_scope('financial')
    so a JWT without it gets a hard 403 (brief §4.3)."""
    def dep(user: User = Depends(get_current_user)) -> User:
        if has_scope(user, scope):
            return user
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient scope")
    return dep


require_admin = require_role(ADMIN)
require_manager = require_role(MANAGER)            # admin passes too
require_operations = require_role(OPERATIONS)


# ----------------------------------------------------------------- projection tokens
def projection_scopes(viewer: User, *, is_self: bool, manages_target_team: bool) -> set[str]:
    """The set of projection scope tokens a viewer holds *for a given target record*, consumed
    by ``core.projection`` to decide which field groups are visible/writable.

    Tokens: ``self`` (own record), ``manager.team`` (manager of the target's team),
    ``admin`` (admin role), ``admin.financial`` (admin holding the financial scope).
    """
    toks: set[str] = set()
    if is_self:
        toks.add("self")
    role = platform_role(viewer)
    if role == ADMIN:
        toks.add("admin")
        if FINANCIAL in granted_scopes(viewer):
            toks.add("admin.financial")
    elif role == MANAGER and manages_target_team:
        toks.add("manager.team")
    return toks
