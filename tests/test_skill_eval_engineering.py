import copy
import json
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from inferrsi.harness import skill_eval_engineering as engineering

TASK = {"id": "serving-parser", "split": "development", "request": engineering.REQUEST,
        "provenance": "Reconstructed public regression fixture"}
ANSWER = {"artifact": "parser.py", "summary": "Repair", "artifact_source": engineering.STARTER}


def test_starter_matches_frozen_fixture():
    fixture = Path(__file__).parent / "fixtures/skill_eval_engineering/parser.py"
    assert fixture.read_text() == engineering.STARTER


@pytest.mark.parametrize("change", [{"split": "holdout"}, {"split": "discovery"},
                                    {"id": "../escape"}, {"expected": True},
                                    {"request": ""}, {"request": "Grade an unrelated task"}])
def test_strict_task_boundary(change):
    with pytest.raises(ValueError):
        engineering.validate_task({**TASK, **change})


@pytest.mark.parametrize("change", [{"artifact": "other.py"}, {"artifact_source": None},
                                    {"artifact_source": ""}, {"passed": True},
                                    {"artifact_source": "x" * 65537}])
def test_missing_wrong_or_oversized_artifact_never_executes(change):
    with mock.patch.object(engineering, "_invoke") as invoke:
        assert not engineering.verify(TASK, {**ANSWER, **change})["passed"]
        invoke.assert_not_called()


def test_unavailable_sandbox_is_not_a_failing_skill_or_host_fallback():
    with mock.patch.object(engineering, "_invoke", return_value=None) as invoke:
        with pytest.raises(engineering.SandboxUnavailable):
            engineering.verify(TASK, ANSWER)
        assert invoke.call_count == 1
        assert invoke.call_args.kwargs == {"probe": True}


def test_trusted_parent_compares_each_behavior_not_agent_checks():
    expected = [{"success": success, "reason": reason}
                for _, _, _, _, success, reason in engineering.VECTORS]
    with mock.patch.object(engineering, "_invoke", side_effect=[{"ready": True}, *expected]):
        result = engineering.verify(TASK, ANSWER)
    assert result["passed"]
    assert len(result["assertions"]) == len(engineering.VECTORS)
    # These are controller tests with mocked processes, not an artifact PASS.
    wrong = copy.deepcopy(expected)
    wrong[4] = {"success": True, "reason": "length"}
    with mock.patch.object(engineering, "_invoke", side_effect=[{"ready": True}, *wrong]):
        result = engineering.verify(TASK, ANSWER)
    assert not result["passed"]
    assert result["assertions"]["stream_error"] is False


def test_child_receives_inputs_without_expected_results():
    calls = []

    def invoke(work, arguments=None, *, probe=False):
        assert (work / "parser.py").read_text() == ANSWER["artifact_source"]
        assert sorted(path.name for path in work.iterdir()) == ["parser.py", "runner.py"]
        if probe:
            return {"ready": True}
        calls.append(arguments)
        return {"success": False, "reason": "malformed_frame"}

    with mock.patch.object(engineering, "_invoke", side_effect=invoke):
        engineering.verify(TASK, ANSWER)
    assert calls == [[status, frames, count] for _, status, frames, count, _, _
                     in engineering.VECTORS]
    assert "VECTORS" not in engineering.RUNNER


def test_exact_boolean_and_reason_required():
    for wrong in ({"success": 1, "reason": "length"}, {"success": True, "reason": "anything"},
                  {"success": True, "reason": "length", "extra": True}, None):
        with mock.patch.object(engineering, "_invoke",
                               side_effect=[{"ready": True}] + [wrong] * len(engineering.VECTORS)):
            assert not engineering.verify(TASK, ANSWER)["passed"]


@pytest.mark.skipif(sys.platform != "linux", reason="Linux sandbox command layout")
def test_sandbox_command_has_no_host_home_repo_or_network_mount():
    with mock.patch.object(engineering.shutil, "which", return_value="/usr/bin/bwrap"), \
         mock.patch.object(Path, "resolve", return_value=Path("/usr/bin/python3.13")), \
         mock.patch.object(Path, "is_file", return_value=True), \
         mock.patch.object(Path, "is_dir", return_value=True):
        command = engineering.sandbox_command(Path("/temporary/test-artifact"))
    assert "--unshare-all" in command
    assert "--clearenv" in command
    assert command[command.index("--remount-ro") + 1] == "/"
    bindings = [command[i + 1:i + 3] for i, item in enumerate(command) if item == "--ro-bind"]
    assert ["/temporary/test-artifact", "/work"] in bindings
    assert all(source not in ("/", "/home", "/tmp", "/workspace") for source, _ in bindings)
    assert not any("--share" in item for item in command)
    assert command[-5:] == ["/usr/bin/python3", "-I", "-S", "-B", "/work/runner.py"]


def test_no_bwrap_is_fail_closed():
    with mock.patch.object(engineering.shutil, "which", return_value=None):
        with pytest.raises(engineering.SandboxUnavailable):
            engineering.sandbox_command(Path("/unused"))


def test_invoke_uses_clean_environment_and_bounded_output():
    process = mock.Mock(returncode=0)

    def start(*args, **kwargs):
        assert kwargs["env"] == {"PATH": "/usr/bin:/bin", "LANG": "C"}
        assert kwargs["start_new_session"] is True
        kwargs["stdout"].write(json.dumps({"ready": True}).encode())
        return process

    with mock.patch.object(engineering, "sandbox_command", return_value=["sandbox"]), \
         mock.patch.object(engineering.subprocess, "Popen", side_effect=start):
        assert engineering._invoke(Path("/unused"), probe=True) == {"ready": True}
    assert process.communicate.call_args.kwargs["timeout"] == 5


@pytest.mark.skipif(sys.platform != "linux", reason="Linux process-group cleanup")
def test_task_timeout_kills_process_group_and_is_failure():
    process = mock.Mock(returncode=-9, pid=123456)
    process.communicate.side_effect = [subprocess.TimeoutExpired("sandbox", 5), None]

    def start(*args, **kwargs):
        kwargs["stderr"].write(b"INFERRSI_ARTIFACT_READY\n")
        return process

    with mock.patch.object(engineering, "sandbox_command", return_value=["sandbox"]), \
         mock.patch.object(engineering.subprocess, "Popen", side_effect=start), \
         mock.patch.object(engineering.os, "killpg") as kill:
        assert engineering._invoke(Path("/unused"), []) is None
    kill.assert_called_once_with(process.pid, engineering.signal.SIGKILL)


def test_real_sandbox_known_bad_starter_or_explicit_unavailable():
    # No model call. This fixture is our published starter, not downloaded code.
    try:
        result = engineering.verify(TASK, ANSWER)
    except engineering.SandboxUnavailable as error:
        pytest.skip(str(error))
    assert not result["passed"]
    assert result["assertions"]["length"]
    assert not result["assertions"]["stream_error"]


# Authored software control; never recorded as a model-produced candidate.
GOOD_ARTIFACT = '''def evaluate(status, frames, requested_tokens):
    def result(reason):
        return {"success": reason in ("length", "stop"), "reason": reason}
    if status != 200:
        return result("http_error")
    terminal = None
    done = False
    for index, frame in enumerate(frames):
        if frame == "[DONE]":
            if done or index != len(frames) - 1:
                return result("malformed_frame")
            done = True
            continue
        if isinstance(frame, dict) and "error" in frame:
            return result("stream_error")
        if done or terminal is not None or not isinstance(frame, dict):
            return result("malformed_frame")
        if set(frame) == {"content"} and type(frame["content"]) is str:
            continue
        if (set(frame) != {"finish_reason", "completion_tokens"}
                or frame["finish_reason"] not in ("length", "stop")
                or type(frame["completion_tokens"]) is not int
                or frame["completion_tokens"] < 0):
            return result("malformed_frame")
        terminal = frame
    if terminal is None:
        return result("missing_terminal")
    count = terminal["completion_tokens"]
    finish = terminal["finish_reason"]
    if count > requested_tokens or (finish == "length" and count != requested_tokens):
        return result("token_mismatch")
    return result(finish)
'''


def test_real_sandbox_known_correct_control_or_explicit_unavailable():
    try:
        result = engineering.verify(TASK, {**ANSWER, "artifact_source": GOOD_ARTIFACT})
    except engineering.SandboxUnavailable as error:
        pytest.skip(str(error))
    assert result["passed"]


def test_regular_snapshot_rejects_symlink_oversize_and_fifo(tmp_path):
    source = tmp_path / "parser.py"
    source.write_bytes(b"code")
    assert engineering.read_regular(source, 4) == b"code"
    with pytest.raises(ValueError):
        engineering.read_regular(source, 3)
    link = tmp_path / "linked.py"
    link.symlink_to(source)
    with pytest.raises(ValueError):
        engineering.read_regular(link, 100)
    if hasattr(engineering.os, "mkfifo"):
        fifo = tmp_path / "pipe"
        engineering.os.mkfifo(fifo)
        with pytest.raises(ValueError):
            engineering.read_regular(fifo, 100)


def test_input_manifest_excludes_only_mutable_artifact_and_rejects_special_nodes(tmp_path):
    (tmp_path / "task.json").write_text("{}")
    (tmp_path / "parser.py").write_text(engineering.STARTER)
    before = engineering.input_hashes(tmp_path)
    assert set(before) == {"task.json"}
    (tmp_path / "parser.py").write_text("changed")
    assert engineering.input_hashes(tmp_path) == before
    (tmp_path / "extra.txt").write_text("not allowed")
    assert engineering.input_hashes(tmp_path) != before
    (tmp_path / "link").symlink_to(tmp_path / "task.json")
    with pytest.raises(ValueError):
        engineering.input_hashes(tmp_path)


def test_negative_count_mutant_is_caught_by_public_oracle():
    # Execute only this repository-authored fixture, not submitted agent code.
    # This is an oracle control, not evidence that the real sandbox ran.
    mutant = GOOD_ARTIFACT.replace(' or frame["completion_tokens"] < 0', '')
    assert mutant != GOOD_ARTIFACT
    namespace = {}
    exec(compile(mutant, "trusted-mutant-fixture", "exec"), namespace)
    name, status, frames, count, success, reason = next(
        vector for vector in engineering.VECTORS if vector[0] == "negative_count")
    assert namespace["evaluate"](status, frames, count) != {"success": success, "reason": reason}


@pytest.mark.parametrize("ready", [False, True])
def test_worker_startup_failure_differs_from_artifact_crash(ready):
    process = mock.Mock(returncode=1)

    def start(*args, **kwargs):
        if ready:
            kwargs["stderr"].write(b"INFERRSI_ARTIFACT_READY\n")
        return process

    with mock.patch.object(engineering, "sandbox_command", return_value=["sandbox"]), \
         mock.patch.object(engineering.subprocess, "Popen", side_effect=start):
        if ready:
            assert engineering._invoke(Path("/unused"), []) is None
        else:
            with pytest.raises(engineering.SandboxUnavailable, match="trusted boundary"):
                engineering._invoke(Path("/unused"), [])
