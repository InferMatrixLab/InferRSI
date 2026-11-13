# Compatibility shell. The implementation lives in inferrsi.knowledge.knowledge_operations;
# patch implementation globals such as _json and _hash on that module.
from __future__ import annotations

from inferrsi.knowledge.knowledge_operations import (
    AUTHORITIES,
    IDENTITY,
    INCIDENTAL,
    Bundle,
    IdentityError,
    KnowledgeReader,
    RevisionConflict,
    _hash,
    _json,
    _normalized,
    _sources,
    _tree,
    safe_path,
)

__all__ = [
    "AUTHORITIES",
    "IDENTITY",
    "RevisionConflict",
    "IdentityError",
    "safe_path",
    "Bundle",
    "KnowledgeReader",
    "INCIDENTAL",
    "_json",
    "_hash",
    "_normalized",
    "_sources",
    "_tree",
]
