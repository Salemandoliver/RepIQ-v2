"""Field-group permission projection — "one record, many views" (brief §3.2 / §4.2).

An entity's fields are organised into named **field groups**, each with a set of **read** and
**write** scope tokens. Given the scopes the current caller holds *for this target record*
(resolved by ``core.rbac``), the projector returns only the groups the caller may read, and
gates writes the same way.

Brief rule: a caller who lacks a group's scope must not see the field at all — it is omitted
from the payload (and a dedicated sub-resource endpoint for that group returns 403), never
returned as a redacted/empty value.

This module is pure (no FastAPI/DB imports) so it is trivially testable. Routers translate a
denied write into an HTTP 403.

Scope tokens are abstract strings, e.g. ``"self"``, ``"manager.team"``, ``"admin"``,
``"admin.financial"``. ``core.rbac.scopes_for(viewer, target)`` produces the caller's set.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FieldGroup:
    name: str
    fields: tuple[str, ...]
    read: frozenset[str]
    write: frozenset[str] = frozenset()


def group(name: str, fields, read, write=()) -> FieldGroup:
    return FieldGroup(name, tuple(fields), frozenset(read), frozenset(write))


class Projection:
    """A set of field groups for one entity type."""

    def __init__(self, groups: list[FieldGroup]):
        self.groups: dict[str, FieldGroup] = {g.name: g for g in groups}

    # -- capability checks --------------------------------------------------
    def can_read(self, group_name: str, scopes: set[str]) -> bool:
        g = self.groups.get(group_name)
        return bool(g and (g.read & scopes))

    def can_write(self, group_name: str, scopes: set[str]) -> bool:
        g = self.groups.get(group_name)
        return bool(g and (g.write & scopes))

    def readable_group_names(self, scopes: set[str]) -> list[str]:
        return [name for name, g in self.groups.items() if g.read & scopes]

    def field_group(self, field: str) -> str | None:
        for g in self.groups.values():
            if field in g.fields:
                return g.name
        return None

    # -- projection ---------------------------------------------------------
    def project(self, data_by_group: dict[str, dict], scopes: set[str]) -> dict:
        """Return only the groups the caller may read. ``data_by_group`` maps group name ->
        {field: value}. Groups the caller cannot read are omitted entirely."""
        return {name: (data_by_group.get(name) or {})
                for name, g in self.groups.items() if g.read & scopes}

    def project_flat(self, data: dict, scopes: set[str]) -> dict:
        """Project a single flat dict of {field: value} down to only the fields whose group
        the caller may read."""
        allowed: set[str] = set()
        for g in self.groups.values():
            if g.read & scopes:
                allowed.update(g.fields)
        return {k: v for k, v in data.items() if k in allowed}

    def filter_writes(self, changes: dict, scopes: set[str]) -> tuple[dict, list[str]]:
        """Split an incoming {field: value} change set into (allowed, denied_field_names)
        based on the caller's write scopes. Routers reject if denied is non-empty (or apply
        only the allowed subset, depending on the endpoint's contract)."""
        allowed, denied = {}, []
        for field, value in changes.items():
            gname = self.field_group(field)
            if gname and self.can_write(gname, scopes):
                allowed[field] = value
            else:
                denied.append(field)
        return allowed, denied
