"""Resolve the authored branches and dependency paths of one pinned composition."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from .decision_cards import DecisionSource, UnknownFinding
from .knowledge_operations import AUTHORITIES, IDENTITY

LAYERS = ("L0", "L1", "L2", "L3")


@dataclass(frozen=True)
class AtomPin:
    ref: str
    revision: str

    def __post_init__(self) -> None:
        if not isinstance(self.ref, str) or not isinstance(self.revision, str):
            raise ValueError("Atom reference and revision must be strings")
        authority, _, identity = self.ref.partition(":")
        if authority not in AUTHORITIES or not re.fullmatch(IDENTITY, identity):
            raise ValueError("A pinned atom needs an authority-qualified reference")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", self.revision):
            raise ValueError("A pinned atom needs a complete Bundle revision")


@dataclass(frozen=True)
class AtomUse:
    """One path through a composition to the requested atom."""

    pin: AtomPin
    path: tuple[str, ...]

    def __post_init__(self) -> None:
        if (not isinstance(self.path, tuple) or not self.path
                or not all(isinstance(step, str) and step for step in self.path)):
            raise ValueError("A dependency path must name each step")


def _release_number(value: object) -> tuple[int, ...] | None:
    if not isinstance(value, str) or not re.fullmatch(r"v?[0-9]+(?:\.[0-9]+)*", value):
        return None
    parts = [int(part) for part in value.removeprefix("v").split(".")]
    while parts and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def _matches(condition: object, actual: str | None) -> bool:
    if isinstance(condition, list):
        if not condition or not all(isinstance(value, str) and value for value in condition):
            raise ValueError("An exact-match condition requires nonempty strings")
        return actual in condition
    if not isinstance(condition, Mapping) or not condition or condition.keys() - {"min", "before"}:
        raise ValueError("Expected an allowlist or a release range with min and/or before")
    lower = _release_number(condition.get("min"))
    upper = _release_number(condition.get("before"))
    if ("min" in condition and lower is None) or ("before" in condition and upper is None):
        raise ValueError("Release bounds must be dotted numeric release strings")
    if lower is not None and upper is not None and lower >= upper:
        raise ValueError("Release range must contain at least one release")
    release = _release_number(actual)
    return (release is not None and (lower is None or lower <= release)
            and (upper is None or release < upper))


def applies(when: Mapping[str, object], context: Mapping[str, str]) -> bool:
    """Match every dimension: exact allowlists or [min, before) dotted release ranges."""
    if not isinstance(when, Mapping):
        raise ValueError("Conditions must map named dimensions to constraints")
    matches = True
    for key, condition in when.items():
        if not isinstance(key, str) or not key:
            raise ValueError("Conditions must name a dimension")
        # Validate later declarations even if an earlier dimension did not match.
        if not _matches(condition, context.get(key)):
            matches = False
    return matches


@dataclass(frozen=True)
class RouteSelection:
    required: tuple[AtomUse, ...] = ()
    optional: tuple[tuple[AtomUse, ...], ...] = ()
    routes: tuple[str, ...] = ()
    finding: str | None = None
    refusal: str | None = None


def _names(values: object, targets: Mapping, field: str) -> tuple[str, ...]:
    if not isinstance(values, list) or not all(isinstance(name, str) and name in targets
                                               for name in values):
        raise ValueError(f"{field} must list names declared in the composition")
    if len(set(values)) != len(values):
        raise ValueError(f"Duplicate name in {field}")
    return tuple(values)


def _acyclic(edges: dict[str, tuple[str, ...]], relation: str) -> None:
    visited = set()
    active = set()

    def visit(name):
        if name in active:
            raise ValueError(f"Cycle in composition {relation} at {name}")
        if name not in visited:
            active.add(name)
            for other in edges[name]:
                visit(other)
            active.remove(name)
            visited.add(name)

    for name in edges:
        visit(name)


def select_routes(composition: dict, *, layer: str, context: Mapping[str, str],
                  case: DecisionSource | None, finding: str | None) -> RouteSelection:
    """Select one disclosure layer and expand applicable routes in authored dependency order."""
    if layer not in LAYERS:
        raise ValueError("Select one of L0, L1, L2 and L3")
    selected_finding = None
    if finding is not None:
        if not isinstance(finding, str) or case is None:
            return RouteSelection(refusal="not_applicable")
        try:
            selected_finding = case.finding_locator(case.finding(finding)[0])
        except UnknownFinding:
            return RouteSelection(refusal="not_applicable")
    elif case is not None and layer == "L1":
        return RouteSelection(refusal="not_applicable")

    nodes, routes = composition["nodes"], composition["routes"]
    if not all(isinstance(group, dict) and group and all(
            isinstance(key, str) and key and isinstance(value, dict) for key, value in group.items()
    ) for group in (nodes, routes)):
        raise ValueError("A composition must declare named nodes and routes")
    pins = {name: AtomPin(node["ref"], node["revision"]) for name, node in nodes.items()}
    requires = {name: _names(node.get("requires", []), nodes, "requires")
                for name, node in nodes.items()}
    _acyclic(requires, "requires")
    supersedes = {}
    conflicts = {}
    required = {}
    optional = {}
    matches = set()
    for name, route in routes.items():
        if route["layer"] not in LAYERS:
            raise ValueError(f"Invalid disclosure layer for route {name}")
        required[name] = _names(route["required"], nodes, "required")
        optional[name] = _names(route.get("optional", []), nodes, "optional")
        if not required[name] or set(required[name]).intersection(optional[name]):
            raise ValueError(f"Route {name} needs distinct required and optional roots")
        supersedes[name] = _names(route.get("supersedes", []), routes, "supersedes")
        conflicts[name] = _names(route.get("conflicts", []), routes, "conflicts")
        if name in conflicts[name]:
            raise ValueError(f"Route {name} conflicts with itself")
        selector = route.get("finding")
        if selector is not None:
            if case is None or not isinstance(selector, str):
                raise ValueError("Only a Case route may declare a finding selector")
            selector = case.finding_locator(case.finding(selector)[0])
        applicable = applies(route.get("when", {}), context)
        if applicable and layer == route["layer"] and selector == selected_finding:
            matches.add(name)
    _acyclic(supersedes, "supersedes")
    # A newer declaration can retire another only inside their common applicable scope.
    chosen = matches.difference(other for name in matches for other in supersedes[name])
    if not chosen:
        return RouteSelection(finding=selected_finding, refusal="not_applicable")
    if any(chosen.intersection(conflicts[name]) for name in chosen):
        return RouteSelection(finding=selected_finding, refusal="conflict")

    def expand(node, path):
        via = (*path, node)
        for child in requires[node]:
            yield from expand(child, via)
        yield AtomUse(pins[node], via)

    ordered = tuple(sorted(chosen))
    return RouteSelection(
        tuple(use for name in ordered for node in required[name] for use in expand(node, (name,))),
        tuple(tuple(expand(node, (name,))) for name in ordered for node in optional[name]),
        ordered, selected_finding,
    )
