"""Module registry — the backbone of the modular monolith.

Each feature module exposes a single ``ModuleSpec``. ``main.py`` builds the app from the
registry: include routers, run startup hooks, register alert rules, expose nav. Adding a
new module is then a new package + one ``register(...)`` call — no edits to main.py or to
any other module.

Usage
-----
    # modules/hr/__init__.py
    from ..core.registry import ModuleSpec, NavItem, register
    from .router import employees_router, leave_router

    register(ModuleSpec(
        name="hr",
        routers=[employees_router, leave_router],
        startup=[seed_hr_reference_data],
        alert_rules=[probation_due_rule],
        nav=[NavItem(label="People", path="/hr", roles=("manager", "admin"))],
    ))

    # main.py
    from .core import registry
    for r in registry.all_routers():
        app.include_router(r)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

from fastapi import APIRouter


@dataclass(frozen=True)
class NavItem:
    """A sidebar/nav entry a module wants shown, gated by platform role."""
    label: str
    path: str
    roles: tuple[str, ...] = ()        # empty = visible to all signed-in users
    icon: str | None = None
    order: int = 100


@dataclass
class ModuleSpec:
    name: str
    routers: list[APIRouter] = field(default_factory=list)
    # Called once at app startup, in registration order. Signature: () -> None.
    startup: list[Callable[[], None]] = field(default_factory=list)
    # Notification/alert rules run by the worker's housekeeping loop.
    # Signature: (db) -> None  (each rule queues its own notifications).
    alert_rules: list[Callable] = field(default_factory=list)
    nav: list[NavItem] = field(default_factory=list)


class _Registry:
    def __init__(self) -> None:
        self._modules: dict[str, ModuleSpec] = {}

    def register(self, spec: ModuleSpec) -> ModuleSpec:
        if spec.name in self._modules:
            raise ValueError(f"Module '{spec.name}' is already registered")
        self._modules[spec.name] = spec
        return spec

    def modules(self) -> list[ModuleSpec]:
        return list(self._modules.values())

    def all_routers(self) -> list[APIRouter]:
        out: list[APIRouter] = []
        for m in self._modules.values():
            out.extend(m.routers)
        return out

    def startup_hooks(self) -> Iterable[Callable[[], None]]:
        for m in self._modules.values():
            yield from m.startup

    def alert_rules(self) -> Iterable[Callable]:
        for m in self._modules.values():
            yield from m.alert_rules

    def nav(self, roles: set[str] | None = None) -> list[NavItem]:
        items: list[NavItem] = []
        for m in self._modules.values():
            for n in m.nav:
                if not n.roles or (roles and roles.intersection(n.roles)):
                    items.append(n)
        return sorted(items, key=lambda n: (n.order, n.label))


# Process-wide singleton.
_registry = _Registry()

register = _registry.register
modules = _registry.modules
all_routers = _registry.all_routers
startup_hooks = _registry.startup_hooks
alert_rules = _registry.alert_rules
nav = _registry.nav
