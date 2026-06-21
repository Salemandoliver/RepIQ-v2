"""Order Entry access control (brief §6.2, §14).

Operations are the engine room — full create/edit on all orders, status, CRQ, Schedule 5, disputes —
but NOT sales reps and NOT managers over HR. Admin can additionally delete, set commission rates and
run/lock commission. Managers + reps get read-only views (their team / their own orders). Financial
figures (commission £) are gated by the ``financial`` scope / admin, never shown to reps.
"""
from __future__ import annotations

from fastapi import HTTPException

from ...core import rbac
from ...models import User

ADMIN, OPERATIONS, MANAGER, REP = "admin", "operations", "manager", "rep"


def order_role(db, user: User) -> str:
    """admin | operations | manager | rep — the user's Order Entry capability tier."""
    pr = rbac.platform_role(user)
    if pr == rbac.ADMIN:
        return ADMIN
    if pr == rbac.OPERATIONS:
        return OPERATIONS
    try:
        from ...services.salesiq.roles import role_for_user
        if role_for_user(db, user) == "manager":
            return MANAGER
    except Exception:
        pass
    return REP


def can_write(role: str) -> bool:
    """Create / edit orders, lines, status, CRQ, disputes, Schedule 5."""
    return role in (ADMIN, OPERATIONS)


def can_delete(role: str) -> bool:
    return role == ADMIN


def can_configure_commission(role: str) -> bool:
    """Set/edit pay-plan rates, approve & lock commission runs."""
    return role == ADMIN


def can_run_commission(role: str) -> bool:
    """Run the calculation + generate statements (ops do this with management)."""
    return role in (ADMIN, OPERATIONS)


def can_see_financial(user: User) -> bool:
    """See commission £ figures — admin / financial scope only (brief §4.3)."""
    return rbac.platform_role(user) == rbac.ADMIN or rbac.has_scope(user, rbac.FINANCIAL)


def require_write(db, user: User):
    if not can_write(order_role(db, user)):
        raise HTTPException(403, "Order entry is for Operations and admin only")


def require_admin(db, user: User):
    if order_role(db, user) != ADMIN:
        raise HTTPException(403, "Admin only")
