"""Compute-node wheel tags and the previously skipped bounded filesystem probe."""

import argparse
import hashlib
import importlib.metadata
import importlib.util
import os
import platform
import signal
import sys
import sysconfig
import time
from pathlib import Path

import packaging
import packaging.tags

# Isolated Python deliberately omits the script directory from sys.path.
_spec = importlib.util.spec_from_file_location(
    "reviewed_fs_probe", Path(__file__).with_name("probe.py")
)
_probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_probe)


def platform_tags():
    package = Path(packaging.__file__).parent
    sources = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(package.glob("*.py"))
    }
    tags = [str(tag) for tag in packaging.tags.sys_tags()]
    if (
        sys.version_info[:2] != (3, 12)
        or platform.system() != "Linux"
        or platform.machine() != "x86_64"
    ):
        raise ValueError("Unexpected target interpreter/platform")
    if not tags or len(tags) != len(set(tags)):
        raise ValueError("Empty or duplicate wheel tag set")
    return {
        "completed": True,
        "python": platform.python_version(),
        "implementation": sys.implementation.name,
        "system": platform.system(),
        "machine": platform.machine(),
        "libc": platform.libc_ver(),
        "soabi": sysconfig.get_config_var("SOABI"),
        "packaging_version": importlib.metadata.version("packaging"),
        "packaging_sources": sources,
        "supported_tags": tags,
    }


def diagnose(output, result):
    deadline = time.monotonic() + 120
    try:
        for name, operation in (
            ("platform", lambda state: state.update(platform_tags())),
            ("filesystem", lambda state: _probe.filesystem_probe(output, state)),
        ):
            state = result[name] = {"completed": False}
            remaining = deadline - time.monotonic()
            if remaining <= 1:
                state["skipped_reason"] = "overall_deadline_exhausted"
            else:
                signal.alarm(max(1, int(remaining)))
                try:
                    operation(state)
                except (OSError, ValueError) as error:
                    state["completed"] = False
                    state["error_type"] = type(error).__name__
            _probe.persist(output, result)
        result["completed"] = all(
            result[name].get("completed") is True for name in ("platform", "filesystem")
        )
        _probe.persist(output, result)
        return 0 if result["completed"] else 1
    finally:
        signal.alarm(0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if (
        not os.environ.get("SLURM_JOB_ID")
        or os.environ.get("SLURM_GPUS_ON_NODE", "0") != "0"
    ):
        raise ValueError("CPU-only Slurm allocation required")
    root = Path(os.environ["TASK_ROOT"]).resolve(strict=True)
    output = args.output.resolve(strict=False)
    if output == root or not output.is_relative_to(root):
        raise ValueError("Output escapes task root")
    output.mkdir(mode=0o700, exist_ok=False)
    result = {
        "scope": "compute_platform_and_filesystem_readiness",
        "verdict": "INCONCLUSIVE",
        "completed": False,
        "job_id": os.environ["SLURM_JOB_ID"],
        "network_requested": False,
        "package_changes": False,
        "evaluator_executed": False,
        "gpu_used": False,
    }
    signal.signal(signal.SIGALRM, _probe.fail_timeout)
    return diagnose(output, result)


if __name__ == "__main__":
    raise SystemExit(main())
