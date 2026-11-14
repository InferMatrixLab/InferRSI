# Compatibility shell. The implementation lives in inferrsi.knowledge._source_snapshot.
from __future__ import annotations

from inferrsi.knowledge._source_snapshot import (
    BUNDLE_LIBRARY,
    LIBRARY,
    MANIFEST,
    REGISTRY,
    REPOSITORY,
    STORED_SCHEMA,
    _snapshot,
    compact,
    manifest,
    resolve,
    source_entry,
)

__all__ = [
    "MANIFEST",
    "REPOSITORY",
    "LIBRARY",
    "BUNDLE_LIBRARY",
    "REGISTRY",
    "STORED_SCHEMA",
    "manifest",
    "compact",
    "resolve",
    "source_entry",
    "_snapshot",
]
