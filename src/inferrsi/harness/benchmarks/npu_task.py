"""Trusted affine RMSNorm workload on an explicitly allocated Ascend NPU.

The independent CPU oracle and host/device transfers are outside timing. Timing
is synchronized eager-call latency, not pure kernel time. No CPU fallback and no
untrusted-code sandbox are provided by this Workbench adapter.
"""

import hashlib
import json
import math
import os
import platform
import statistics
import time
from pathlib import Path

from .numpy_task import input_record, inputs


def reference(x, weight, eps, np):
    """Scalar double arithmetic, independent of the device reduction/fused op."""
    expected = np.empty_like(x)
    for index, row in enumerate(x):
        values = [float(value) for value in row]
        scale = math.sqrt(math.fsum(value * value for value in values) / len(values) + eps)
        expected[index] = [value / scale * float(w) for value, w in zip(values, weight)]
    return expected


def environment(torch, torch_npu, np):
    from torch_npu.npu.utils import get_cann_version

    return {
        "backend": "ascend",
        "device": torch.npu.get_device_name(0),
        "logical_device": 0,
        "python": platform.python_version(),
        "torch": torch.__version__,
        "torch_npu": torch_npu.__version__,
        "numpy": np.__version__,
        "cann": str(get_cann_version()),
        "os": platform.system(),
        "machine": platform.machine(),
        "allocation": "caller-owned; one visible device",
    }


def check_output(output, x, weight, original, original_weight, expected, oracle, torch, np):
    tensor = isinstance(output, torch.Tensor)
    shape_dtype_device = (
        tensor and tuple(output.shape) == original.shape
        and output.dtype == torch.float32 and output.device == torch.device("npu:0")
    )
    def preserved(tensor, original):
        return (tuple(tensor.shape) == original.shape and tensor.dtype == torch.float32
                and tensor.device == torch.device("npu:0") and tensor.is_contiguous()
                and tensor.cpu().numpy().tobytes() == original.tobytes())

    # Reading results and checking preservation happens after device synchronization.
    values = output.detach().cpu().numpy() if shape_dtype_device else None
    return {
        "shape_dtype_device": shape_dtype_device,
        "finite": values is not None and bool(np.isfinite(values).all()),
        "input_preserved": preserved(x, original),
        "weight_preserved": preserved(weight, original_weight),
        "values": values is not None
        and bool(np.allclose(values, expected, rtol=oracle["rtol"], atol=oracle["atol"])),
    }


def device_kernels(document):
    """Read actual Ascend hardware records, not CPU launches/flow arrows."""
    events = document.get("traceEvents", []) if isinstance(document, dict) else document
    hardware = {event["pid"] for event in events
                if event.get("name") == "process_name"
                and event.get("args", {}).get("name") == "Ascend Hardware"}
    return [event for event in events
            if event.get("ph") == "X" and event.get("pid") in hardware
            and str(event.get("args", {}).get("Task Type", "")).startswith("KERNEL_")]


def evaluate(task, candidate: Path, action: str, result_dir: Path) -> dict:
    # The caller owns resource admission. This adapter does not reserve devices
    # or reinterpret the scheduler's selected physical device IDs.
    allocated = os.environ.get("ASCEND_RT_VISIBLE_DEVICES", "")
    if not allocated or len(allocated.split(",")) != 1:
        raise RuntimeError("One explicitly allocated visible NPU is required")
    import numpy as np
    import torch
    import torch_npu

    if not torch.npu.is_available() or torch.npu.device_count() != 1:
        raise RuntimeError("One NPU must be available; there is no CPU fallback")
    torch.npu.set_device(0)
    manifest = task.manifest
    oracle, measurement = manifest["oracle"], manifest["measurement"]
    namespace = {"__name__": "benchmark_candidate", "__file__": str(candidate)}
    exec(compile(candidate.read_bytes(), "implementation.py", "exec"), namespace)
    compute = namespace.get("compute")
    if not callable(compute):
        raise ValueError("Candidate must define compute(x, weight, *, eps)")

    prepared, records, seen = [], [], set()
    for case in manifest["workloads"]:
        count = 1
        if case["id"] in measurement["case_ids"]:
            count += measurement["warmups"] + measurement["samples"]
        for index in range(count):
            original = inputs(case, np, sequence=index)
            rng = np.random.default_rng(np.random.SeedSequence([case["seed"], index, 7]))
            original_weight = rng.uniform(-1.5, 1.5, case["shape"][-1]).astype(np.float32)
            expected = reference(original, original_weight, oracle["eps"], np)
            record = input_record(case, original)
            record["weight_sha256"] = hashlib.sha256(original_weight.tobytes()).hexdigest()
            record["call_index"] = index
            record["phase"] = (
                "precheck" if index == 0
                else "warmup" if index <= measurement["warmups"] else "measurement"
            )
            # x itself varies: a weight-only change cannot evade x-output replay checks.
            if record["input_sha256"] in seen:
                raise ValueError("Repeated input bytes in NPU sequence")
            seen.add(record["input_sha256"])
            x = torch.from_numpy(original.copy()).to("npu:0")
            weight = torch.from_numpy(original_weight.copy()).to("npu:0")
            prepared.append((case, x, weight, original, original_weight, expected, record))
            records.append(record)
    torch.npu.synchronize()
    checks, executed, samples = {}, [], {key: [] for key in measurement["case_ids"]}
    result = {
        "status": "completed", "action": action, "passed": False,
        "assertions": checks, "environment": environment(torch, torch_npu, np),
        "coverage": manifest["coverage"], "input_sequence": records, "executed_calls": executed,
    }

    def call(entry, *, timed=False):
        case, x, weight, original, original_weight, expected, record = entry
        torch.npu.synchronize()
        started = time.perf_counter_ns() if timed else None
        with torch.inference_mode():
            output = compute(x, weight, eps=oracle["eps"])
        torch.npu.synchronize()
        elapsed = (time.perf_counter_ns() - started) / 1e6 if timed else None
        assertions = check_output(
            output, x, weight, original, original_weight, expected, oracle, torch, np
        )
        checks.update({f"{case['id']}.call-{record['call_index']}.{k}": v
                       for k, v in assertions.items()})
        executed.append(record)
        if not all(assertions.values()):
            result["failed_call"] = {**record, "usable_measurement": False}
            return False
        if timed:
            if not math.isfinite(elapsed) or elapsed <= 0:
                raise ValueError("Timer did not resolve positive latency")
            samples[case["id"]].append({"elapsed_ms": elapsed, **record})
        return True

    # All correctness cases are checked before any timed input.
    for entry in prepared:
        if entry[-1]["phase"] == "precheck" and not call(entry):
            return result

    if action == "profile":
        # Warm all measured shapes before attaching the profiler. Profile one
        # fresh input per shape; ordinary measurement never enables instrumentation.
        for entry in prepared:
            if entry[-1]["phase"] == "warmup" and not call(entry):
                return result
        selected = [entry for entry in prepared if entry[-1]["phase"] == "measurement"
                    and entry[-1]["call_index"] == measurement["warmups"] + 1]
        with torch_npu.profiler.profile(
            activities=[torch_npu.profiler.ProfilerActivity.CPU,
                        torch_npu.profiler.ProfilerActivity.NPU],
            record_shapes=True, profile_memory=False, with_stack=False,
        ) as profiler:
            for entry in selected:
                with torch.profiler.record_function("rmsnorm-candidate-call"):
                    if not call(entry):
                        return result
        trace = result_dir / "npu-trace.json"
        profiler.export_chrome_trace(str(trace))
        # Raw profiler output may contain local identifiers: retain locally;
        # publication should use a reviewed, path-free kernel summary.
        document = json.loads(trace.read_text(encoding="utf-8"))
        kernels = device_kernels(document)
        if not kernels:
            raise RuntimeError("NPU profiler produced no device kernel events")
        result["diagnostic"] = {
            "kind": "ascend-torch-profiler", "artifact": "npu-trace.json",
            "sha256": hashlib.sha256(trace.read_bytes()).hexdigest(),
            "performance_verdict": None,
            "kernels": [{"name": event["name"], "duration_us": event.get("dur")}
                        for event in kernels],
            "limitation": "Instrumented diagnostic; includes verification copies; not a score",
        }
    else:
        for entry in prepared:
            if entry[-1]["phase"] == "precheck":
                continue
            if not call(entry, timed=action == "measure" and entry[-1]["phase"] == "measurement"):
                return result
        if action == "measure":
            cases = [{"id": key, "samples_ms": [v["elapsed_ms"] for v in values],
                      "sample_input_sha256": [v["input_sha256"] for v in values],
                      "median_ms": statistics.median(v["elapsed_ms"] for v in values)}
                     for key, values in samples.items()]
            result.update(cases=cases, measurement=measurement,
                          metrics={"suite_latency_ms": sum(case["median_ms"] for case in cases)})
    result["passed"] = all(checks.values())
    return result
