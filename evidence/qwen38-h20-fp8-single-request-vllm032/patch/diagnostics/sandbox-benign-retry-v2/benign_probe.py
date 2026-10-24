"""Frozen trusted containment probe. Never loads benchmark data or generated code."""

import importlib.metadata
import json
import os
import resource
import socket
import sys
from pathlib import Path

sys.path.insert(0, "/opt/site-packages")
resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))

import evalplus  # noqa: E402 - intentionally isolated installed package path.
import numpy  # noqa: E402
import psutil  # noqa: E402


def main():
    expected_namespaces = json.loads(os.environ["PROBE_PARENT_NAMESPACES"])
    changed = {
        name: os.readlink("/proc/self/ns/" + name) != value
        for name, value in expected_namespaces.items()
    }
    status = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines())
    absent = {
        name: not Path(name).exists()
        for name in (
            "/home",
            "/root",
            "/etc/passwd",
            "/run/user",
            "/dev/nvidia0",
            os.environ["PROBE_UNMOUNTED_SENTINEL"],
        )
    }
    readonly = {}
    for name in ("/opt/python/.write-probe", "/opt/site-packages/.write-probe", "/.write-probe"):
        try:
            Path(name).write_text("synthetic")
            readonly[name] = False
        except OSError:
            readonly[name] = True
    Path("/work/tmp/benign.txt").write_text("synthetic owned temporary data")
    Path("/work/output/benign.txt").write_text("synthetic owned output")
    interfaces = [name for _, name in socket.if_nameindex()]
    blocked = False
    with socket.socket() as channel:
        channel.settimeout(0.2)
        try:
            channel.connect(("198.51.100.1", 9))  # Reserved documentation address.
        except OSError:
            blocked = True
    limits = {
        name: list(resource.getrlimit(getattr(resource, "RLIMIT_" + name)))
        for name in ("AS", "CPU", "NPROC", "NOFILE", "FSIZE", "CORE")
    }
    checks = {
        "new_namespaces": all(changed.values()),
        "host_paths_absent": all(absent.values()),
        "readonly_runtime_and_root": all(readonly.values()),
        "network_blocked": blocked,
        "only_loopback": interfaces == ["lo"],
        "no_new_privileges": status["NoNewPrivs"].strip() == "1",
        "zero_effective_capabilities": int(status["CapEff"].strip(), 16) == 0,
        "nonroot_namespace_uid": os.geteuid() == 65534,
        "environment_cleared": "PROBE_INHERITED_SECRET" not in os.environ,
        "relocated_python": Path(sys.base_prefix) == Path("/opt/python"),
        "limited_cpu_affinity": len(os.sched_getaffinity(0)) == 1,
        "fixed_rlimits": limits
        == {
            "AS": [2147483648] * 2,
            "CPU": [30] * 2,
            "NPROC": [64] * 2,
            "NOFILE": [64] * 2,
            "FSIZE": [1048576] * 2,
            "CORE": [0, 0],
        },
    }
    report = {
        "checks": checks,
        "passed": all(checks.values()),
        "namespaces_changed": changed,
        "packages": {
            name: importlib.metadata.version(name) for name in ("evalplus", "numpy", "psutil")
        },
        "numpy_benign_result": int(numpy.array([2, 3]).sum()),
        "psutil_imported": bool(psutil.__version__),
        "evalplus_imported": evalplus is not None,
        "generated_code_executed": False,
        "benchmark_data_mounted": False,
        "full_evaluator_executed": False,
        "qualified_generated_code_executor": False,
    }
    print(json.dumps(report, sort_keys=True))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
