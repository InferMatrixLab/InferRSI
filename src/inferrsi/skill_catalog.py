# Compatibility shell. The implementation lives in inferrsi.knowledge.skill_catalog;
# importing it still requires the optional PyYAML 'skills' extra.
from __future__ import annotations

from inferrsi.knowledge.skill_catalog import (
    _applicability,
    _directory,
    _effective,
    _entry,
    _frontmatter,
    _indexed_directories,
    _metadata,
    _references,
    _sidecar,
    _skill_name,
    _strings,
    _unique_fields,
    get_skill,
    skill_directories,
    skill_directory,
    skill_instructions,
    skill_metadata,
    skill_records,
    skill_reference,
    skill_resource,
)

__all__ = [
    "skill_directories",
    "skill_directory",
    "skill_metadata",
    "skill_records",
    "get_skill",
    "skill_instructions",
    "skill_resource",
    "skill_reference",
    "_frontmatter",
    "_skill_name",
    "_directory",
    "_unique_fields",
    "_indexed_directories",
    "_entry",
    "_sidecar",
    "_references",
    "_strings",
    "_applicability",
    "_effective",
    "_metadata",
]
