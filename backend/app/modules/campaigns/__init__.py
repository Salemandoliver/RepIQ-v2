"""Campaigns module — BT Promotions + Sales Incentives, detected in calls and surfaced in SalesIQ."""
from ...core.registry import ModuleSpec, register
from . import models  # noqa: F401  (register tables on Base.metadata for create_all)
from .router import router

module = register(ModuleSpec(name="campaigns", routers=[router]))
