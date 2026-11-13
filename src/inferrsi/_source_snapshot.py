# Compatibility shell. The implementation lives in inferrsi.knowledge._source_snapshot.
from __future__ import annotations

from inferrsi.knowledge._source_snapshot import (
    LIBRARY,
    MANIFEST,
    REGISTRY,
    REPOSITORY,
    STORED_SCHEMA,
    _snapshot,
    compact,
    manifest,
    resolve,
)

__all__ = [
    "MANIFEST",
    "REPOSITORY",
    "LIBRARY",
    "REGISTRY",
    "STORED_SCHEMA",
    "manifest",
    "compact",
    "resolve",
    "_snapshot",
]
