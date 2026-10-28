"""Offline advisory controls: no provider access, GitHub requests or approval."""
import copy
import io
import zipfile

import pytest

from inferrsi.infra.artifacts import sha256, write_json
from tests.fixtures.skill_eval_compare_support import FixedOutputClient
from tests.fixtures.skill_eval_pr_support import SimulatedGitHub, approval, setup
from tools import skill_eval_pr as integration


def evaluated(tmp_path, modes=None, ids=("one",)):
    repo, mapping, identity = setup(tmp_path, mode="addition", ids=ids)
    configuration = integration.compare.read_json(mapping)
    configuration["skills"][0]["paths"] = ["library"]
    write_json(mapping, configuration)
    output = tmp_path / "execution"
    plan = integration.prepare(repo, mapping, identity, output)
    client = FixedOutputClient(tmp_path, modes)
    integration.execute(output, approval(plan), client=client)
    return plan, integration.reports(output), output, client


@pytest.mark.parametrize("modes,expected", [
    ({}, "covered evidence supports proceeding to independent review"),
    ({("one", "baseline"): "incorrect"},
     "covered evidence supports proceeding to independent review"),
    ({("one", "candidate"): "incorrect"}, "address observed regression"),
    ({("one", "baseline"): "incorrect", ("one", "candidate"): "incorrect"},
     "obtain missing evidence"),
    ({("one", "candidate"): "invalid_json"}, "obtain missing evidence"),
])
def test_real_offline_pairs_drive_advisory(tmp_path, modes, expected):
    plan, results, _, _ = evaluated(tmp_path, modes)
    guidance = integration.review_guidance(plan, results, evidence_state="available")
    assert guidance["disposition"] == expected
    assert len(guidance["observations"]) == 1
    body = integration.summary(plan, results, "https://example.invalid/evidence", 10, 1)
    assert expected in body and "not incremental benefit" in body
    assert "No approval or merge authorization" in body


def test_regression_is_not_cancelled_by_fix_or_hidden_by_gaps(tmp_path):
    plan, results, _, _ = evaluated(tmp_path, {
        ("fix", "baseline"): "incorrect", ("regression", "candidate"): "incorrect",
        ("error", "candidate"): "invalid_json"}, ids=("fix", "regression", "error"))
    plan["coverage"].append({"path": "unmapped.json", "coverage": "uncovered"})
    guidance = integration.review_guidance(plan, results, evidence_state="available")
    assert guidance["disposition"] == "address observed regression"
    assert {p["outcome"] for p in guidance["observations"]} == {
        "fix", "regression", "inconclusive"}
    assert any("Uncovered" in reason for reason in guidance["reasons"])


@pytest.mark.parametrize("state", ["expired", "missing", "invalid", "planned / unexecuted"])
def test_unavailable_evidence_cannot_support_positive_guidance(tmp_path, state):
    plan, results, _, _ = evaluated(tmp_path)
    guidance = integration.review_guidance(plan, results, evidence_state=state)
    assert guidance["disposition"] == "obtain missing evidence"
    assert guidance["observations"] == []


@pytest.mark.parametrize("mutation", ["head", "base", "plan", "exam", "missing_pair",
                                     "no_report", "duplicate", "status", "gap", "no_cases"])
def test_stale_incomplete_and_uncovered_evidence_is_not_positive(tmp_path, mutation):
    plan, results, _, _ = evaluated(tmp_path)
    if mutation in ("head", "base"):
        plan[mutation] = "f" * 40
    elif mutation in ("plan", "exam"):
        results[0]["plan_sha256" if mutation == "plan" else "exam"] = "changed"
    elif mutation == "missing_pair":
        results[0]["pairs"] = []  # Even unchanged positive aggregate counts are not enough.
    elif mutation == "no_report":
        results = []
    elif mutation == "duplicate":
        results.append(copy.deepcopy(results[0]))
    elif mutation == "status":
        results[0]["status"]["execution_state"] = "not_completed"
    elif mutation == "gap":
        plan["coverage"].append({"path": "unknown", "coverage": "unsupported"})
    elif mutation == "no_cases":
        plan["comparisons"] = []
    assert integration.review_guidance(plan, results, evidence_state="available")[
        "disposition"] == "obtain missing evidence"


def test_prepared_only_and_missing_artifact_publish_insufficient_evidence(tmp_path):
    repo, mapping, identity = setup(tmp_path, mode="addition", ids=("one",))
    output = tmp_path / "plan"
    plan = integration.prepare(repo, mapping, identity, output)
    body = integration.summary(plan, [], "https://example.invalid/plan", 10, 1)
    assert "PLANNED" in body and "obtain missing evidence" in body
    api = SimulatedGitHub(plan)
    api.artifact["name"] = "unrelated"
    integration.publish_retained(api, output, 10, 11, 1)
    assert "artifacts are missing" in api.comments[0]["body"]
    assert "obtain missing evidence" in api.comments[0]["body"]
    assert not (output / "execution-claim.json").exists()


def test_publication_retry_preserves_negative_guidance_without_calls(tmp_path):
    plan, _, output, client = evaluated(tmp_path, {("one", "candidate"): "incorrect"})
    api = SimulatedGitHub(plan, integration.result_archive(output).read_bytes())
    before = len(client.calls)
    for writer in (11, 12):
        integration.publish_retained(api, output, 10, writer, 1)
    assert len(api.comments) == 1 and len(client.calls) == before
    assert "address observed regression" in api.comments[0]["body"]


def test_import_retry_cannot_fill_missing_evidence_from_previous_download(tmp_path):
    plan, _, output, _ = evaluated(tmp_path)
    retained = integration.result_archive(output).read_bytes()
    integration.import_results(retained, output)
    assert integration.review_guidance(plan, integration.reports(output),
        evidence_state="available")["disposition"].startswith("covered evidence")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w"):
        pass
    integration.import_results(buffer.getvalue(), output)
    guidance = integration.review_guidance(plan, integration.reports(output),
                                           evidence_state="available")
    assert guidance["disposition"] == "obtain missing evidence"
    assert guidance["observations"][0]["outcome"] == "missing_pair"


@pytest.mark.parametrize("status", [None, [], "completed", 1, {},
                                    {"execution_state": None}, {"execution_state": []}])
def test_invalid_status_shape_cannot_crash_or_support_positive_guidance(tmp_path, status):
    plan, _, output, client = evaluated(tmp_path)
    path = output / "selected/results/status.json"
    write_json(path, status)
    write_json(path.with_name("status.receipt.json"), {"result_sha256": sha256(path)})
    api = SimulatedGitHub(plan, integration.result_archive(output).read_bytes())
    before = len(client.calls)
    integration.publish_retained(api, output, 10, 11, 1)
    body = api.comments[0]["body"]
    assert "obtain missing evidence" in body
    assert "artifacts are invalid" in body
    assert len(client.calls) == before


@pytest.mark.parametrize("field,value", [("observations", None), ("observations", []),
                                         ("checks", None), ("checks", []),
                                         ("evidence_sha256", None)])
def test_malformed_nested_trial_evidence_remains_nonpositive(tmp_path, field, value):
    plan, _, output, _ = evaluated(tmp_path)
    path = output / "selected/results/one-candidate-1/result.json"
    record = integration.compare.read_json(path)
    record[field] = value
    write_json(path, record)
    write_json(path.with_name("receipt.json"), {"result_sha256": sha256(path)})
    api = SimulatedGitHub(plan, integration.result_archive(output).read_bytes())
    integration.publish_retained(api, output, 10, 11, 1)
    assert "obtain missing evidence" in api.comments[0]["body"]


def test_advisory_reasons_are_deduplicated_and_pairs_are_collapsed(tmp_path):
    plan, results, _, _ = evaluated(tmp_path, {
        ("one", "candidate"): "invalid_json", ("two", "candidate"): "invalid_json"},
        ids=("one", "two"))
    guidance = integration.review_guidance(plan, results, evidence_state="available")
    assert len(guidance["reasons"]) == len(set(guidance["reasons"]))
    body = integration.summary(plan, results, "https://example.invalid/evidence", 10, 1)
    assert body.index("### Advisory:") < body.index("RETAINED RESULTS")
    assert body.index("<details>") < body.index("Per-case outcomes")
