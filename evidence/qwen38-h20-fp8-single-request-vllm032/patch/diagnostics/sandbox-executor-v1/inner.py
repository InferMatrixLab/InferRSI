"""Generic official evaluator entry, available only inside the readonly sandbox."""

import contextlib
import importlib
import os
import resource
import sys
from pathlib import Path

# -I deliberately excludes script paths; only the explicitly readonly helper root is added.
sys.path.insert(0, "/opt/executor")
import contract
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
    _, export, samples = contract.inputs("/input", sys.argv[2], sys.argv[3], policy["input_bytes"])
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
    with contextlib.redirect_stdout(sys.stderr):
        evaluator = importlib.import_module("evalplus.evaluate")
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
    # Preserve exactly the upstream bytes once, including its original formatting.
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
