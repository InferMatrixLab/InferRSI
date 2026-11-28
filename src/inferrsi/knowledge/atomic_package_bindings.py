"""Bind shared package originals to verified, ordered L3 material."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .atomic_composition import AtomPin, AtomUse
from .atomic_generation import InstalledGeneration
from .atomic_reader import atom_material
from .knowledge_operations import safe_path


@dataclass(frozen=True)
class PackageOriginal:
    """One entry from the independently frozen legacy package resource list."""

    alias: str
    source_path: str
    size: int
    sha256: str

    def __post_init__(self) -> None:
        safe_path(self.alias)
        safe_path(self.source_path)
        if self.alias == "record.json":
            raise ValueError("record.json belongs to the individual package caller")
        if type(self.size) is not int or self.size < 0:
            raise ValueError(f"invalid original byte length for {self.alias}")
        if not isinstance(self.sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
            raise ValueError(f"invalid original SHA-256 for {self.alias}")


def bind_shared_package_originals(
    generation: InstalledGeneration,
    originals: Iterable[PackageOriginal],
    pins: Mapping[str, AtomPin],
) -> tuple[AtomUse, ...]:
    """Verify all declared roots before returning uses in legacy resource order.

    The supplied sequence fixes the exact aliases, source paths, and bytes.
    Each alias must have a distinct sealed L3 pin. A caller composition must
    still provide its own identity, revision, and permission checks.
    """
    ordered = tuple(originals)
    aliases = {original.alias for original in ordered}
    if not aliases or len(aliases) != len(ordered):
        raise ValueError("shared package originals must have unique aliases")
    if aliases != pins.keys():
        raise ValueError("shared package pins must match the original aliases")
    if len(set(pins.values())) != len(ordered):
        raise ValueError("shared package aliases must use distinct atom pins")

    uses = []
    for original in ordered:
        pin = pins[original.alias]
        if not generation.source_range_verified(pin):
            raise ValueError(f"unverified shared package pin for {original.alias}")
        _, bundle = generation.read_resolved(pin.ref, revision=pin.revision)
        _, proof = atom_material(bundle, bundle.view())
        if (
            proof["layer"] != "L3"
            or proof["source_path"] != original.source_path
            or proof["source_byte_range"] != [0, original.size]
            or proof["bytes"] != original.size
            or proof["sha256"] != original.sha256
        ):
            raise ValueError(f"shared package pin does not match the original for {original.alias}")
        uses.append(AtomUse(pin, (original.alias,)))

    return tuple(uses)
