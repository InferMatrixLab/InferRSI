"""Generic official evaluator entry, available only inside the readonly sandbox."""

import contextlib
import importlib
import json
import os
import resource
import sys
import time
from pathlib import Path

# -I deliberately excludes script paths; only the explicitly readonly helper root is added.
sys.path.insert(0, "/opt/executor")
import contract
import data_binding
import synthetic_probe as boundary


def main():
    try:
        boundary.authorize_start()
    except (ValueError, OSError):
        os.write(2, b"PAYLOAD_START_REJECTED\n")
        return 23
    descriptor = os.open("/dev/null", os.O_RDONLY)
    os.dup2(descriptor, 0)
    if descriptor != 0:
        os.close(descriptor)
    os.write(2, b"PAYLOAD_START_AUTHORIZED\n")
    policy = contract.policy("/opt/executor/policy.json", sys.argv[1])
    if sys.flags.optimize:
        raise ValueError("EvalPlus correctness assertions must remain enabled")
    for name, value in (("NPROC", policy["tasks"]), ("MEMLOCK", 0), ("MSGQUEUE", 0)):
        resource.setrlimit(getattr(resource, "RLIMIT_" + name), (value, value))
    boundary.install_ipc_filter()
    raw_inputs, export, samples = contract.inputs(
        "/input", sys.argv[2], sys.argv[3], policy["input_bytes"]
    )
    data_binding.validate(raw_inputs, export, samples)
    work = Path("/work")
    cache, output = work / "cache", work / "output/results.json"
    if cache.exists() or output.exists():
        raise ValueError("evaluator output/cache reuse forbidden")
    # All module-captured environment settings precede the first EvalPlus import.
    os.environ["XDG_CACHE_HOME"] = str(cache)
    os.environ["HUMANEVAL_OVERRIDE_PATH"] = "/input/humaneval-subset.jsonl"
    os.environ.pop("EVALPLUS_MAX_MEMORY_BYTES", None)
    os.environ.pop("EVALPLUS_TIMEOUT_PER_TASK", None)
    sys.path.insert(0, "/opt/site-packages")
    observations = {
        "scope": "full164-canonical-resource-pilot",
        "limits": {
            name: list(resource.getrlimit(getattr(resource, "RLIMIT_" + name)))
            for name in ("AS", "CPU", "FSIZE", "NPROC", "NOFILE")
        },
        "work_capacity_bytes": os.statvfs(work).f_frsize * os.statvfs(work).f_blocks,
    }
    started = time.monotonic()
    with contextlib.redirect_stdout(sys.stderr):
        evaluator = importlib.import_module("evalplus.evaluate")
        original_groundtruth = evaluator.get_groundtruth

        def measured_groundtruth(*args, **kwargs):
            started_gt = time.monotonic()
            try:
                return original_groundtruth(*args, **kwargs)
            finally:
                observations["groundtruth_seconds"] = time.monotonic() - started_gt

        evaluator.get_groundtruth = measured_groundtruth
        evaluator.evaluate(
            dataset="humaneval",
            samples="/input/humaneval-solutions.jsonl",
            output_file=str(output),
            parallel=1,
            base_only=False,
            mini=False,
            noextreme=False,
            test_details=True,
        )
    raw = contract.read(output, policy["result_bytes"])
    contract.results(raw, export, samples, policy["result_bytes"])
    observations.update(
        evaluator_seconds=time.monotonic() - started,
        result_bytes=len(raw),
        cache_file_bytes=sum(
            path.stat().st_size for path in cache.rglob("*") if path.is_file()
        ),
        work_file_bytes=sum(
            path.stat().st_size for path in work.rglob("*") if path.is_file()
        ),
        work_allocated_bytes=(os.statvfs(work).f_blocks - os.statvfs(work).f_bfree)
        * os.statvfs(work).f_frsize,
        coordinator_maxrss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        groundtruth_wrapper_preserves_arguments_return_and_exceptions=True,
    )
    os.write(
        2,
        b"FULL164_OBSERVATIONS "
        + json.dumps(observations, sort_keys=True).encode()
        + b"\n",
    )
    # Preserve exactly the upstream bytes once, including its original formatting.
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
