"""Shared data and byte contracts: canonical JSON, RunSpec and claim types.

``RunSpec`` is the only name this initializer re-exports. Import the canonical
encoder from ``contracts.json_v1`` and the verdict types from ``contracts.claim``.
No module here imports a core or Apps module, or does I/O on import.
"""

from .runspec import RunSpec

__all__ = ["RunSpec"]
