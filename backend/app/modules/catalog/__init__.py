"""Product catalogue module — the company's products/pillars that campaigns + intelligence link to."""
from ...core.registry import ModuleSpec, register
from . import models  # noqa: F401  (register tables on Base.metadata for create_all)
from .router import router

module = register(ModuleSpec(name="catalog", routers=[router]))
