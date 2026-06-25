"""Review Reflections module — a guided two-way coaching dialogue on each weekly (Oliver) or
monthly/quarterly (Gary) performance review. The transcript and the structured signal mined from it
feed every intelligence surface (insights, Smart Alerts, 1-to-1 briefs, Ask RepIQ, the Oracle).
Plan: docs/Review-Reflections-Plan.md.

Phase 1 = engine + data (models, dialogue engine, extraction, reflection_signal backbone). Routers,
nav and the voice/text UI come in later phases.
"""
from ...core.registry import ModuleSpec, register
from . import models  # noqa: F401  register tables on Base.metadata for create_all
from .router import router as reflections_router

module = register(ModuleSpec(name="reflections", routers=[reflections_router]))
