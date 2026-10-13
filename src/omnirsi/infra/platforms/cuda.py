"""NVIDIA device reservation checks, parameterized by campaign hardware."""

import csv
import io
import os
import re
import subprocess


def inspect_devices(*, device_ids, device_model, command):
    from . import tool_facts

    device = tool_facts(
        command(
            ["nvidia-smi", "--query-gpu=index,uuid,name,driver_version", "--format=csv,noheader"]
        )
    )
    probe = device["probe"]
    if probe["returncode"] != 0:
        return device
    rows = []
    for row in csv.reader(io.StringIO(probe["stdout"])):
        fields = [value.strip() for value in row]
        if len(fields) == 4 and fields[0].isdigit():
            rows.append(dict(zip(("index", "uuid", "name", "driver_version"), fields)))
    device["topology"] = command(["nvidia-smi", "topo", "-m"])
    device["devices"] = rows
    selected = [
        row
        for row in rows
        if not device_ids or row["index"] in device_ids or row["uuid"] in device_ids
    ]
    device["selection_verified"] = bool(selected) and len(selected) == (
        len(device_ids) if device_ids else len(rows)
    )
    if not device["selection_verified"]:
        device["status"] = "unavailable"
    elif device_model and any(
        device_model.casefold() not in row["name"].casefold() for row in selected
    ):
        device["status"] = "device_model_mismatch"
    else:
        device["status"] = "available"
    return device


def qualify_devices(*, count: int, device_model: str):
    if isinstance(count, bool) or not isinstance(count, int) or count < 1 or not device_model:
        raise ValueError("A positive device count and device model are required")
    ids = [
        item.strip()
        for item in os.environ.get("CUDA_VISIBLE_DEVICES", "").split(",")
        if item.strip()
    ]
    if len(ids) != count or len(set(ids)) != count:
        raise ValueError(
            f"Set CUDA_VISIBLE_DEVICES to exactly {count} caller-reserved {device_model} IDs/UUIDs"
        )
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=index,uuid,name,driver_version", "--format=csv,noheader"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    devices = [
        dict(zip(("index", "uuid", "name", "driver"), [v.strip() for v in row]))
        for row in csv.reader(io.StringIO(result.stdout))
        if len(row) == 4
    ]
    selected = [gpu for gpu in devices if gpu["index"] in ids or gpu["uuid"] in ids]
    if len(selected) != count or any(
        not re.search(r"\b" + re.escape(device_model) + r"\b", gpu["name"]) for gpu in selected
    ):
        raise ValueError(
            f"The {count} requested physical devices must all be {device_model}; "
            "inspect nvidia-smi mapping"
        )
    active = subprocess.run(
        ["nvidia-smi", "--query-compute-apps=gpu_uuid,pid,process_name", "--format=csv,noheader"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    selected_uuids = {gpu["uuid"] for gpu in selected}
    if any(
        row and row[0].strip() in selected_uuids for row in csv.reader(io.StringIO(active.stdout))
    ):
        raise ValueError(
            "An allocated GPU already has a compute process; do not overlap campaign trials"
        )
    return selected
