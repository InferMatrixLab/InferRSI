import copy
import json
from pathlib import Path

import pytest

from tools.skill_eval_verifier import verify

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/skill_eval_grading.json").read_text(encoding="utf-8")
)
CASES = FIXTURE["cases"]


def task_with(changes):
    task = copy.deepcopy(FIXTURE["task"])
    for path, value in changes.items():
        target = task
        *parents, key = path.split(".")
        for parent in parents:
            target = target[parent]
        target[key] = copy.deepcopy(value)
    return task


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_independent_grading_cases(case):
    result = verify(task_with(case["changes"]), case["answer"])
    assert result == {
        "passed": True,
        "assertions": dict.fromkeys(
            ("report_verdict", "claim_scope", "findings", "reduction", "evidence", "explanation"),
            True,
        ),
    }


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
@pytest.mark.parametrize(
    "dimension", ["report_verdict", "claim_scope", "findings", "latency_reduction_pct", "evidence"]
)
def test_one_wrong_dimension_cannot_pass(case, dimension):
    answer = copy.deepcopy(case["answer"])
    answer[dimension] = {
        "report_verdict": "FAIL" if answer["report_verdict"] == "PASS" else "PASS",
        "claim_scope": "production",
        "findings": answer["findings"] + ["invented_finding"],
        "latency_reduction_pct": 99,
        "evidence": answer["evidence"] + ["invented.log"],
    }[dimension]
    assert not verify(task_with(case["changes"]), answer)["passed"]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_each_required_evidence_key_is_required(case):
    for key in case["answer"]["evidence"]:
        answer = copy.deepcopy(case["answer"])
        answer["evidence"].remove(key)
        assert not verify(task_with(case["changes"]), answer)["passed"], key


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_every_answer_field_is_required_even_when_nullable(case):
    for field in case["answer"]:
        answer = copy.deepcopy(case["answer"])
        del answer[field]
        assert not verify(task_with(case["changes"]), answer)["passed"], field


@pytest.mark.parametrize("answer", [None, [], "answer", 1, True])
def test_nonobject_answers_are_rejected(answer):
    assert not verify(task_with({}), answer)["passed"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("report_verdict", []), ("claim_scope", []), ("findings", "quality_failed"),
        ("findings", [["quality_failed"]]), ("evidence", "contract"),
        ("evidence", [None]), ("latency_reduction_pct", True),
        ("latency_reduction_pct", float("nan")), ("latency_reduction_pct", float("inf")),
        ("latency_reduction_pct", -float("inf")), ("latency_reduction_pct", "20"),
        ("reason", ""), ("reason", " \n\t"), ("reason", ["text"]),
    ],
)
def test_malformed_answer_fields(field, value):
    answer = {**CASES[0]["answer"], field: value}
    assert not verify(task_with({}), answer)["passed"]


@pytest.mark.parametrize(
    "changes,case_id",
    [
        ({"candidate.workload.steps": 4, "evidence_scope": "kernel",
          "candidate.quality": "failed", "candidate.failed_requests": 1}, "workload-mismatch"),
        ({"evidence_scope": "kernel", "candidate.quality": "missing"}, "kernel-only"),
        ({"candidate.quality": "missing", "candidate.failed_requests": 1}, "quality-missing"),
        ({"candidate.quality": "failed", "candidate.failed_requests": 1}, "quality-failed"),
        ({"candidate.failed_requests": 1, "contract.min_reduction_pct": 21}, "failed-requests"),
        ({"mode": "extract", "candidate.workload.steps": 4, "evidence_scope": "kernel",
          "candidate.quality": "failed", "candidate.failed_requests": 1}, "extract"),
    ],
)
def test_rule_precedence_and_extract_bypass(changes, case_id):
    answer = next(case["answer"] for case in CASES if case["id"] == case_id)
    assert verify(task_with(changes), answer)["passed"]


@pytest.mark.parametrize(
    "gain,passed", [(-0.0201, False), (-0.02, True), (0, True), (0.02, True), (0.0201, False)]
)
def test_point_zero_two_percentage_point_tolerance(gain, passed):
    # 以精确的零收益检查边界，避免 20.02 - 20 的浮点表示影响断言。
    task = task_with({
        "candidate.latencies_ms": FIXTURE["task"]["baseline"]["latencies_ms"],
        "contract.min_reduction_pct": 0,
    })
    answer = {**CASES[0]["answer"], "latency_reduction_pct": gain}
    assert verify(task, answer)["passed"] is passed


@pytest.mark.parametrize(
    "changes",
    [
        {"baseline.latencies_ms": []}, {"candidate.latencies_ms": [[]]},
        {"baseline.latencies_ms": [[0]]}, {"baseline.latencies_ms": [[float("nan")]]},
        {"candidate.latencies_ms": [[float("inf")]]},
        {"candidate.latencies_ms": [[100], [200], [float("inf")]]},
    ],
)
@pytest.mark.parametrize("answer", [CASES[0]["answer"], {}])
def test_invalid_task_inputs_are_errors(changes, answer):
    with pytest.raises((ValueError, ZeroDivisionError)):
        verify(task_with(changes), answer)


def test_reason_is_only_a_nonempty_text_check():
    answer = {**CASES[0]["answer"], "reason": "Unrelated text is not semantically judged."}
    assert verify(task_with({}), answer)["passed"]
