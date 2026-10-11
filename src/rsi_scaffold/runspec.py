"""Minimal RunSpec snapshot (repo × revision × backend × device × model × scenario)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class RunSpec:
    repo: str
    revision: str
    backend: str
    device: str
    model: str
    scenario: str
    executor: str = "default"
    snapshot_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunSpec:
        return cls(
            repo=str(data["repo"]),
            revision=str(data["revision"]),
            backend=str(data["backend"]),
            device=str(data["device"]),
            model=str(data["model"]),
            scenario=str(data["scenario"]),
            executor=str(data.get("executor", "default")),
            snapshot_id=str(data.get("snapshot_id", "")),
        )
