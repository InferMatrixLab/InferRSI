# Neutral raw repository-pack data leaf (D020). It holds only the original
# REPO_TYPES tuple and pack.json reader, and imports no inferrsi module.
# K02 moved pack.json to the Harness resource root (D007). The anchor stays the
# root package and joins the physical path, so reading a Harness-owned resource
# never imports inferrsi.harness and never gives infra an edge into Harness.
from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

REPO_TYPES = ("vllm", "vllm_omni", "afd_plugin", "vllm_rlt", "strata", "sglang", "sglang_omni")


def repository_pack(repo_type: str) -> dict[str, Any]:
    if repo_type not in REPO_TYPES:
        raise ValueError(f"Unknown repository type: {repo_type}")
    path = files("inferrsi").joinpath("harness", "data", "repo_packs", repo_type, "pack.json")
    return json.loads(path.read_text(encoding="utf-8"))
