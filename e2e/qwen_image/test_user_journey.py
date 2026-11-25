"""Explicit acceptance entry: live Agent run or read-only evidence replay."""

from pathlib import Path
from subprocess import CalledProcessError

import pytest

from e2e.qwen_image.audit import EvidenceViolation, audit, read, reference
from e2e.qwen_image.driver import discover, launch
from e2e.qwen_image.retest import execute, seal, write


@pytest.fixture(scope="module")
def observed(e2e_options):
    options = e2e_options
    if not options["live"]:
        report = audit(options["campaign"], options["observer"])
        if options["artifacts"]:
            output = Path(options["artifacts"])
            output.mkdir(parents=True, exist_ok=False)
            write(output / "pytest-report.json", report)
        return report
    output = Path(options["artifacts"])
    host = launch(options["project"], options["baseline_revision"], output,
                  executable=options["executable"], model=options["model"],
                  timeout=options["timeout_seconds"])
    if (host["returncode"] != 0 or host["state"] != "exited"
            or not host["native_turn_completed"]):
        report = {"workflow_verdict": "INCONCLUSIVE", "findings": [{
            "code": "host_did_not_complete", "verdict": "INCONCLUSIVE"}], "host": host}
        write(output / "pytest-report.json", report)
        return report
    try:
        campaign = discover(options["campaign_parent"], options["project"], host["started_at"])
        if options["retest"]:
            if not options["patch"]:
                raise ValueError("An actual --e2e-patch is required before independent timing")
            observer = Path(options["observer"])
            submission = reference(observer.parent, read(observer)["submission"])
            plan, _ = seal(options["project"], options["baseline_revision"], campaign,
                           options["patch"], output / "independent", submission=submission)
            execute(output / "independent", plan, options["timeout_seconds"])
        report = audit(campaign, options["observer"], host_reply=output / "final-reply.txt")
    except EvidenceViolation:
        report = {"workflow_verdict": "FAIL", "findings": [{
            "code": "independent_patch_identity_violation", "verdict": "FAIL"}]}
    except (OSError, ValueError, KeyError, CalledProcessError) as error:
        report = {"workflow_verdict": "INCONCLUSIVE", "findings": [{
            "code": "collection_or_independent_retest_incomplete", "verdict": "INCONCLUSIVE",
            "error_type": type(error).__name__}]}
    write(output / "pytest-report.json", report)
    return report


def test_ordinary_user_optimization(observed):
    # pytest has no INCONCLUSIVE status. Keep it in the JSON receipt and fail the
    # acceptance assertion, rather than silently reporting missing NPU evidence green.
    assert observed["workflow_verdict"] == "PASS", observed


def test_completion_required_no_observer_assistance(observed):
    assert observed.get("completion_mode") == "unassisted", observed
