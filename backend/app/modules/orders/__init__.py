"""Order Entry module (brief §14) — orders, line items, status machine, sales-team splits, disputes,
ERP Dump import, commission engine, and Schedule 5 reconciliation. Replaces NetSuite + the Excel
trackers (kept in parallel until reconciled)."""
from ...core.registry import ModuleSpec, register
from . import models  # noqa: F401  register tables on Base.metadata for create_all
from .router import router as orders_router
from .extra_router import router as orders_extra_router
from .commission import router as commission_router
from .schedule5 import router as schedule5_router

module = register(ModuleSpec(
    name="orders",
    routers=[orders_router, orders_extra_router, commission_router, schedule5_router],
))
