"""#412 R3: Harness runs a frozen task protocol only in a child interpreter.

Each operation is one ``python -I -B protocol_child.py`` process under a deadline. The
tests drive real child processes; the envelope cases substitute the child script itself
to inject faults the real entry never writes.
"""

import ast
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from inferrsi.benchmark.registry import task_resources
from inferrsi.harness import protocol_child, task_protocol
from inferrsi.harness.task_protocol import TaskProtocolError, run

SETTINGS = {"pairs": 2, "samples": 1, "warmups": 1}
QWEN_ARGUMENTS = ["--pairs", "2", "--samples", "1", "--warmups", "1"]


def write_protocol(root, body):
    root.mkdir(parents=True, exist_ok=True)
    path = root / "optimization.py"
    path.write_text(body, encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def failure(root, digest, operation="validate_arguments", **arguments):
    with pytest.raises(TaskProtocolError) as error:
        run(root, digest, operation, **(arguments or {"arguments": []}))
    return error.value


def qwen():
    root = Path(str(task_resources("qwen21-denoise-npu")))
    return root, hashlib.sha256((root / "optimization.py").read_bytes()).hexdigest()


def test_qwen21_protocol_answers_all_three_operations(tmp_path):
    root, digest = qwen()
    assert run(root, digest, "validate_arguments", arguments=QWEN_ARGUMENTS) == SETTINGS
    candidate, output = tmp_path / "candidate.py", tmp_path / "measurement"
    assert run(root, digest, "arguments", candidate=candidate, output=output,
               settings=SETTINGS) == [
        "--candidate", str(candidate), "--output-dir", str(output), "--device", "npu",
        "--pairs", "2", "--samples", "1", "--warmups", "1"]
    assessment = run(root, digest, "assess", directory=tmp_path, settings=SETTINGS,
                     execution={"status": "completed", "returncode": 0})
    assert assessment == {"status": "infrastructure_failure", "score": None,
                          "verdict": "INCONCLUSIVE", "reason": "missing_task_result"}


def test_argparse_usage_error_keeps_exit_status_two_and_its_message(capsys):
    root, digest = qwen()
    with pytest.raises(SystemExit) as stop:
        run(root, digest, "validate_arguments", arguments=["--pairs", "0x"])
    assert stop.value.code == 2
    assert "invalid int value" in capsys.readouterr().err


def test_protocol_exception_keeps_its_type_and_message(tmp_path):
    digest = write_protocol(tmp_path, "def validate_arguments(a):\n"
                                      "    raise TypeError('bad settings')\n")
    error = failure(tmp_path, digest)
    assert error.kind == "protocol_exception"
    # The protocol's own message and "<Type>: <message>" survive the child transport.
    assert str(error) == "bad settings"
    assert error.reason == "TypeError: bad settings"


def test_transport_failures_stay_distinguishable_from_protocol_exceptions(tmp_path):
    digest = write_protocol(tmp_path,
                            "def validate_arguments(a):\n    return {'x': float('nan')}\n")
    error = failure(tmp_path, digest)
    assert error.kind == "result"
    assert error.reason == f"TaskProtocolError: {error}"
    assert str(error).startswith("result: ValueError: ")


@pytest.mark.parametrize("value, message", [
    ("float('nan')", "Out of range float values are not JSON compliant"),
    ("object()", "is not JSON serializable"),
])
def test_unserializable_results_are_rejected_in_the_child(tmp_path, value, message):
    digest = write_protocol(tmp_path, f"def validate_arguments(a):\n    return {{'x': {value}}}\n")
    error = failure(tmp_path, digest)
    assert error.kind == "result" and message in str(error)


@pytest.mark.parametrize("result", ["[1]", "'text'", "None"])
def test_result_of_the_wrong_type_is_an_invalid_response(tmp_path, result):
    digest = write_protocol(tmp_path, f"def validate_arguments(a):\n    return {result}\n")
    error = failure(tmp_path, digest)
    assert error.kind == "invalid_response"
    assert "validate_arguments result must be a dict" in str(error)


def test_arguments_result_must_be_strings(tmp_path):
    digest = write_protocol(tmp_path, "def arguments(c, o, s):\n    return ['ok', 3]\n")
    error = failure(tmp_path, digest, "arguments", candidate=tmp_path / "c.py",
                    output=tmp_path / "o", settings={})
    assert error.kind == "invalid_response"


def test_protocol_output_goes_to_stderr_and_never_reaches_the_envelope(tmp_path, capsys):
    digest = write_protocol(tmp_path, (
        "import os, subprocess, sys\n"
        "def validate_arguments(a):\n"
        "    print('python print')\n"
        "    sys.stdout.flush()\n"
        "    os.write(1, b'raw descriptor write\\n')\n"
        "    subprocess.run([sys.executable, '-c', 'print(\"grandchild\")'], check=True)\n"
        "    print('diagnostic line', file=sys.stderr)\n"
        "    return {'kept': True}\n"))
    assert run(tmp_path, digest, "validate_arguments", arguments=[]) == {"kept": True}
    # Each of these small writes reaches the caller's stderr within the forwarded tail.
    forwarded = capsys.readouterr().err
    for line in ("python print", "raw descriptor write", "grandchild", "diagnostic line"):
        assert line in forwarded


def test_diagnostics_are_forwarded_when_the_protocol_raises(tmp_path, capsys):
    digest = write_protocol(tmp_path, (
        "import sys\n"
        "def validate_arguments(a):\n"
        "    print('context before failure', file=sys.stderr)\n"
        "    raise ValueError('rejected')\n"))
    error = failure(tmp_path, digest)
    assert str(error) == "rejected" and error.reason == "ValueError: rejected"
    assert "context before failure" in capsys.readouterr().err


def test_only_the_stderr_tail_is_forwarded(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(task_protocol, "STDERR_TAIL_BYTES", 16)
    digest = write_protocol(tmp_path, (
        "import sys\n"
        "def validate_arguments(a):\n"
        "    sys.stderr.write('x' * 100 + 'END-OF-LOG')\n"
        "    return {}\n"))
    run(tmp_path, digest, "validate_arguments", arguments=[])
    assert capsys.readouterr().err == "xxxxxxEND-OF-LOG"


@pytest.mark.parametrize("payload, kind", [
    (b"", "malformed_response"),
    (b"{not json", "malformed_response"),
    (b'{"a":1,"a":2}', "malformed_response"),
    (b'{"x":NaN}', "malformed_response"),
    (b'{"x":1e999}', "malformed_response"),
    (b'{"schema_version":2,"operation":"validate_arguments","result":{}}',
     "invalid_response"),
    (b'{"schema_version":1,"operation":"assess","result":{}}', "invalid_response"),
    (b'{"schema_version":1,"operation":"validate_arguments","result":{},"error":{}}',
     "invalid_response"),
    (b'{"schema_version":1,"operation":"validate_arguments",'
     b'"error":{"kind":"unknown","type":"X","message":"m"}}', "invalid_response"),
])
def test_malformed_or_foreign_envelopes_are_distinct_failures(tmp_path, monkeypatch, capsys,
                                                              payload, kind):
    # Fault injection: a real child process writes exactly these envelope bytes.
    child = tmp_path / "child.py"
    child.write_text("import os, sys\nsys.stderr.write('child diagnostics')\n"
                     f"os.write(1, {payload!r})\n", encoding="utf-8")
    monkeypatch.setattr(task_protocol, "CHILD_ENTRY", child)
    digest = write_protocol(tmp_path / "task", "def validate_arguments(a):\n    return {}\n")
    assert failure(tmp_path / "task", digest).kind == kind
    assert "child diagnostics" in capsys.readouterr().err


def test_child_exit_without_an_envelope_is_an_exit_status_failure(tmp_path, capsys):
    digest = write_protocol(tmp_path, (
        "import os, sys\n"
        "def validate_arguments(a):\n"
        "    sys.stderr.write('protocol broke')\n"
        "    sys.stderr.flush()\n"
        "    os._exit(3)\n"))
    error = failure(tmp_path, digest)
    assert error.kind == "exit_status"
    assert "exited with 3" in str(error) and "protocol broke" in str(error)
    assert "protocol broke" in capsys.readouterr().err


def test_launch_failure_is_a_transport_failure(tmp_path, monkeypatch):
    digest = write_protocol(tmp_path, "def validate_arguments(a):\n    return {}\n")
    monkeypatch.setattr(task_protocol.sys, "executable", str(tmp_path / "missing-python"))
    assert failure(tmp_path, digest).kind == "launch"


def test_oversized_envelope_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(task_protocol, "STDOUT_LIMIT_BYTES", 64)
    digest = write_protocol(tmp_path, "def validate_arguments(a):\n    return {'x': 'y' * 100}\n")
    assert failure(tmp_path, digest).kind == "output_limit"


def _late_writer(marker):
    # repr() quotes the whole child program, so a Windows path inside it stays valid source.
    code = f"import pathlib, time; time.sleep(4); pathlib.Path({str(marker)!r}).write_text('x')"
    return f"    subprocess.Popen([sys.executable, '-c', {code!r}])\n"


def test_deadline_stops_the_child_and_its_descendants(tmp_path, monkeypatch, capsys):
    marker = tmp_path / "late.txt"
    monkeypatch.setattr(task_protocol, "PROTOCOL_TIMEOUT_SECONDS", 3.0)
    digest = write_protocol(tmp_path / "task", (
        "import subprocess, sys, time\n"
        "def validate_arguments(a):\n" + _late_writer(marker) +
        "    print('waiting past the deadline', file=sys.stderr, flush=True)\n"
        "    time.sleep(60)\n"))
    started = time.monotonic()
    assert failure(tmp_path / "task", digest).kind == "timeout"
    assert time.monotonic() - started < 30
    assert "waiting past the deadline" in capsys.readouterr().err
    time.sleep(5)
    assert not marker.exists()


@pytest.mark.parametrize("body, raises", [
    ("    return {}\n", False),
    ("    raise ValueError('rejected')\n", True),
])
def test_scratch_directory_is_removed_after_every_operation(tmp_path, monkeypatch, body,
                                                           raises):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(task_protocol.tempfile, "tempdir", str(scratch))
    digest = write_protocol(tmp_path / "task", "def validate_arguments(a):\n" + body)
    if raises:
        assert failure(tmp_path / "task", digest).kind == "protocol_exception"
    else:
        assert run(tmp_path / "task", digest, "validate_arguments", arguments=[]) == {}
    assert list(scratch.iterdir()) == []


def test_descendants_left_running_are_stopped_with_the_child(tmp_path):
    marker = tmp_path / "late.txt"
    digest = write_protocol(tmp_path / "task", (
        "import subprocess, sys\n"
        "def validate_arguments(a):\n" + _late_writer(marker) + "    return {'done': True}\n"))
    assert run(tmp_path / "task", digest, "validate_arguments", arguments=[]) == {"done": True}
    time.sleep(5)
    assert not marker.exists()


def test_changed_protocol_bytes_never_run(tmp_path):
    marker = tmp_path / "ran.txt"
    digest = write_protocol(tmp_path / "task", "def validate_arguments(a):\n    return {}\n")
    (tmp_path / "task/optimization.py").write_text(
        f"import pathlib\npathlib.Path({str(marker)!r}).write_text('x')\n"
        "def validate_arguments(a):\n    return {}\n", encoding="utf-8")
    assert failure(tmp_path / "task", digest).kind == "identity"
    assert not marker.exists()


def test_child_checks_the_digest_of_the_bytes_it_compiles(tmp_path):
    # The child re-reads and checks the protocol itself, so bytes swapped after the
    # parent's check still never run.
    marker = tmp_path / "ran.txt"
    good = write_protocol(tmp_path, "def validate_arguments(a):\n    return {}\n")
    (tmp_path / "optimization.py").write_text(
        f"import pathlib\npathlib.Path({str(marker)!r}).write_text('x')\n", encoding="utf-8")
    request = tmp_path / "request.json"
    request.write_bytes(protocol_child.dumps_strict({
        "schema_version": 1, "operation": "validate_arguments",
        "protocol": str(tmp_path / "optimization.py"), "protocol_sha256": good,
        "arguments": {"arguments": []}}))
    completed = subprocess.run(
        [sys.executable, "-I", "-B", str(task_protocol.CHILD_ENTRY), str(request)],
        capture_output=True, check=True, timeout=60)
    assert json.loads(completed.stdout)["error"]["kind"] == "identity"
    assert not marker.exists()


@pytest.mark.parametrize("arguments, message", [
    ({"arguments": "not a list"}, "list of strings"),
    ({"arguments": [], "extra": 1}, "takes exactly"),
])
def test_invalid_requests_fail_before_any_child_starts(tmp_path, arguments, message):
    digest = write_protocol(tmp_path, "def validate_arguments(a):\n    return {}\n")
    error = failure(tmp_path, digest, **arguments)
    assert error.kind == "request" and message in str(error)


def test_relative_paths_are_rejected(tmp_path):
    digest = write_protocol(tmp_path, "def arguments(c, o, s):\n    return []\n")
    error = failure(tmp_path, digest, "arguments", candidate=Path("candidate.py"),
                    output=tmp_path, settings={})
    assert error.kind == "request" and "absolute" in str(error)


def test_child_is_isolated_loads_no_inferrsi_and_writes_no_bytecode(tmp_path, monkeypatch):
    # -I drops PYTHONPATH and the working directory from sys.path; -B writes no cache.
    shadow = tmp_path / "shadow"
    shadow.mkdir()
    (shadow / "json.py").write_text("raise RuntimeError('shadowed')\n", encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(shadow))
    monkeypatch.setenv("R3_PROBE", "kept")
    digest = write_protocol(tmp_path / "task", (
        "import json, os, sys\n"
        "def validate_arguments(a):\n"
        "    return {'isolated': sys.flags.isolated, 'no_bytecode': sys.dont_write_bytecode,\n"
        "            'inferrsi': [m for m in sys.modules if m.startswith('inferrsi')],\n"
        "            'probe': os.environ.get('R3_PROBE')}\n"))
    assert run(tmp_path / "task", digest, "validate_arguments", arguments=[]) == {
        "isolated": 1, "no_bytecode": True, "inferrsi": [], "probe": "kept"}
    assert not list((tmp_path / "task").rglob("__pycache__"))


def test_harness_never_executes_protocol_code_in_process(tmp_path):
    digest = write_protocol(tmp_path, "def validate_arguments(a):\n    return {}\n")
    run(tmp_path, digest, "validate_arguments", arguments=[])
    assert "task_optimization_protocol" not in sys.modules
    source = Path(task_protocol.__file__).read_text(encoding="utf-8")
    assert "module_from_spec" not in source and "exec(" not in source


def test_child_entry_imports_only_the_standard_library():
    tree = ast.parse(task_protocol.CHILD_ENTRY.read_text(encoding="utf-8"))
    imported = {alias.name.split(".")[0] for node in ast.walk(tree)
                if isinstance(node, ast.Import) for alias in node.names}
    imported |= {(node.module or "").split(".")[0] for node in ast.walk(tree)
                 if isinstance(node, ast.ImportFrom)}
    assert not [node for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.level]
    assert imported <= set(sys.stdlib_module_names), imported


def test_prepare_freezes_exactly_the_validated_protocol(tmp_path):
    source, digest = qwen()
    settings = task_protocol.prepare(source, tmp_path / "frozen", QWEN_ARGUMENTS)
    assert settings["evaluation_settings"] == SETTINGS
    assert settings["frozen_files"]["optimization.py"] == digest
