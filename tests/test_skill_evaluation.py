import importlib.util
import time
from pathlib import Path

import pytest

from inferrsi.harness.skill_evaluation import (
    CodexClient,
    export_bundle,
    run_trial,
    summarize,
    task_verdict,
    toml_value,
    trace_metrics,
)
from inferrsi.knowledge_operations import KnowledgeReader

ROOT = Path(__file__).resolve().parents[1]


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_codex_adapter_uses_ephemeral_isolated_real_command(tmp_path):
    command = CodexClient("test-model", "xhigh", 10).command(
        tmp_path / "workspace", tmp_path / "answer.json", tmp_path / "schema.json", "Task"
    )
    assert command[:2] == ("codex", "exec")
    assert "--ephemeral" in command and "--ignore-user-config" in command
    assert 'approval_policy="never"' in command
    assert 'sandbox_mode="danger-full-access"' in command
    assert 'web_search="disabled"' in command
    assert "--sandbox" not in command


def test_trace_retains_unknown_usage_and_errors(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text('{"type":"turn.failed","error":{"message":"limited"}}\n')
    trace = trace_metrics(path)
    assert trace["usage"] is None
    assert trace["completed_turns"] == 0 and trace["errors"]


@pytest.mark.parametrize("status", ["timeout", "error", "cancelled", "failed"])
def test_incomplete_execution_never_passes(status):
    assert (
        task_verdict({"status": status}, {"completed_turns": 1, "errors": []}, {}, {"passed": True})
        == "INCONCLUSIVE"
    )


def test_completed_wrong_or_missing_answer_fails():
    trace = {"completed_turns": 1, "errors": []}
    assert task_verdict({"status": "completed"}, trace, {}, {"passed": False}) == "FAIL"
    assert task_verdict({"status": "completed"}, trace, None, None) == "FAIL"
    assert task_verdict({"status": "completed"}, trace, {}, None) == "INCONCLUSIVE"


def test_export_preserves_declared_cross_skill_resource(tmp_path):
    reader = KnowledgeReader(skill_root=ROOT / "src/inferrsi/data/skill_library")
    view = export_bundle(reader, "checkout:inference-benchmark-design", tmp_path)
    assert view["revision"].startswith("sha256:")
    assert (tmp_path / view["entrypoint"]).is_file()
    for path in view["dependencies"]:
        assert (tmp_path / path).is_file()
    assert not list(tmp_path.rglob(".git"))
    assert not list(tmp_path.rglob("verify.py"))


def test_pairs_preserve_regressions_and_missing_metrics():
    base = {
        "task_id": "one",
        "repeat": 1,
        "elapsed_seconds": 2,
        "observations": {"usage": None},
        "condition": "N",
        "verdict": "PASS",
    }
    result = summarize([base, {**base, "condition": "E-benchmark", "verdict": "FAIL"}])
    assert result["pairs"][0]["regression"] is True
    assert result["conditions"]["N"]["input_tokens"] is None
    assert result["conditions"]["N"]["cost"] is None


def test_toml_literals_do_not_shell_interpolate():
    assert toml_value({"key": [False, "a\\b"]}) == '{"key"=[false,"a\\\\b"]}'


def test_frozen_verifier_rejects_blank_and_fabricated_claims():
    verifier = load_tool("skill_eval_verifier")
    pilot = load_tool("skill_eval_pilot")
    tasks = pilot.fixtures()
    assert len(tasks) == 6
    for task in tasks:
        assert not verifier.verify(task, {})["passed"]
        verdict, gain, findings, scope = verifier.expected(task)
        answer = {
            "report_verdict": verdict,
            "latency_reduction_pct": gain,
            "findings": sorted(findings),
            "claim_scope": scope,
            "evidence": task["evidence_keys"],
            "reason": "Fixture oracle check",
        }
        assert verifier.verify(task, answer)["passed"]
        assert not verifier.verify(task, {**answer, "claim_scope": "production"})["passed"]
        assert not verifier.verify(task, {**answer, "evidence": ["invented.log"]})["passed"]
        if verdict != "PASS":
            assert not verifier.verify(task, {**answer, "report_verdict": "PASS"})["passed"]


def test_task_inputs_never_embed_oracle_fields():
    for task in load_tool("skill_eval_pilot").fixtures():
        assert "expected" not in task and "report_verdict" not in task
        assert task["provenance"].startswith("Historical latency slices")


def test_recovery_keeps_interrupted_attempt_without_automatic_retry(tmp_path):
    pilot = load_tool("skill_eval_pilot")
    entry = {"task_id": "task", "condition": "N", "repeat": 1}
    directory = tmp_path / "results/task-N-1"
    directory.mkdir(parents=True)
    trials = pilot.recover_attempts(tmp_path, [entry])
    assert trials[0]["execution_state"] == "interrupted"
    assert trials[0]["verdict"] == "INCONCLUSIVE"
    assert pilot.recover_attempts(tmp_path, [entry]) == trials
    assert summarize(trials)["conditions"]["N"]["elapsed_seconds"] is None


def test_verifier_rejects_malformed_generated_answers():
    verifier = load_tool("skill_eval_verifier")
    task = load_tool("skill_eval_pilot").fixtures()[0]
    for answer in (
        [],
        {"findings": [[1]], "evidence": ["contract"]},
        {"findings": [], "evidence": [None]},
    ):
        assert not verifier.verify(task, answer)["passed"]


def test_final_fixture_protocol_is_explicit_and_uses_distinct_latency_inputs():
    pilot = load_tool("skill_eval_pilot")
    original, final = pilot.fixtures(), pilot.fixtures(True)
    assert original[0]["baseline"]["latencies_ms"] != final[0]["baseline"]["latencies_ms"]
    for task in final:
        assert set(task["contract"]["verdict_definitions"]) == {"PASS", "FAIL", "INCONCLUSIVE"}
        assert "Use null" in task["contract"]["output_field_semantics"]["latency_reduction_pct"]


def test_expired_real_executor_deadline_records_missing_events(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    result = run_trial(
        CodexClient("never-called", "xhigh", 1),
        {"id": "expired", "split": "development"},
        "N",
        1,
        workspace,
        tmp_path / "trial",
        tmp_path / "schema.json",
        tmp_path / "verifier.py",
        "Never executed",
        time.monotonic() - 1,
    )
    assert result["execution_state"] == "timeout"
    assert result["verdict"] == "INCONCLUSIVE"
    assert result["observations"]["usage"] is None
