"""Hardware-specific discovery and qualification; no performance claims."""

import platform
import re

from .cuda import inspect_devices as inspect_cuda
from .mlx import inspect_devices as inspect_mlx


def tool_facts(probe: dict) -> dict:
    return {
        "status": "tool_available" if probe["returncode"] == 0 else "unavailable",
        "probe": probe,
        "selection_verified": False,
        "note": "Raw tool output is not a model/backend compatibility certification",
    }


def _framed_cells(line: str) -> list[str] | None:
    """Split one row of a pipe-framed table into stripped cells."""
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def _npu_smi_records(stdout: str) -> list[dict]:
    """Read one record per NPU row of the framed `npu-smi info` table.

    Each NPU row is "<id> <name>" (for example "0 910B3"). Its chip row repeats
    the NPU ID followed by the chip index, and process rows carry a PID, so only
    the two-token row with an alphabetic name identifies a device.
    """
    records = []
    for line in stdout.splitlines():
        cells = _framed_cells(line)
        if cells is None:
            continue
        head = cells[0].split()
        if len(head) == 2 and head[0].isdigit() and re.search(r"[A-Za-z]", head[1]):
            records.append({"id": head[0], "name": head[1]})
    return records


def _rocminfo_records(stdout: str) -> list[dict]:
    """Read one record per `Agent N` block that names a GPU."""
    blocks: list[dict] = []
    current: dict | None = None
    for line in stdout.splitlines():
        if line.startswith("Agent"):
            current = {}
            blocks.append(current)
        elif current is not None and ":" in line:
            key, _, value = line.partition(":")
            current[key.strip()] = value.strip()
    # Host CPU agents carry a Uuid and a marketing name too, so only an explicit
    # "Device Type: GPU" block names an accelerator.
    return [
        {"id": block["Uuid"], "name": block["Marketing Name"]}
        for block in blocks
        if block.get("Device Type", "").casefold() == "gpu"
        and block.get("Uuid")
        and block.get("Marketing Name")
    ]


def _normalized_model(value: str) -> str:
    return re.sub(r"[\s_-]+", "", value.casefold()).removeprefix("ascend")


def parsed_tool_facts(
    probe: dict, *, device_ids, device_model, tokens, records
) -> dict:
    """Qualify a selection against parsed device records, never loose tokens."""
    device = tool_facts(probe)
    if probe["returncode"] != 0:
        return device
    devices = records(probe["stdout"])
    device["devices"] = devices
    if not devices:
        device["reason"] = f"No device records parsed from {tokens} output"
        return device
    reported = {item["id"] for item in devices}
    missing = [item for item in device_ids if item not in reported]
    if missing:
        device["reason"] = f"Requested device IDs absent from {tokens} output: {', '.join(missing)}"
        return device
    selected = [item for item in devices if not device_ids or item["id"] in device_ids]
    requested_model = _normalized_model(device_model or "")
    if device_model and not requested_model:
        device["status"] = "device_model_mismatch"
        device["reason"] = "Requested device model has no comparable token"
    elif requested_model and any(
        requested_model not in _normalized_model(item["name"]) for item in selected
    ):
        device["status"] = "device_model_mismatch"
        device["reason"] = (
            f"Requested device model absent from the selected {tokens} records: {device_model}"
        )
    else:
        device["status"] = "available"
        device["selection_verified"] = True
    return device


def inspect_cpu(**kwargs):
    return {
        "status": "available",
        "tool": "platform",
        "details": platform.processor(),
        "note": "CPU contract/smoke testing only; no accelerator validation",
    }


def inspect_rocm(*, command, device_ids=(), device_model=None, **kwargs):
    return parsed_tool_facts(
        command(["rocminfo"]),
        device_ids=device_ids,
        device_model=device_model,
        tokens="rocminfo",
        records=_rocminfo_records,
    )


def inspect_ascend(*, command, device_ids=(), device_model=None, **kwargs):
    return parsed_tool_facts(
        command(["npu-smi", "info"]),
        device_ids=device_ids,
        device_model=device_model,
        tokens="npu-smi",
        records=_npu_smi_records,
    )


# Extend platform discovery here; scheduling, process ownership and verdicts
# do not branch on backend names. Discovery does not certify compatibility.
PLATFORM_PROBES = {
    "cpu": inspect_cpu,
    "cuda": inspect_cuda,
    "rocm": inspect_rocm,
    "ascend": inspect_ascend,
    "mlx": inspect_mlx,
}


def inspect_device(backend, *, device_ids, device_model, command):
    if backend not in PLATFORM_PROBES:
        raise ValueError(f"Unknown backend: {backend}")
    return PLATFORM_PROBES[backend](
        device_ids=device_ids,
        device_model=device_model,
        command=command,
    )
