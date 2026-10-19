"""Source/cache separation and dependency metadata for prepared environments."""

import json
import os
import subprocess
import sys
from pathlib import Path


def storage_locations(args, output_root, require_source=True):
    source = Path(args.source_repo).resolve()
    cache = Path(args.cache_root).resolve()
    output_root = Path(output_root).resolve()
    if require_source and not source.is_dir():
        raise ValueError("source-repo must be an existing checkout")
    if cache.is_relative_to(source) or output_root.is_relative_to(source):
        raise ValueError("Cache and campaign output must be outside the source checkout")
    for key in ("HF_HOME", "HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE", "TRANSFORMERS_CACHE"):
        if os.environ.get(key) and Path(os.environ[key]).resolve().is_relative_to(source):
            raise ValueError(f"{key} must be outside the source checkout")
    return source, cache, output_root


def dependency_versions():
    packages = (
        "torch",
        "vllm",
        "vllm-omni",
        "diffusers",
        "transformers",
        "triton",
        "nvidia-cuda-runtime-cu12",
        "nvidia-cuda-runtime-cu13",
        "nvidia-cudnn-cu12",
        "nvidia-cudnn-cu13",
        "nvidia-nccl-cu12",
        "nvidia-nccl-cu13",
        "flashinfer-python",
    )
    code = (
        "import importlib.metadata as metadata,json,sys\n"
        "versions={}\n"
        "for name in sys.argv[1:]:\n"
        " try: versions[name]=metadata.version(name)\n"
        " except metadata.PackageNotFoundError: versions[name]='not_installed'\n"
        "print(json.dumps(versions))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, *packages],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return json.loads(result.stdout)


def semantic_dependency_versions(versions):
    # Source revisions cover vLLM-Omni code; editable package version text can differ.
    return {name: version for name, version in versions.items() if name != "vllm-omni"}
