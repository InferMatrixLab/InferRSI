# Neutral target-repository descriptors (D007, D020). Anchor the read at the
# root package so resolving a descriptor never imports a business module.
from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

REPO_TYPES = (
    "vllm", "vllm_omni", "vllm_musa", "afd_plugin", "vllm_rlt", "strata", "sglang", "sglang_omni"
)


def repository_pack(repo_type: str) -> dict[str, Any]:
    if repo_type not in REPO_TYPES:
        raise ValueError(f"Unknown repository type: {repo_type}")
    path = files("inferrsi").joinpath("resources", "repo_packs", f"{repo_type}.json")
    return json.loads(path.read_text(encoding="utf-8"))
