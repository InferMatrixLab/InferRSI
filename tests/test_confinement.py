"""Confinement policy. The fixture backend is not an operating-system boundary."""

import json
import sys
import time
from pathlib import Path

import pytest

from inferrsi.infra.confinement import (
    ConfinementUnavailable,
    FixtureBackend,
    UnavailableBackend,
    UnshareBackend,
    confined_execute,
    namespace_plan,
    select_backend,
)


def test_build_write_outside_the_checkout_is_denied_and_does_not_run(tmp_path):
    checkout = tmp_path / "candidate"
    checkout.mkdir()
    ledger = tmp_path / "ledger.json"
    ledger.write_text("safe", encoding="utf-8")
    argv = (
        sys.executable,
        "-c",
        "open(__import__('sys').argv[1], 'w').write('pwned')",
        str(ledger),
    )
    with pytest.raises(ConfinementUnavailable, match="outside writable"):
        confined_execute(
            argv,
            checkout,
            (checkout,),
            (),
            time.monotonic() + 5,
            backend=FixtureBackend(),
        )
    assert ledger.read_text(encoding="utf-8") == "safe"


def test_missing_backend_refuses_without_running(tmp_path):
    marker = tmp_path / "ran"
    argv = (sys.executable, "-c", "open('ran','w').write('yes')")
    with pytest.raises(ConfinementUnavailable, match="unavailable"):
        confined_execute(
            argv,
            tmp_path,
            (tmp_path,),
            (),
            time.monotonic() + 5,
            backend=UnavailableBackend(),
        )
    assert not marker.exists()


def test_select_backend_fails_closed_when_namespaces_are_disabled(monkeypatch):
    monkeypatch.setattr("inferrsi.infra.confinement.namespaces_available", lambda: False)
    assert isinstance(select_backend(), UnavailableBackend)


def test_unshare_failure_does_not_fall_back(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv("SECRET_CANARY", "CANARY-ENV")

    def fake_run(argv, **kwargs):
        del kwargs
        calls.append(json.loads(Path(argv[-1]).read_text(encoding="utf-8")))

        class Completed:
            returncode = 1
            stdout = ""
            stderr = "unshare failed"

        return Completed()

    monkeypatch.setattr("inferrsi.infra.confinement.subprocess.run", fake_run)
    with pytest.raises(ConfinementUnavailable, match="unshare failed"):
        UnshareBackend().run(
            (sys.executable, "-c", "print('should-not-run')"),
            tmp_path,
            (tmp_path,),
            (),
            time.monotonic() + 5,
        )
    assert calls
    assert "SECRET_CANARY" not in calls[0]["env"]
    assert "/" not in {item["source"] for item in calls[0]["mounts"]}


def test_namespace_plan_keeps_host_root_and_secrets_out(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_CANARY", "CANARY-ENV")
    plan = namespace_plan((tmp_path / "writable",), (tmp_path / "readable",))
    assert "/" not in {item["source"] for item in plan["mounts"]}
    assert "SECRET_CANARY" not in plan["env"]
    assert str(tmp_path / "private") not in {item["source"] for item in plan["mounts"]}


def test_build_and_trial_cannot_see_private_canaries(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_CANARY", "CANARY-ENV")
    private = tmp_path / "private"
    private.mkdir()
    (private / "canary.txt").write_text("CANARY-FILE", encoding="utf-8")
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    trial = tmp_path / "trial"
    trial.mkdir()
    script = (
        "import os\n"
        "print(os.environ.get('SECRET_CANARY', ''))\n"
        "try:\n"
        "    print(open(%r).read())\n"
        "except PermissionError:\n"
        "    print('FILE-HIDDEN')\n" % str(private / "canary.txt")
    )
    argv = (sys.executable, "-c", script)
    backend = FixtureBackend()
    stages = (
        confined_execute(argv, checkout, (checkout,), (), time.monotonic() + 10, backend=backend),
        confined_execute(
            argv, checkout, (trial,), (checkout,), time.monotonic() + 10, backend=backend
        ),
    )
    for record in stages:
        assert record["status"] == "completed"
        assert "CANARY-ENV" not in record["stdout"]
        assert "CANARY-FILE" not in record["stdout"]
        assert "FILE-HIDDEN" in record["stdout"]
