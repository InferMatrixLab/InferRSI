"""Read a required group of pinned atoms from one authorized Knowledge source view."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Protocol

from .atomic_composition import LAYERS, AtomPin, AtomUse, applies, select_routes
from .atomic_generation import InstalledGeneration
from .decision_cards import DecisionSource
from .knowledge_operations import (
    Bundle,
    IdentityError,
    UnavailableRevision,
    safe_path,
)

_DIGEST = re.compile(r"[0-9a-f]{64}")
_OPERATIONS = frozenset({"read", "retain", "redistribute"})


class PinnedSource(Protocol):
    def read_resolved(self, reference: str, *, revision: str) -> tuple[str, Bundle]: ...


@dataclass(frozen=True)
class GroupDelivery:
    """Bodies and their corresponding public receipt records in delivery order."""

    bodies: tuple[bytes, ...]
    receipt: dict


def _refused(reason: str, *, required_bytes: int | None = None) -> GroupDelivery:
    receipt = {"status": reason, "body_bytes": 0, "delivered": []}
    if required_bytes is not None:
        receipt["required_bytes"] = required_bytes
    return GroupDelivery((), receipt)


def _selected(delivery: GroupDelivery, request: dict) -> GroupDelivery:
    return GroupDelivery(delivery.bodies, {**delivery.receipt, "selection": request})


def _actions(max_bytes: int, operations: Iterable[str]) -> set[str]:
    if type(max_bytes) is not int or max_bytes < 0:
        raise ValueError("Body budget must be a nonnegative integer")
    actions = {"read", *operations}
    if not actions <= _OPERATIONS:
        raise ValueError("Unknown atom operation")
    return actions


def permits_operations(declaration: dict, actions: set[str]) -> bool:
    """Check each declared grant and the explicit license required for redistribution."""
    if not all(declaration["permissions"].get(action) is True for action in actions):
        return False
    license_id = declaration.get("license")
    if "redistribute" in actions and (not isinstance(license_id, str) or
            license_id.strip().lower() in {"", "unknown", "none", "noassertion", "no_license"}):
        return False
    return True


def _restriction(declaration: dict, actions: set[str], context: Mapping[str, str]) -> str | None:
    if not permits_operations(declaration, actions):
        return "permission_denied"
    if not applies(declaration["when"], context):
        return "not_applicable"
    return None


def atom_material(bundle: Bundle, view: dict) -> tuple[bytes, dict]:
    """Recover and verify the authored byte span, including a binary attachment."""
    atom = view["atom"]
    resource = safe_path(atom.get("resource", view["entrypoint"]))
    if resource not in bundle.content:
        raise ValueError("Atom resource is missing from the pinned Bundle")
    body = bundle.content[resource]
    span = atom["source_span"]
    index = span["source_index"]
    if type(index) is not int or not 0 <= index < len(view["sources"]):
        raise ValueError("Atom source_span must select a declared source")
    source = view["sources"][index]
    commit = source.get("commit")
    snapshot = source.get("sha256")
    if "commit" in source:
        if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("Invalid immutable source commit")
    elif not isinstance(snapshot, str) or not _DIGEST.fullmatch(snapshot):
        raise ValueError("An atom needs an immutable source snapshot")
    start, end = span["byte_range"]
    if type(start) is not int or type(end) is not int or start < 0 or end - start != len(body):
        raise ValueError("Source range must cover the exact bytes of the atom")
    digest = hashlib.sha256(body).hexdigest()
    if span["sha256"] != digest or view["resources"][resource] != digest:
        raise ValueError("Atom does not match the declared source digest")
    if atom["layer"] not in LAYERS:
        raise ValueError("Invalid atom disclosure layer")
    return body, {
        "resource": resource,
        "layer": atom["layer"], "source": dict(source), "source_path": safe_path(span["path"]),
        "source_byte_range": [start, end], "source_sha256": span["sha256"],
        "sha256": digest, "bytes": len(body),
    }


class AtomicReader:
    """The caller supplies a snapshot reader and grants for the current project."""

    def __init__(self, source: PinnedSource, *, permits: Callable[[AtomPin, str], bool]):
        self.source = source
        self.permits = permits

    def _snapshot(self, pin: AtomPin) -> tuple[Bundle, dict] | None:
        try:
            qualified, held = self.source.read_resolved(pin.ref, revision=pin.revision)
        except UnavailableRevision:
            return None
        except IdentityError as exc:
            if exc.code != "unknown_identity":
                raise
            return None
        if qualified != pin.ref or held.metadata.get("id") != pin.ref.partition(":")[2]:
            return None
        bundle = Bundle(held.metadata, dict(held.content), dict(held.dependencies))
        view = bundle.view()
        return (bundle, view) if view["revision"] == pin.revision else None

    def _materialize(self, required, optional, *, max_bytes, context, actions,
                     layer=None) -> GroupDelivery:
        cached: dict[AtomPin, tuple[bytes, dict]] = {}
        paths: dict[AtomPin, list[list[str]]] = {}
        omissions = []
        used_bytes = 0

        def include(group: Iterable[AtomUse]) -> GroupDelivery | None:
            nonlocal used_bytes
            proposed: dict[AtomPin, list[list[str]]] = {}
            for use in group:
                via = list(use.path)
                if via not in proposed.setdefault(use.pin, []):
                    proposed[use.pin].append(via)
            if not proposed:
                return _refused("not_applicable")
            if any(not self.permits(pin, op) for pin in proposed for op in actions):
                return _refused("permission_denied")
            for pin in proposed:
                if pin in cached:
                    continue
                snapshot = self._snapshot(pin)
                if snapshot is None:
                    return _refused("unavailable_revision")
                bundle, view = snapshot
                atom = view.get("atom")
                if not isinstance(atom, dict):
                    raise ValueError("A composition node must reference an atom")
                reason = _restriction(atom, actions, context)
                if reason:
                    return _refused(reason)
                cached[pin] = atom_material(bundle, view)
            total = used_bytes + sum(len(cached[pin][0]) for pin in proposed if pin not in paths)
            if total > max_bytes:
                return _refused("over_budget", required_bytes=total)
            for pin, vias in proposed.items():
                seen = paths.setdefault(pin, [])
                seen.extend(via for via in vias if via not in seen)
            used_bytes = total
            return None

        refusal = include(required)
        if refusal is not None:
            return refusal
        if layer is not None:
            routes = {via[0] for vias in paths.values() for via in vias}
            supplied = {via[0] for pin, vias in paths.items() if cached[pin][1]["layer"] == layer
                        for via in vias if len(via) == 2}
            if routes != supplied:
                raise ValueError(f"Selected route has no required root supplying {layer}")
        for group in optional:
            refusal = include(group)
            if refusal is not None:
                omissions.append({"path": list(group[-1].path),
                                  "reason": refusal.receipt["status"]})
        pinned = isinstance(self.source, InstalledGeneration) and self.source.release_pinned
        records = [{"ref": pin.ref, "revision": pin.revision, "paths": via,
                    "source_range_verification": "verified_at_build" if pinned else "declared",
                    **cached[pin][1]}
                   for pin, via in paths.items()]
        receipt = {"status": "delivered", "body_bytes": used_bytes, "delivered": records}
        if omissions:
            receipt["omissions"] = omissions
        return GroupDelivery(tuple(cached[pin][0] for pin in paths), receipt)

    def read_group(
        self, uses: Iterable[AtomUse], *, max_bytes: int, context: Mapping[str, str],
        operations: Iterable[str] = (),
    ) -> GroupDelivery:
        """Resolve and authorize every required path before releasing any body."""
        return self._materialize(uses, (), max_bytes=max_bytes, context=context,
                                 actions=_actions(max_bytes, operations))

    def read_selection(
        self, reference: str, *, revision: str, layer: str, max_bytes: int,
        context: Mapping[str, str], finding: str | None = None, operations: Iterable[str] = (),
    ) -> GroupDelivery:
        """Read one pinned composition by layer and, for a Case, one original finding."""
        pin = AtomPin(reference, revision)
        actions = _actions(max_bytes, operations)
        if layer not in LAYERS:
            raise ValueError("Select one of L0, L1, L2 and L3")
        requested = {"ref": reference, "revision": revision, "layer": layer, "finding": finding}
        if not all(self.permits(pin, action) for action in actions):
            return _selected(_refused("permission_denied"), requested)
        snapshot = self._snapshot(pin)
        if snapshot is None:
            return _selected(_refused("unavailable_revision"), requested)
        bundle, view = snapshot
        composition = view.get("composition")
        if not isinstance(composition, dict):
            raise ValueError("Expected a pinned composition")
        reason = _restriction(composition, actions, context)
        if reason:
            return _selected(_refused(reason), requested)
        case = None
        if view["kind"] == "case":
            case = DecisionSource.from_bundle(reference, bundle, view)
        plan = select_routes(composition, layer=layer, context=context, case=case, finding=finding)
        if plan.refusal:
            return _selected(_refused(plan.refusal), requested)
        delivery = self._materialize(plan.required, plan.optional, max_bytes=max_bytes,
                                     context=context, actions=actions, layer=layer)
        return _selected(delivery, {**requested, "canonical_finding": plan.finding,
                                    "routes": list(plan.routes)})
