"""Moore Threads (MUSA) device reservation checks through the MTML bindings.

`pymtml` is the pynvml-compatible shim shipped by mthreads-ml-py, and it is the
same binding vLLM-MUSA itself uses for platform queries, so no vendor CLI has to
exist on the target host. The probe is a bounded, read-only subprocess: it
imports pymtml only, never torch, and never initializes a MUSA context.
"""

import json
import os
import subprocess
import sys
import textwrap

PROBE_CODE = textwrap.dedent(
    """
    import json
    try:
        import pymtml as pynvml
    except Exception as exc:
        print(json.dumps({"error": "pymtml unavailable: %s" % exc}))
        raise SystemExit(3)

    def text(value):
        return value.decode() if isinstance(value, bytes) else str(value)

    try:
        pynvml.nvmlInit()
    except Exception as exc:
        print(json.dumps({"error": "nvmlInit failed: %s" % exc}))
        raise SystemExit(4)
    try:
        try:
            driver_version = text(pynvml.nvmlSystemGetDriverVersion())
        except Exception:
            driver_version = None
        devices = []
        for index in range(pynvml.nvmlDeviceGetCount()):
            # One unreadable device must not hide the others: keep the identity
            # fields above the failure and report the device-local error.
            record = {"index": str(index)}
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(index)
            except Exception as exc:
                record["error"] = "%s: %s" % (type(exc).__name__, exc)
                devices.append(record)
                continue
            try:
                record["uuid"] = text(pynvml.nvmlDeviceGetUUID(handle))
                record["name"] = text(pynvml.nvmlDeviceGetName(handle))
            except Exception as exc:
                record["error"] = "%s: %s" % (type(exc).__name__, exc)
            if driver_version:
                record["driver_version"] = driver_version
            try:
                memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
                record["memory_total_mib"] = int(memory.total) >> 20
            except Exception:
                pass
            devices.append(record)
        print(json.dumps({"devices": devices}))
    finally:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass
    """
)

# MUSA has no nvidia-smi/npu-smi equivalent that is guaranteed to be installed,
# so process ownership is read through the same MTML bindings. A binding that
# cannot answer is *not* an idle device: the probe reports the failure and exits
# non-zero so qualification cannot mistake "unknown" for "free". A binding can
# also implement the query without implementing accounting and answer "no
# processes" on a card that is in use, so the reply carries the device's used
# memory as an independent signal and an empty list only counts as idle when the
# memory figure agrees.
IDLE_USED_MIB = 256

BUSY_CODE = textwrap.dedent(
    """
    import json
    import sys

    def fail(reason):
        print(json.dumps({"error": reason}))
        raise SystemExit(3)

    try:
        import pymtml as pynvml
    except Exception as exc:
        fail("pymtml unavailable: %s" % exc)
    try:
        pynvml.nvmlInit()
    except Exception as exc:
        fail("nvmlInit failed: %s" % exc)
    try:
        query = getattr(pynvml, "nvmlDeviceGetComputeRunningProcesses", None)
        if query is None:
            fail("nvmlDeviceGetComputeRunningProcesses is unavailable")
        memory_info = getattr(pynvml, "nvmlDeviceGetMemoryInfo", None)
        busy = []
        usage = []
        for index in sys.argv[1].split(","):
            handle = pynvml.nvmlDeviceGetHandleByIndex(int(index))
            # Only an explicit sequence is a process list. A binding that answers
            # None (or any other falsy non-list) has not established ownership,
            # so `or ()` would turn "unknown" into an affirmative "no processes".
            reply = query(handle)
            if not isinstance(reply, (list, tuple)):
                fail(
                    "nvmlDeviceGetComputeRunningProcesses returned %s for device %s"
                    % (type(reply).__name__, index)
                )
            for process in reply:
                busy.append({"device": index, "pid": int(process.pid)})
            used = None
            if memory_info is not None:
                try:
                    memory = memory_info(handle)
                    used = getattr(memory, "used", None)
                    if used is None:
                        used = int(memory.total) - int(memory.free)
                    used = int(used) >> 20
                except Exception:
                    used = None
            usage.append({"device": index, "used_mib": used})
        print(json.dumps({"processes": busy, "usage": usage}))
    except SystemExit:
        raise
    except Exception as exc:
        fail("process query failed: %s" % exc)
    finally:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass
    """
)


def _records(stdout: str) -> list[dict]:
    try:
        document = json.loads(stdout)
    except json.JSONDecodeError:
        return []
    devices = document.get("devices") if isinstance(document, dict) else None
    if not isinstance(devices, list):
        return []
    records = []
    for device in devices:
        # A device the probe could not identify keeps its error in the raw output
        # but cannot qualify a selection, so it is not a record here.
        if not isinstance(device, dict) or not device.get("index") or not device.get("name"):
            continue
        record = dict(device)
        # parsed_tool_facts qualifies a selection on the tool-neutral `id` field.
        record["id"] = device["index"]
        records.append(record)
    return records


def _visibility_ids() -> list[str]:
    """Read the mask the trial process inherits, in its positional order."""
    return [
        item.strip()
        for item in os.environ.get("MUSA_VISIBLE_DEVICES", "").split(",")
        if item.strip()
    ]


def inspect_devices(*, device_ids, device_model, command, python=None):
    from . import parsed_tool_facts

    device = parsed_tool_facts(
        command([python or sys.executable, "-c", PROBE_CODE]),
        device_ids=device_ids,
        device_model=device_model,
        tokens="pymtml",
        records=_records,
    )
    # parsed_tool_facts keeps a reached tool at "tool_available" even when the
    # selection or the device list is unusable; the run gate only admits
    # "available", so fail loudly instead of reporting a misleading status.
    if device["status"] == "tool_available" and device.get("reason"):
        device["status"] = "unavailable"
    # Discovery sees every physical card; the trial sees only the masked,
    # positional view. When those disagree the verified physical device is not
    # the device the run will use, so the selection stays unverified rather
    # than borrowing a signature from a different card.
    from . import logical_binding

    requested = [str(item) for item in (device_ids or ())]
    mask = os.environ.get("MUSA_VISIBLE_DEVICES")
    if device["selection_verified"] and requested and not logical_binding(requested, mask):
        device["selection_verified"] = False
        device["status"] = "unavailable"
        device["reason"] = (
            "MUSA_VISIBLE_DEVICES does not bind the declared devices to the run's "
            f"logical indices: declared {requested}, mask {mask or 'unset'}. Set "
            "MUSA_VISIBLE_DEVICES to the declared ids in order, so musa:0 is the "
            "first declared card"
        )
    return device


def qualify_devices(*, count: int, device_model: str, python=None):
    """Fail unless `count` caller-reserved MUSA devices are idle and all match.

    Mirrors :func:`inferrsi.apps.host.platforms.cuda.qualify_devices` for a prepared
    MUSA host: the selection comes from MUSA_VISIBLE_DEVICES, the expected model
    is matched against pymtml's device name, and an already-running compute
    process on a selected device aborts the campaign.

    Identity contract: ``MUSA_VISIBLE_DEVICES`` is positional -- the runtime maps
    its first entry to ``musa:0`` regardless of which physical card that entry
    names -- so qualification accepts only physical integer ids and returns each
    record with the ``logical_index`` the trial will use. Callers must keep both
    numbers in the evidence; without them a verdict cannot distinguish the card
    that was checked free from the card that produced the tokens. An unknown
    process state (import failure, init failure, no query API, unreadable reply)
    is a failure, never an idle device, and a UUID selection is rejected because
    its positional mapping cannot be reconciled with the verified physical card.

    A caller that needs a non-identity selection declares the physical ids in
    mask order -- logical index L is the L-th entry -- and must not pass a
    physical id that the mask does not place at that position. Discovery
    (``inspect_devices``) rejects such a mismatch outright.
    """
    if isinstance(count, bool) or not isinstance(count, int) or count < 1 or not device_model:
        raise ValueError("A positive device count and device model are required")
    ids = [
        item.strip()
        for item in os.environ.get("MUSA_VISIBLE_DEVICES", "").split(",")
        if item.strip()
    ]
    if len(ids) != count or len(set(ids)) != count:
        raise ValueError(
            f"Set MUSA_VISIBLE_DEVICES to exactly {count} caller-reserved {device_model} IDs"
        )
    # MUSA_VISIBLE_DEVICES is a positional namespace: the engine maps its first
    # entry to `musa:0`, not the physical card the entry names. Accepting a UUID
    # here would verify one card and let the trial run on another, so only
    # physical integer ids are supported and the mapping is reported back.
    if any(not item.isdigit() for item in ids):
        raise ValueError(
            "MUSA_VISIBLE_DEVICES must list physical integer device ids; UUID "
            "selections are not supported because the runtime maps the variable "
            "by position and would not run the verified physical card"
        )
    result = subprocess.run(
        [python or sys.executable, "-c", PROBE_CODE],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    devices = _records(result.stdout)
    selected = [device for device in devices if device["index"] in ids]
    if len(selected) != count or any(
        device_model.casefold() not in device["name"].casefold() for device in selected
    ):
        raise ValueError(
            f"The {count} requested physical devices must all be {device_model}; "
            "inspect the pymtml mapping"
        )
    # Query the resolved physical indices, never the caller's raw entries: a raw
    # entry can be a UUID that `int()` in the probe would reject before the
    # process query ever runs.
    busy = subprocess.run(
        [python or sys.executable, "-c", BUSY_CODE, ",".join(ids)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if busy.returncode != 0:
        reason = "unreadable reply"
        try:
            reason = json.loads(busy.stdout).get("error") or reason
        except (json.JSONDecodeError, AttributeError):
            pass
        raise ValueError(
            f"Cannot verify that the selected MUSA devices are idle: {reason}. "
            "Qualification refuses an unknown device state"
        )
    try:
        report = json.loads(busy.stdout or "")
    except json.JSONDecodeError as error:
        raise ValueError(
            "Cannot verify that the selected MUSA devices are idle: the process "
            "query returned unreadable output"
        ) from error
    if not isinstance(report, dict) or "processes" not in report:
        raise ValueError(
            "Cannot verify that the selected MUSA devices are idle: the process "
            "query did not report a process list"
        )
    if report["processes"]:
        raise ValueError(
            "An allocated MUSA device already has a compute process; "
            "do not overlap campaign trials"
        )
    # An empty process list is only evidence when an independent signal agrees:
    # a binding can answer "no processes" without implementing accounting.
    usage = report.get("usage")
    if not isinstance(usage, list) or len(usage) != len(ids):
        raise ValueError(
            "Cannot verify that the selected MUSA devices are idle: the process "
            "query reported no per-device memory usage"
        )
    for row in usage:
        used = row.get("used_mib") if isinstance(row, dict) else None
        if not isinstance(used, int) or isinstance(used, bool):
            raise ValueError(
                "Cannot verify that the selected MUSA devices are idle: the "
                "binding reports no used memory, so an empty process list proves "
                "nothing"
            )
        # A binding that derives used memory as total - free turns a free figure
        # larger than total into a negative integer. It passes an upper bound and
        # proves nothing, so only a plausible non-negative reading is evidence.
        if used < 0:
            raise ValueError(
                "Cannot verify that the selected MUSA devices are idle: the "
                f"binding reports {used} MiB used on device {row.get('device')}, "
                "which is not a valid reading"
            )
        if used > IDLE_USED_MIB:
            raise ValueError(
                f"MUSA device {row.get('device')} is using {used} MiB while the "
                "process query reported no processes; that binding's process "
                "accounting cannot be trusted"
            )
    # Report the physical->logical mapping the trial will use, so evidence ties
    # the measured device to the verified one.
    order = {value: position for position, value in enumerate(ids)}
    for device in selected:
        device["logical_index"] = order[device["index"]]
    return selected
