"""Local controls exercise decision logic only; no Linux sandbox is executed."""

import ast
import errno
import json
import os
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
    # Load just the filter constructor, never the finite process/IPC probes.
    module = ast.parse((ROOT / "synthetic_probe.py").read_text())
    selected = [
        node
        for node in module.body
        if (isinstance(node, ast.FunctionDef) and node.name == "filter_instructions")
        or (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "IPC_SYSCALLS"
                for target in node.targets
            )
        )
    ]
    namespace = {"errno": errno}
    exec(
        compile(ast.Module(body=selected, type_ignores=[]), "filter-control", "exec"),
        namespace,
    )
    program = namespace["filter_instructions"]()

    def evaluate(architecture, number):
        accumulator = 0
        pc = 0
        while pc < len(program):
            opcode, yes, no, value = program[pc]
            if opcode == 0x20:
                accumulator = {0: number, 4: architecture}[value]
            elif opcode == 0x15:
                pc += yes if accumulator == value else no
            elif opcode == 0x35:
                pc += yes if accumulator >= value else no
            elif opcode == 0x06:
                return value
            else:
                raise ValueError("unexpected BPF opcode")
            pc += 1
        raise ValueError("filter failed to return")

    expected_denied = {29, 30, 31, 64, 65, 66, 67, 68, 69, 70, 71, 220, 240}
    controls = []
    for number in range(451):
        expected = 0x50000 | errno.EPERM if number in expected_denied else 0x7FFF0000
        require(evaluate(0xC000003E, number) == expected, f"syscall {number}")
    controls.append("all native syscall decisions 0 through 450")
    for architecture, number in (
        (0x40000003, 117),
        (0xC00000B7, 29),
        (0, 0),
        (0xC000003E, 0x40000000),
        (0xC000003E, 0x4000001D),
    ):
        require(
            evaluate(architecture, number) == 0x80000000, "ABI mismatch was not killed"
        )
    controls.append("three other architectures and two x32 calls denied")

    # psutil is intentionally not installed in this local tooling environment.
    # These controls never use it; the registered cluster runtime already has it.
    with patch.dict(sys.modules, {"psutil": types.ModuleType("psutil")}):
        sys.path.insert(0, str(ROOT))
        import bounds_driver as driver

    for pairs in ((("x", 1), ("x", 2)),):
        try:
            driver.unique(pairs)
        except ValueError:
            pass
        else:
            raise ValueError("duplicate JSON keys accepted")
    controls.append("duplicate status keys rejected")
    fields = {"PPid": "10", "NSpid": "20 1"}
    record = {"child-pid": 20, "pid-namespace": 99}
    with (
        patch.object(driver, "pidfd_open", return_value=77),
        patch.object(os, "close"),
        patch.object(os, "readlink", return_value="pid:[99]"),
        patch.object(driver, "status", return_value=fields),
        patch.object(driver, "exited", return_value=False),
    ):
        held, identity = driver.bind_init(record, 10)
        require(
            held == 77 and identity["namespace_pids"] == [20, 1], "valid init rejected"
        )
    controls.append("valid namespace-init identity accepted")
    cases = (
        ({"child-pid": True, "pid-namespace": 99}, fields, False, "pid:[99]"),
        (record, {"PPid": "11", "NSpid": "20 1"}, False, "pid:[99]"),
        (record, {"PPid": "10", "NSpid": "20 2"}, False, "pid:[99]"),
        (record, fields, True, "pid:[99]"),
        (record, fields, False, "pid:[100]"),
    )
    for value, observed, dead, link in cases:
        with (
            patch.object(driver, "pidfd_open", return_value=77),
            patch.object(os, "close"),
            patch.object(os, "readlink", return_value=link),
            patch.object(driver, "status", return_value=observed),
            patch.object(driver, "exited", return_value=dead),
        ):
            try:
                driver.bind_init(value, 10)
            except ValueError:
                pass
            else:
                raise ValueError("invalid namespace-init identity accepted")
    controls.append("five invalid init identities rejected")
    with (
        patch.object(driver, "pidfd_open", return_value=77),
        patch.object(os, "close") as closed,
        patch.object(os, "readlink", return_value="pid:[99]"),
        patch.object(driver, "status", return_value=fields),
        patch.object(driver, "exited", side_effect=[False, True]),
    ):
        try:
            driver.bind_init(record, 10)
        except ValueError:
            closed.assert_called_once_with(77)
        else:
            raise ValueError("init exit during binding accepted")
    controls.append("exit during identity binding rejected and pidfd closed")
    for end in ("eof", "timeout"):
        read_fd, write_fd = os.pipe()
        raw = bytearray()
        try:
            os.write(write_fd, b'{"child-')
            if end == "eof":
                os.close(write_fd)
                write_fd = -1
            try:
                driver.read_line(read_fd, time.monotonic() + 0.05, raw)
            except ValueError:
                require(raw == b'{"child-', "partial status bytes lost")
            else:
                raise ValueError("incomplete status line accepted")
        finally:
            os.close(read_fd)
            if write_fd >= 0:
                os.close(write_fd)
    controls.append("partial status retained on EOF and deadline")
    for scenario in ("exit_race", "wait_timeout", "stdout_failure"):
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            output = Path(temporary)
            (output / "stdout.json").write_bytes(b'{"partial":true}\n')
            (output / "stderr.private.log").write_bytes(b"")
            report = {"passed": False, "error": {"type": "OriginalProbeFailure"}}
            process = Mock()
            process.returncode = None if scenario == "wait_timeout" else 0
            process.poll.return_value = process.returncode
            process.wait.side_effect = subprocess.TimeoutExpired("trusted", 5)
            with (
                patch.object(
                    driver, "exited", side_effect=[False, True, True, True]
                ) as observed,
                patch.object(
                    driver, "pidfd_send_signal", side_effect=ProcessLookupError
                ),
                patch.object(os, "close") as closed,
            ):
                if scenario != "exit_race":
                    observed.side_effect = None
                    observed.return_value = True
                if scenario == "stdout_failure":
                    with patch.object(
                        Path,
                        "read_bytes",
                        side_effect=OSError("synthetic read failure"),
                    ):
                        driver.finalize_case(
                            report,
                            process,
                            77,
                            [],
                            [80, -1],
                            output,
                            bytearray(b"partial-status"),
                            {"rootfs_digest": "bound"},
                        )
                else:
                    driver.finalize_case(
                        report,
                        process,
                        77,
                        [],
                        [80, -1],
                        output,
                        bytearray(b"partial-status"),
                        {"rootfs_digest": "bound"},
                    )
                require(closed.call_count == 2, "later descriptors were not closed")
            actual = json.loads((output / "report.json").read_text())
            require(
                actual["error"] == report["error"] and not actual["passed"],
                "original failure lost",
            )
            require(
                (output / "status.private.jsonl").read_bytes() == b"partial-status",
                "status lost",
            )
            errors = actual["cleanup_or_evidence_errors"]
            if scenario == "exit_race":
                require(
                    actual["signal_race_already_exited"] and not errors,
                    "exit race not confirmed",
                )
            elif scenario == "wait_timeout":
                require(
                    any(row["type"] == "TimeoutExpired" for row in errors),
                    "wait failure lost",
                )
                require(
                    actual["outputs_stable"] is False
                    and actual["cleanup_complete"] is False
                    and actual["stdout_sha256"] is None
                    and actual["stderr_sha256"] is None,
                    "live launcher incorrectly got stable final hashes",
                )
            else:
                require(
                    actual["stdout_sha256"] is None
                    and any(row["operation"] == "read_stdout" for row in errors),
                    "read failure lost",
                )
    controls.append(
        "cleanup exit race, wait timeout and stdout failure retain original errors and records"
    )
    # Syntax compilation checks all sources without executing platform probes.
    for name in ("runtime.py", "bounds_driver.py", "synthetic_probe.py"):
        compile((ROOT / name).read_text(), name, "exec")
    controls.append("three runtime sources compile")
    isolated = subprocess.run(
        [
            sys.executable,
            "-IB",
            "-c",
            "import runpy,sys,types; sys.modules['psutil']=types.ModuleType('psutil'); "
            "runpy.run_path(sys.argv[1], run_name='trusted_import_control')",
            str(ROOT / "bounds_driver.py"),
        ],
        capture_output=True,
        timeout=10,
    )
    require(isolated.returncode == 0, isolated.stderr.decode())
    controls.append(
        "isolated interpreter loads exact adjacent runtime; psutil import stubbed"
    )
    print(
        json.dumps(
            {"passed": True, "controls": controls, "linux_runtime_executed": False}
        )
    )


if __name__ == "__main__":
    main()
