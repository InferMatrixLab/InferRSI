# Compatibility shell. The implementation lives in inferrsi.knowledge._skill_selection.
from __future__ import annotations

from inferrsi.knowledge._skill_selection import (
    RELEVANCE_METHODS,
    TASK_RELEVANCE,
    SkillIndexError,
    context_view,
    indexed_skill,
    lexical_score,
    raw_string_lexical_score,
    record_context,
    skill_score,
    task_score,
    words,
)

__all__ = [
    "RELEVANCE_METHODS",
    "SkillIndexError",
    "words",
    "lexical_score",
    "raw_string_lexical_score",
    "indexed_skill",
    "skill_score",
    "context_view",
    "TASK_RELEVANCE",
    "task_score",
    "record_context",
]
