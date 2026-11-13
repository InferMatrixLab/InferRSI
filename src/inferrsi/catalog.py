# Compatibility shell. Knowledge names live in inferrsi.knowledge.catalog;
# REPO_TYPES and repository_pack live in the neutral inferrsi._repo_pack_data.
from __future__ import annotations

from inferrsi._repo_pack_data import REPO_TYPES, repository_pack
from inferrsi.knowledge.catalog import (
    BACKENDS,
    KNOWLEDGE_REPOS,
    KNOWLEDGE_SCOPES,
    SCENARIO_ALIASES,
    _validate_record,
    _walk,
    files,
    get_knowledge,
    knowledge_records,
    search_knowledge,
)

__all__ = [
    "REPO_TYPES",
    "KNOWLEDGE_SCOPES",
    "KNOWLEDGE_REPOS",
    "BACKENDS",
    "SCENARIO_ALIASES",
    "knowledge_records",
    "search_knowledge",
    "get_knowledge",
    "repository_pack",
    "_walk",
    "_validate_record",
    "files",
]
