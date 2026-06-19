"""HR module — employee records (SafeHR replacement). Phase 1: identity + personal (incl.
preferred name / photo) + contact + emergency contacts, with field-level projection and audit."""
from ...core.registry import ModuleSpec, NavItem, register
from . import models  # noqa: F401  (register tables on Base.metadata for create_all)
from .router import router

module = register(ModuleSpec(
    name="hr",
    routers=[router],
    nav=[NavItem(label="People", path="/people", roles=("manager", "admin"), icon="users", order=80)],
))
