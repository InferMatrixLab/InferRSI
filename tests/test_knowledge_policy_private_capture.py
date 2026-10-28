"""One-shot owner-approved capture: fixture transport and encryption, no live writes."""

import io
import json
import subprocess
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest

from tools import check_knowledge_model_policy as policy


@pytest.fixture
def capture(tmp_path, monkeypatch):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"before": policy.PRIVATE_CAPTURE_BEFORE,
        "ref": "refs/heads/main", "repository": {"full_name": "InferMatrixLab/InferRSI"}}))
    root = tmp_path / "checkout"
    cert = root / ".github/diagnostics/issue203-capture-public.pem"
    cert.parent.mkdir(parents=True)
    cert.write_text("synthetic public certificate")
    output = tmp_path / "output"
    output.mkdir()
    for key, value in {"ISSUE203_PRIVATE_CAPTURE": "one-shot", "GITHUB_EVENT_NAME": "push",
                       "GITHUB_RUN_ATTEMPT": "1", "GITHUB_REPOSITORY": "InferMatrixLab/InferRSI",
                       "GITHUB_EVENT_PATH": str(event), "RUNNER_TEMP": str(output),
                       "GITHUB_OUTPUT": str(tmp_path / "step-output"),
                       "GITHUB_TOKEN": "FAKE_TOKEN", "EXTRA_SECRET": "FAKE_SECRET"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(policy, "ROOT", root)
    encrypt = Mock(return_value=Mock(stdout=b"synthetic ciphertext"))
    monkeypatch.setattr(policy.subprocess, "run", encrypt)
    payload = {"context": policy.CONTEXT, "state": "pending"}
    return output, event, encrypt, f"statuses/{policy.PRIVATE_CAPTURE_HEAD}", payload


def test_capture_is_once_ciphertext_only_and_child_has_no_credentials(capture, capsys):
    output, _, encrypt, route, payload = capture
    for _ in range(2):
        policy.capture_private_rejection("FAKE_PRIVATE_RESPONSE", route, payload)
    encrypt.assert_called_once()
    assert encrypt.call_args.kwargs["input"] == b"FAKE_PRIVATE_RESPONSE"
    assert encrypt.call_args.kwargs["env"] == {
        "PATH": "/usr/bin:/bin", "LANG": "C", "OPENSSL_CONF": "/dev/null"}
    assert encrypt.call_args.kwargs["stderr"] is subprocess.DEVNULL
    assert encrypt.call_args.kwargs["timeout"] == 10
    assert (output / policy.PRIVATE_CAPTURE_FILE).read_bytes() == b"synthetic ciphertext"
    assert (output / "issue203-capture-attempted").read_bytes() == b""
    assert (output / policy.PRIVATE_CAPTURE_FILE).stat().st_mode & 0o777 == 0o600
    assert (output.parent / "step-output").read_text() == "private_capture=encrypted\n"
    assert "FAKE_PRIVATE_RESPONSE" not in capsys.readouterr().out


@pytest.mark.parametrize("key,value", [
    ("ISSUE203_PRIVATE_CAPTURE", ""), ("GITHUB_EVENT_NAME", "pull_request_target"),
    ("GITHUB_EVENT_NAME", "workflow_dispatch"), ("GITHUB_EVENT_NAME", "issue_comment"),
    ("GITHUB_RUN_ATTEMPT", "2"), ("GITHUB_REPOSITORY", "other/repository"),
])
def test_other_runs_default_off(capture, monkeypatch, key, value):
    output, _, encrypt, route, payload = capture
    monkeypatch.setenv(key, value)
    policy.capture_private_rejection("FAKE_PRIVATE_RESPONSE", route, payload)
    encrypt.assert_not_called()
    assert not list(output.iterdir())


@pytest.mark.parametrize("mutation", [
    {"before": "b" * 40}, {"ref": "refs/heads/other"},
    {"repository": {"full_name": "other/repository"}},
])
def test_unrelated_pushes_do_not_capture(capture, mutation):
    _, event, encrypt, route, payload = capture
    event.write_text(json.dumps({**json.loads(event.read_text()), **mutation}))
    policy.capture_private_rejection("FAKE_PRIVATE_RESPONSE", route, payload)
    encrypt.assert_not_called()


@pytest.mark.parametrize("route,payload", [
    ("statuses/" + "b" * 40, {"context": policy.CONTEXT, "state": "pending"}),
    ("pulls/51", None),
    (f"statuses/{policy.PRIVATE_CAPTURE_HEAD}", {"context": "other", "state": "pending"}),
    (f"statuses/{policy.PRIVATE_CAPTURE_HEAD}", {"context": policy.CONTEXT, "state": "success"}),
])
def test_other_requests_do_not_capture(capture, route, payload):
    _, _, encrypt, _, _ = capture
    policy.capture_private_rejection("FAKE_PRIVATE_RESPONSE", route, payload)
    encrypt.assert_not_called()


def test_encryption_failure_is_fixed_diagnostic_and_not_retried(capture, capsys):
    output, _, encrypt, route, payload = capture
    encrypt.side_effect = subprocess.CalledProcessError(1, "FAKE_SECRET", stderr=b"FAKE_SECRET")
    for _ in range(2):
        policy.capture_private_rejection("FAKE_PRIVATE_RESPONSE", route, payload)
    encrypt.assert_called_once()
    assert not (output / policy.PRIVATE_CAPTURE_FILE).exists()
    assert capsys.readouterr().out == '{"private_capture":"unavailable"}\n'


def test_destination_symlink_is_not_followed(capture, capsys):
    output, _, _, route, payload = capture
    victim = output / "untouched"
    victim.write_bytes(b"untouched")
    (output / policy.PRIVATE_CAPTURE_FILE).symlink_to(victim)
    policy.capture_private_rejection("FAKE_PRIVATE_RESPONSE", route, payload)
    assert victim.read_bytes() == b"untouched"
    assert not (output.parent / "step-output").exists()
    assert "FAKE_PRIVATE_RESPONSE" not in capsys.readouterr().out


@pytest.mark.parametrize("code,errors,expected", [(422, "FAKE_PRIVATE_RESPONSE", 1),
    (422, [{"message": "FAKE_PRIVATE_RESPONSE"}], 0), (403, "FAKE_PRIVATE_RESPONSE", 0)])
def test_only_errors_string_from_existing_422_is_offered(code, errors, expected):
    callback = Mock()
    response = HTTPError("https://example.invalid", code, "", {}, io.BytesIO(json.dumps({
        "message": "FAKE_OTHER_BODY", "errors": errors}).encode()))
    failure = policy.GitHubHTTPError(response, capture=callback)
    assert callback.call_count == expected
    if expected:
        callback.assert_called_once_with("FAKE_PRIVATE_RESPONSE")
        result = policy.status_write_failure(failure, {"description": "fixture"})
        assert result["kind"] == "status-rejected"
        assert result["state"] == "failure"
    assert "FAKE_" not in str(failure)
