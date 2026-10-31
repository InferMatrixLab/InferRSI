"""Offline evidence projection tests; no provider calls or artifact execution."""

import copy
import json
import os
import subprocess
import sys
from unittest.mock import patch

import pytest

from tools import skill_eval_artifact_guidance as advice
from tools import skill_eval_cloud_replay as replay


def pair(before=None, after=None):
    before = {"stream_error": False, "length": True} if before is None else before
    after = {"stream_error": True, "length": True} if after is None else after

    def trial(values, role):
        return {
            "trusted": True,
            "checks": {"passed": all(values.values()), "assertions": values},
            "evidence_ref": "report.json#/pairs/0/" + role,
        }

    return {
        "case": "parser",
        "capture_state": "artifact_verification_deferred",
        "baseline": trial(before, "baseline"),
        "candidate": trial(after, "candidate"),
    }


def test_per_check_fix_is_not_skill_causality_or_merge_acceptance():
    result = advice.guidance([pair()])
    assert result["disposition"] == "review_observed_improvement"
    assert result["observations"][0]["changes"]["improved"] == ["stream_error"]
    assert result["automatic_acceptance"] is False
    assert "causality" in result["limitations"][0]


def test_mixed_improvement_never_cancels_regression():
    result = advice.guidance(
        [pair({"stream_error": False, "length": True}, {"stream_error": True, "length": False})]
    )
    assert result["disposition"] == "address_regression"
    assert result["next_steps"][0]["check"] == "length"
    assert result["next_steps"][0]["evidence_refs"] == ["report.json#/pairs/0/candidate"]
    assert "not the cause" in result["next_steps"][0]["action"]


def test_tie_suggests_discriminating_evidence_not_another_model_call():
    result = advice.guidance([pair({"length": True}, {"length": True})])
    assert result["disposition"] == "no_observed_check_change"
    assert "no improvement" in result["headline"]
    assert "discriminating task" in result["next_steps"][0]["action"]
    assert result["next_steps"][0]["requires_new_execution"] is False
    assert advice.safe("artifact_verification_deferred") in advice.markdown(result)


def test_unchanged_failure_is_not_tie_success():
    result = advice.guidance([pair({"stream_error": False}, {"stream_error": False})])
    assert result["disposition"] == "address_remaining_failure"
    assert result["observations"][0]["changes"]["still_failing"] == ["stream_error"]


@pytest.mark.parametrize(
    "change",
    [
        None,
        {},
        {"passed": True, "assertions": {}},
        {"passed": True, "assertions": {"x": 1}},
        {"passed": True, "assertions": {"x": False}},
    ],
)
def test_missing_malformed_checks_are_not_pass(change):
    item = pair()
    item["candidate"]["checks"] = change
    assert advice.guidance([item])["disposition"] == "obtain_valid_evidence"


def test_untrusted_claim_and_different_check_sets_cannot_be_complete():
    item = pair()
    item["candidate"]["trusted"] = False
    assert advice.guidance([item])["missing_evidence"]
    result = advice.guidance([pair({"one": True}, {"two": True})])
    assert result["disposition"] == "obtain_valid_evidence"
    assert result["observations"][0]["changes"]["uncompared"] == ["one", "two"]
    assert advice.guidance([])["disposition"] == "obtain_valid_evidence"


def test_replay_requires_complete_qualified_receipt():
    receipt = {
        "verdict": "INCONCLUSIVE",
        "qualification": {"verdict": "PASS"},
        "artifacts": [
            {"arm": role, "result": {"passed": True, "assertions": {"x": True}}}
            for role in ("baseline", "candidate")
        ],
    }
    assert advice.replay(receipt)["disposition"] == "obtain_valid_evidence"
    receipt["verdict"] = "PASS"
    assert advice.replay(receipt)["disposition"] == "no_observed_check_change"


def test_projection_does_not_mutate_grades_or_capture_and_escapes_markdown():
    item = pair()
    item["case"] = "<script>|`case\n![x](https://example.invalid/pixel)"
    original = copy.deepcopy(item)
    result = advice.guidance([item])
    rendered = advice.markdown(result)
    assert item == original
    assert "<script>" not in rendered and "&lt;script&gt;" in rendered
    assert "![" not in rendered and "](https:" not in rendered


def test_existing_replay_cli_writes_json_and_readable_guidance(tmp_path):
    receipt = {
        "verdict": "PASS",
        "qualification": {"verdict": "PASS"},
        "artifacts": [
            {"arm": role, "result": {"passed": True, "assertions": {"x": True}}}
            for role in ("baseline", "candidate")
        ],
    }
    out = tmp_path / "receipt"
    with (
        patch.object(
            sys,
            "argv",
            [
                "replay",
                "--output",
                str(out),
                "--evidence-commit",
                "a" * 40,
                "--bundle-sha256",
                "b" * 64,
                "--revision",
                "c" * 40,
                "--runner-image",
                "offline",
            ],
        ),
        patch.object(replay, "fetch_bundle", return_value=b"unused"),
        patch.object(replay, "replay", return_value=receipt),
    ):
        assert replay.main() == 0
    assert (
        json.loads((out / "replay.json").read_text())["guidance"]["automatic_acceptance"] is False
    )
    assert "What to do next" in (out / "replay.md").read_text()


def test_existing_compare_cli_surface_still_available():
    completed = subprocess.run(
        [sys.executable, "-m", "tools.skill_eval_compare", "--help"],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )
    assert "report" in completed.stdout


def test_comparison_preserves_deferred_capture_and_uses_independent_checks():
    from tools import skill_eval_compare as compare

    checks = {"passed": True, "assertions": {"stream_error": True}}
    result = {
        "pairs": [
            {
                "case_id": "parser",
                "repeat": 1,
                "outcome": "inconclusive",
                **{
                    role: {
                        "verdict": "INCONCLUSIVE",
                        "checks": None,
                        "artifact_checks": checks,
                        "artifact_verdict": "PASS",
                        "grader_trust": "reverified",
                    }
                    for role in compare.ROLES
                },
            }
        ]
    }
    before = copy.deepcopy(result)
    projected = advice.comparison(result)
    assert projected["disposition"] == "no_observed_check_change"
    assert projected["observations"][0]["capture_state"] == "inconclusive"
    assert result == before


def test_existing_report_cli_integrates_missing_evidence_first_screen(tmp_path):
    from tests.test_skill_eval_generation import prepared
    from tools import skill_eval_compare as compare

    _, output, _ = prepared(tmp_path)
    result = compare.report(output)
    assert result["guidance"]["disposition"] == "obtain_valid_evidence"
    rendered = (output / "report.md").read_text()
    assert rendered.index("What to do next") < rendered.index("Frozen plan:")
    assert "missing_or_unverified" in json.dumps(result["guidance"])
