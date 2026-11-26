"""Read a required group of pinned atoms from one authorized Knowledge source view."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Protocol

from .knowledge_operations import (
    AUTHORITIES,
    IDENTITY,
    Bundle,
    IdentityError,
    UnavailableRevision,
    safe_path,
)

_DIGEST = re.compile(r"[0-9a-f]{64}")
_OPERATIONS = frozenset({"read", "retain", "redistribute"})


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


def _provenance(view: dict, atom: dict, body: bytes) -> dict:
    span = atom["source_span"]
    index = span["source_index"]
    if type(index) is not int or not 0 <= index < len(view["sources"]):
        raise ValueError("Atom source_span must select a declared source")
    source = view["sources"][index]
    commit = source.get("commit")
    snapshot = source.get("sha256")
    if not (
        (isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit))
        or (isinstance(snapshot, str) and _DIGEST.fullmatch(snapshot))
    ):
        raise ValueError("An atom needs an immutable source snapshot")
    start, end = span["byte_range"]
    if type(start) is not int or type(end) is not int or start < 0 or end - start != len(body):
        raise ValueError("Source range must cover the exact bytes of the atom")
    digest = hashlib.sha256(body).hexdigest()
    if span["sha256"] != digest or view["resources"][view["entrypoint"]] != digest:
        raise ValueError("Atom does not match the declared source digest")
    if atom["layer"] not in ("L0", "L1", "L2", "L3"):
        raise ValueError("Invalid atom disclosure layer")
    return {
        "layer": atom["layer"], "source": dict(source), "source_path": safe_path(span["path"]),
        "source_byte_range": [start, end], "source_sha256": span["sha256"],
        "sha256": digest, "bytes": len(body),
    }


class AtomicReader:
    """The caller supplies a snapshot reader and grants for the current project."""

    def __init__(self, source: PinnedSource, *, permits: Callable[[AtomPin, str], bool]):
        self.source = source
        self.permits = permits

    def read_group(
        self, uses: Iterable[AtomUse], *, max_bytes: int, context: Mapping[str, str],
        operations: Iterable[str] = (),
    ) -> GroupDelivery:
        """Resolve and authorize every required path before releasing any body."""
        if type(max_bytes) is not int or max_bytes < 0:
            raise ValueError("Body budget must be a nonnegative integer")
        actions = {"read", *operations}
        if not actions <= _OPERATIONS:
            raise ValueError("Unknown atom operation")
        paths: dict[AtomPin, list[list[str]]] = {}
        for use in uses:
            via = list(use.path)
            seen = paths.setdefault(use.pin, [])
            if via not in seen:
                seen.append(via)
        if not paths:
            return _refused("not_applicable")
        if any(not self.permits(pin, action) for pin in paths for action in actions):
            return _refused("permission_denied")

        bodies, delivered = [], []
        for pin, via_paths in paths.items():
            try:
                qualified, held = self.source.read_resolved(pin.ref, revision=pin.revision)
            except UnavailableRevision:
                return _refused("unavailable_revision")
            except IdentityError as exc:
                if exc.code != "unknown_identity":
                    raise
                return _refused("unavailable_revision")
            if qualified != pin.ref or held.metadata.get("id") != pin.ref.partition(":")[2]:
                return _refused("unavailable_revision")
            # Bind the receipt and bytes to one snapshot of the mutable source mappings.
            bundle = Bundle(held.metadata, dict(held.content), dict(held.dependencies))
            view = bundle.view()
            if view["revision"] != pin.revision:
                return _refused("unavailable_revision")
            atom = view["atom"]
            if not all(atom["permissions"].get(action) is True for action in actions):
                return _refused("permission_denied")
            license_id = atom.get("license")
            if "redistribute" in actions and (
                not isinstance(license_id, str)
                or license_id.strip().lower() in {"", "unknown", "none", "noassertion"}
            ):
                return _refused("permission_denied")
            if not applies(atom["when"], context):
                return _refused("not_applicable")
            body = bundle.content[view["entrypoint"]]
            record = _provenance(view, atom, body)
            bodies.append(body)
            delivered.append({"ref": pin.ref, "revision": pin.revision,
                              "paths": via_paths, **record})

        total = sum(map(len, bodies))
        if total > max_bytes:
            return _refused("over_budget", required_bytes=total)
        return GroupDelivery(tuple(bodies), {"status": "delivered", "body_bytes": total,
                                             "delivered": delivered})
