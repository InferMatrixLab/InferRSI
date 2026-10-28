"""Local startup/cleanup controls; actual Linux capability remains a separate probe."""

import ast
import ctypes
import errno
import importlib.util
import json
import os
import select
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent


def require(value, message):
    if not value:
        raise ValueError(message)


def main():
    with patch.dict(sys.modules, {"psutil": types.ModuleType("psutil")}):
        spec = importlib.util.spec_from_file_location(
            "startup_driver", ROOT / "bounds_driver.py"
        )
        driver = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(driver)
    controls = []
    for data, expected in (
        (driver.START_TOKEN, 0),
        (b"", 23),
        (b"wrong\n", 23),
        (driver.START_TOKEN[:-1], 23),
        (driver.START_TOKEN + b"x", 23),
    ):
        run = subprocess.run(
            [sys.executable, "-IB", str(ROOT / "synthetic_probe.py"), "gate_check"],
            input=data,
            capture_output=True,
            timeout=8,
            check=False,
        )
        require(run.returncode == expected, "incorrect startup decision")
        require(
            run.stderr
            == (driver.AUTHORIZED_MARKER if expected == 0 else driver.REJECTED_MARKER),
            "incorrect startup marker",
        )
        require(
            json.loads(run.stdout) == {"mode": "gate_check", "passed": True}
            if expected == 0
            else run.stdout == b"",
            "unexpected payload output",
        )
    controls.append(
        "actual gate entry: exact token accepted; EOF, wrong, short and extra byte rejected"
    )

    source = ast.parse((ROOT / "synthetic_probe.py").read_text())
    node = next(
        node
        for node in source.body
        if isinstance(node, ast.FunctionDef) and node.name == "authorize_start"
    )
    namespace = {
        "time": time,
        "select": select,
        "os": os,
        "START_TOKEN": driver.START_TOKEN,
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), "gate", "exec"), namespace)
    for data in (b"", driver.START_TOKEN):
        read_fd, write_fd = os.pipe()
        try:
            if data:
                os.write(write_fd, data)
            try:
                namespace["authorize_start"](read_fd, timeout=0.03)
            except TimeoutError:
                pass
            else:
                raise ValueError("open startup writer authorized without EOF")
        finally:
            os.close(read_fd)
            os.close(write_fd)
    controls.append(
        "held-open empty and full-token pipes time out without authorization"
    )

    with patch.object(driver.ctypes, "CDLL") as library:
        with patch.object(driver.sys, "platform", "darwin"):
            try:
                driver.pidfd_open(1)
            except ValueError:
                pass
            else:
                raise ValueError("foreign platform accepted")
        library.assert_not_called()
    controls.append("foreign ABI rejects before any syscall")
    library = Mock()

    def failed_call(*args):
        ctypes.set_errno(errno.ESRCH)
        return -1

    library.syscall.side_effect = failed_call
    with (
        patch.object(driver.sys, "platform", "linux"),
        patch.object(driver.platform, "machine", return_value="x86_64"),
        patch.object(driver.ctypes, "CDLL", return_value=library),
    ):
        try:
            driver.pidfd_send_signal(10, 9)
        except ProcessLookupError as error:
            require(error.errno == errno.ESRCH, "errno lost")
        else:
            raise ValueError("syscall error accepted")
        require(library.syscall.call_args.args[0].value == 424, "wrong syscall number")
        library.syscall.side_effect = None
        library.syscall.return_value = 55
        require(driver.pidfd_open(123) == 55, "pidfd result lost")
        require(
            library.syscall.call_args.args[0].value == 434, "wrong open syscall number"
        )
    controls.append(
        "fixed raw syscall binding preserves ESRCH and actual descriptor results (mocked)"
    )

    with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
        output = Path(temporary)
        with (
            patch.dict(os.environ, {"SLURM_JOB_ID": "control"}),
            patch.object(
                driver, "pidfd_open", side_effect=OSError(errno.ENOSYS, "unavailable")
            ),
            patch.object(driver.subprocess, "Popen") as launch,
        ):
            require(
                driver.capability(output / "capability.json") == 2,
                "failed API accepted",
            )
            launch.assert_not_called()
        record = json.loads((output / "capability.json").read_bytes())
        require(
            record["passed"] is False and record["error"]["errno"] == errno.ENOSYS,
            "capability failure lost",
        )
    controls.append("capability failure retained before launching a child")

    for bound, observed in ((False, False), (True, False), (True, True)):
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            output = Path(temporary)
            (output / "stdout.json").write_bytes(b"late-output")
            (output / "stderr.private.log").write_bytes(b"")
            process = Mock()
            process.returncode = 0
            process.poll.return_value = 0
            report = {"passed": True}
            with (
                patch.object(driver, "exited", return_value=observed),
                patch.object(driver, "pidfd_send_signal"),
                patch.object(os, "close"),
            ):
                driver.finalize_case(
                    report,
                    process,
                    77 if bound else None,
                    [],
                    [],
                    output,
                    bytearray(),
                    {"rootfs_digest": "control"},
                )
            require(
                report["outputs_stable"] is observed,
                "unobserved namespace exit marked stable",
            )
            require(
                (report["stdout_sha256"] is not None) is observed,
                "unstable output got final hash",
            )
            require(report["passed"] is observed, "unconfirmed cleanup accepted")
            process.stdin.close.assert_called_once()
    controls.append(
        "missing or live init never gets final output hash; authorization pipe closed on cleanup"
    )

    with (
        tempfile.TemporaryDirectory(dir=ROOT) as temporary,
        patch.dict(os.environ, {"SLURM_JOB_ID": "control"}),
    ):
        root = Path(temporary)
        binary = root / "bwrap"
        binary.write_bytes(b"control")
        driver.runtime.write(
            root / "rootfs.json",
            {"executor": {"binary_sha256": driver.runtime.sha(b"control")}},
        )
        driver.runtime.write(
            root / "runtime-locators.private.json", {"bwrap": str(binary)}
        )
        preflight = {
            "passed": True,
            "cleanup_errors": [],
            "job_id": "control",
            "driver_sha256": driver.runtime.sha(
                (ROOT / "bounds_driver.py").read_bytes()
            ),
            "python_binary_sha256": driver.runtime.sha(
                Path(sys._base_executable).read_bytes()
            ),
            "kernel_release": driver.platform.release(),
        }
        cap = root / "cap.json"
        driver.runtime.write(cap, preflight)
        argv = [
            "driver",
            "probe",
            "--inventory",
            str(root),
            "--capability",
            str(cap),
            "--output",
            str(root / "probe"),
        ]
        with (
            patch.object(sys, "argv", argv),
            patch.object(
                driver,
                "run_case",
                return_value={"passed": False, "final_init_exit_observed": False},
            ) as run,
        ):
            require(driver.main() == 2, "incomplete suite accepted")
            require(
                run.call_count == 1, "next sandbox launched after unconfirmed cleanup"
            )
        summary = json.loads((root / "probe/summary.json").read_bytes())
        require(
            summary["unexecuted_modes"] == list(driver.MODES[1:]),
            "unexecuted cases omitted",
        )
        preflight["job_id"] = "different"
        driver.runtime.write(cap, preflight)
        with patch.object(sys, "argv", argv), patch.object(driver, "run_case") as run:
            try:
                driver.main()
            except ValueError:
                pass
            else:
                raise ValueError("foreign job capability accepted")
            run.assert_not_called()
    controls.append(
        "no next case after unconfirmed cleanup; wrong-job capability rejected before bwrap"
    )
    print(
        json.dumps(
            {"passed": True, "controls": controls, "linux_runtime_executed": False}
        )
    )


if __name__ == "__main__":
    main()
