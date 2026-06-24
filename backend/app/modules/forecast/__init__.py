"""Weekly Forecast module — each Sales Rep commits a weekly forecast (Data/Cloud/Mobile SOV) on
Monday, tracked daily against placed orders, with a rolling Forecast Reliability Score that feeds
every performance surface. Plan: docs/Weekly-Forecast-Plan.md.

Phase 1 = data foundation (models + services + achievement/reliability maths). Routers and nav are
added in later phases.
"""
from ...core.registry import ModuleSpec, register
from . import models  # noqa: F401  register tables on Base.metadata for create_all
from .router import router as forecast_router

module = register(ModuleSpec(name="forecast", routers=[forecast_router]))
