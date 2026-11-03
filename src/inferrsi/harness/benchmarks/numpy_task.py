"""CPU task payload; never schedules processes or makes performance verdicts.

Only reviewed, trusted implementations may run here. Hash checks detect drift,
not malicious code. The public input suite is not a hidden evaluation set.
"""

import cProfile
import hashlib
import math
import platform
import pstats
import statistics
import time
from pathlib import Path


def inputs(case, np):
    rng = np.random.default_rng(case["seed"])
    x = rng.standard_normal(case["shape"]).astype(np.float32)
    if case["distribution"] == "zeros":
        x.fill(0)
    elif case["distribution"] == "large":
        x = x * np.float32(100) + np.float32(1000)
    elif case["distribution"] == "tiny":
        x *= np.float32(1e-7)
    if case["layout"] == "strided":
        storage = np.empty((*x.shape[:-1], x.shape[-1] * 2), dtype=np.float32)
        view = storage[..., ::2]
        view[...] = x
        x = view
    return x


def reference(x, oracle, np):
    """Scalar double-precision oracle, independent of NumPy reduction kernels."""
    rows = np.moveaxis(x, 1, -1)
    output = np.empty_like(rows)
    for index in np.ndindex(rows.shape[:-1]):
        values = [float(v) for v in rows[index]]
        if oracle["operation"] == "softmax":
            maximum = max(values)
            exps = [math.exp(v - maximum) for v in values]
            total = math.fsum(exps)
            result = [v / total for v in exps]
        else:
            scale = math.sqrt(math.fsum(v * v for v in values) / len(values) + oracle["eps"])
            result = [v / scale for v in values]
        output[index] = result
    return np.moveaxis(output, -1, 1)


def check_output(output, x, original, expected, oracle, np):
    return {
        "shape_dtype": isinstance(output, np.ndarray)
        and output.shape == x.shape
        and output.dtype == x.dtype,
        "finite": isinstance(output, np.ndarray) and bool(np.isfinite(output).all()),
        "input_preserved": x.tobytes() == original.tobytes(),
        "values": isinstance(output, np.ndarray)
        and output.shape == expected.shape
        and bool(
            np.allclose(output, expected, rtol=oracle["rtol"], atol=oracle["atol"], equal_nan=False)
        ),
    }


def evaluate(task, candidate: Path, action: str, result_dir: Path) -> dict:
    # Optional dependency is loaded only for execution, never task discovery.
    import numpy as np

    manifest = task.manifest
    source = candidate.read_bytes()
    namespace = {"__name__": "benchmark_candidate", "__file__": str(candidate)}
    exec(compile(source, "implementation.py", "exec"), namespace)
    compute = namespace.get("compute")
    if not callable(compute):
        raise ValueError("Candidate must define compute(x, *, eps)")
    oracle = manifest["oracle"]
    checks, cases, workload_records = {}, [], []
    prepared = []
    for case in manifest["workloads"]:
        x = inputs(case, np)
        original = x.copy()
        expected = reference(x, oracle, np)
        workload_records.append(
            {
                "id": case["id"],
                "input_sha256": hashlib.sha256(x.tobytes()).hexdigest(),
                "shape": list(x.shape),
                "dtype": str(x.dtype),
                "strides": list(x.strides),
            }
        )
        output = compute(x, eps=oracle["eps"])
        assertions = check_output(output, x, original, expected, oracle, np)
        checks.update({case["id"] + "." + k: v for k, v in assertions.items()})
        prepared.append((case, x, original, expected))
    result = {
        "status": "completed",
        "action": action,
        "passed": all(checks.values()),
        "assertions": checks,
        "environment": {
            "backend": "cpu",
            "python": platform.python_version(),
            "numpy": np.__version__,
            "os": platform.system(),
            "machine": platform.machine(),
        },
        "coverage": manifest["coverage"],
        "workloads": workload_records,
    }
    if not result["passed"] or action == "check":
        return result

    # Correctness and profiling do not masquerade as a paired measurement.
    profiler = cProfile.Profile() if action == "profile" else None
    measurement = manifest["measurement"]
    for case, x, original, expected in prepared:
        samples = []
        for index in range(measurement["warmups"] + measurement["samples"]):
            if profiler:
                profiler.enable()
            started = time.perf_counter_ns()
            output = compute(x, eps=oracle["eps"])
            elapsed = (time.perf_counter_ns() - started) / 1e6
            if profiler:
                profiler.disable()
            assertions = check_output(output, x, original, expected, oracle, np)
            if not all(assertions.values()):
                checks.update({f"{case['id']}.call-{index}.{k}": v for k, v in assertions.items()})
                result.update(
                    passed=False,
                    cases=cases,
                    failed_call={
                        "case": case["id"],
                        "call_index": index,
                        "phase": "warmup" if index < measurement["warmups"] else "measurement",
                        "elapsed_ms": elapsed,
                        "prior_samples_ms": samples,
                        "usable_measurement": False,
                    },
                )
                return result
            if index >= measurement["warmups"]:
                if not math.isfinite(elapsed) or elapsed <= 0:
                    raise ValueError("Timer did not resolve a positive duration")
                samples.append(elapsed)
        cases.append(
            {"id": case["id"], "samples_ms": samples, "median_ms": statistics.median(samples)}
        )
    if profiler:
        # Strip local installation paths from the textual profile before capture.
        with (result_dir / "profile.txt").open("w", encoding="utf-8") as stream:
            pstats.Stats(profiler, stream=stream).strip_dirs().sort_stats(
                "cumulative"
            ).print_stats()
        result["diagnostic"] = {
            "kind": "cpu-cprofile",
            "artifact": "profile.txt",
            "performance_verdict": None,
            "limitation": "Instrumented CPU calls; no accelerator timeline",
        }
    else:
        result["cases"] = cases
        result["measurement"] = measurement
        result["metrics"] = {"suite_latency_ms": sum(c["median_ms"] for c in cases)}
    return result
