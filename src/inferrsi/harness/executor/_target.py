"""Trusted local CPU target configuration supplied by the host."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from inferrsi.contracts._harness_errors import PublicError
from inferrsi.harness.records import _run_store as run_store


@dataclass(frozen=True)
class LocalCpuTarget:
    """Trusted host configuration of the local CPU target; never read from a request.

    ``work_root`` holds per-attempt workspaces (``workspaces/<output_root>``) and private
    capture snapshots. ``controller_root`` / ``target_root`` authorize input sources of
    those namespaces; ``None`` leaves that namespace unauthorized. ``module_root``
    explicitly enables evaluation through standalone source entries under that trusted
    root. The retained source is executed directly in an isolated Python interpreter;
    package imports and ambient cwd/PYTHONPATH entry resolution are not used.
    """

    target_id: str
    config_revision: str
    work_root: Path
    controller_root: Path | None = None
    target_root: Path | None = None
    module_root: Path | None = None

    def __post_init__(self) -> None:
        errors = [
            f"{name}: not an Id"
            for name in ("target_id", "config_revision")
            if not run_store._is_id(getattr(self, name))
        ]
        for name in ("work_root", "controller_root", "target_root", "module_root"):
            value = getattr(self, name)
            if value is None:
                continue
            object.__setattr__(self, name, Path(value))
            if not Path(value).is_absolute():
                errors.append(f"{name}: must be an explicit absolute local path")
        if errors:
            raise PublicError(
                "InvalidRequest", stage="configure", message="illegal local CPU target",
                field_errors=errors,
            )
