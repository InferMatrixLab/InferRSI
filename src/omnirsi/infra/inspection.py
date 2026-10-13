"""Compose target identity, dependency metadata and platform facts."""

import json
import os
import platform
import sys
from collections.abc import Callable
from pathlib import Path

from ..catalog import repository_pack
from .commands import probe_command
from .platforms import inspect_device
from .targets import repository_identity


def inspect_environment(
    repo: str,
    repo_type: str,
    backend: str,
    *,
    device_ids: tuple[str, ...] = (),
    device_model: str | None = None,
    python: str | None = None,
    command: Callable[[list[str]], dict] = probe_command,
    snapshot: Callable[[Path], dict] = repository_identity,
) -> dict:
    repository = snapshot(Path(repo).resolve())
    python = python or sys.executable
    package_code = (
        "import json,sys,importlib.metadata as m; "
        "names=['torch','vllm','vllm-omni','vllm-afd-plugin','vllm-rlt','torch-npu',"
        "'nvidia-nccl-cu12','nvidia-nccl-cu13','nvidia-cuda-runtime-cu12',"
        "'nvidia-cuda-runtime-cu13']; "
        "installed={d.metadata['Name'].lower():d.version for d in m.distributions() "
        "if d.metadata['Name']}; "
        "print(json.dumps({'python':sys.version,'packages':{n:installed.get(n) for n in names}}))"
    )
    python_info = command([python, "-c", package_code])
    if python_info["returncode"] == 0:
        try:
            python_info["environment"] = json.loads(python_info["stdout"])
        except json.JSONDecodeError:
            python_info["parse_error"] = "Target Python did not emit a JSON environment"

    device = inspect_device(
        backend, device_ids=device_ids, device_model=device_model, command=command
    )

    return {
        "host": {"platform": platform.platform(), "hostname": platform.node()},
        "repository": repository,
        "repository_pack": repository_pack(repo_type),
        "backend": backend,
        "requested_device_ids": list(device_ids),
        "requested_device_model": device_model,
        "visible_devices": {
            key: os.environ.get(key)
            for key in (
                "CUDA_VISIBLE_DEVICES",
                "HIP_VISIBLE_DEVICES",
                "ROCR_VISIBLE_DEVICES",
                "ASCEND_RT_VISIBLE_DEVICES",
            )
        },
        "target_python": python_info,
        "device": device,
        "compatibility": "unverified",
    }
