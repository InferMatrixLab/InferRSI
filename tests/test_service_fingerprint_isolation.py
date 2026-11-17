"""Check cross-file fixture isolation without executing a fingerprint workflow."""

import os
import subprocess
import sys
from pathlib import Path


def test_service_guard_restores_lazy_import_aliases(tmp_path):
    check = tmp_path / "test_aliases.py"
    check.write_text(
        "def test_restored_alias():\n"
        "    from inferrsi.harness import project\n"
        "    from inferrsi.infra import artifacts\n"
        "    assert project.sha256 is artifacts.sha256\n"
        "    assert project.sha256.__module__ == 'inferrsi.infra.artifacts'\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-B", "-m", "pytest", "-p", "no:cacheprovider", "-q",
         "tests/test_project_service_reuse.py::test_exact_round_policy_and_legacy_argument_validation",
         str(check)],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
