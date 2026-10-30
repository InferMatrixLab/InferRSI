"""Confinement policy. The fixture backend is not an operating-system boundary."""

import sys
import time

import pytest

from inferrsi.infra.confinement import (
    ConfinementUnavailable,
    FixtureBackend,
    UnavailableBackend,
    UnshareBackend,
    confined_execute,
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

    def fake_run(argv, **kwargs):
        del kwargs
        calls.append(argv)

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
    assert calls and calls[0][0] == "unshare"
    assert "should-not-run" not in calls[0]
