"""Hardware-specific discovery and qualification; no performance claims."""

import platform

from .cuda import inspect_devices as inspect_cuda


def tool_facts(probe: dict) -> dict:
    return {
        "status": "tool_available" if probe["returncode"] == 0 else "unavailable",
        "probe": probe,
        "selection_verified": False,
        "note": "Raw tool output is not a model/backend compatibility certification",
    }


def inspect_cpu(**kwargs):
    return {
        "status": "available",
        "tool": "platform",
        "details": platform.processor(),
        "note": "CPU contract/smoke testing only; no accelerator validation",
    }


def inspect_rocm(*, command, **kwargs):
    return tool_facts(command(["rocminfo"]))


def inspect_ascend(*, command, **kwargs):
    return tool_facts(command(["npu-smi", "info"]))


# Extend platform discovery here; scheduling, process ownership and verdicts
# do not branch on backend names. Discovery does not certify compatibility.
PLATFORM_PROBES = {
    "cpu": inspect_cpu,
    "cuda": inspect_cuda,
    "rocm": inspect_rocm,
    "ascend": inspect_ascend,
}


def inspect_device(backend, *, device_ids, device_model, command):
    if backend not in PLATFORM_PROBES:
        raise ValueError(f"Unknown backend: {backend}")
    return PLATFORM_PROBES[backend](
        device_ids=device_ids,
        device_model=device_model,
        command=command,
    )
