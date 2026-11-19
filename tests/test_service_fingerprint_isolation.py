"""Verify the service guard and its isolation from legacy campaign tests."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_service_guard_restores_lazy_import_aliases(tmp_path):
    check = tmp_path / "test_aliases.py"
    check.write_text(
        "def test_restored_alias():\n"
        "    from inferrsi.harness import artifact_primitives, project, task_protocol\n"
        "    assert project.sha256 is task_protocol.sha256 is artifact_primitives.sha256\n"
        "    assert project.sha256.__module__ == 'inferrsi.harness.artifact_primitives'\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-B", "-m", "pytest", "-p", "no:cacheprovider", "-q",
         "tests/test_project_service_reuse.py::test_exact_round_policy_and_legacy_argument_validation",
         "tests/test_optimization_session.py::test_started_task_uses_frozen_protocol_without_registry",
         str(check)],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_guard_blocks_lazily_imported_fingerprints_even_when_caught(monkeypatch, tmp_path):
    from tests.test_project_service_reuse import no_fingerprints

    guard = no_fingerprints.__wrapped__(monkeypatch)
    next(guard)
    from inferrsi.harness.task_protocol import sha256

    with pytest.raises(AssertionError, match="must not calculate"):
        sha256(tmp_path / "unread-file")
    with pytest.raises(AssertionError, match="fingerprint call was attempted"):
        next(guard)
