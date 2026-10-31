"""Fixed workbench integration with scripted sandbox outputs; never host candidate exec."""

import copy
import json
import time
from pathlib import Path

import pytest

from inferrsi.harness import kv_edit_workbench as workbench
from inferrsi.harness import kv_reclamation as kv
from inferrsi.model import anthropic_edit_agent as edit
from tests.test_anthropic_edit_agent import call, read_task, response, submit, work

BASELINE = b"# visible linear starter\n"
CANDIDATE = "raise AssertionError('must never run on host')\n"
TRACE = {"id": "dev_empty", "split": "development", "events": [], "expected": []}
EXPECTED = {"observations": [], "pending": []}


def suite():
    return workbench.VisibleSuite(json.dumps({
        "schema": "kv-visible-suite-v1", "development": [TRACE], "benchmark_events": [],
        "benchmark_expected": EXPECTED, "min_improvement_pct": 0,
    }).encode())


def stage(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "candidate.py").write_bytes(BASELINE)
    (root / "task.json").write_text('{"request":"optimize"}')
    plan = edit.EditPlan(edit.freeze_files(root, ["task.json", "candidate.py"]),
        edit.EditLimits(65536, 4096, 8, 8, 4, 2, 600), ("dev_empty",),
        "elapsed_seconds", "seconds", "minimize", "b" * 64)
    return root, plan


def fake_sandbox(source, payload, output, deadline):
    assert type(source) is bytes and deadline > time.monotonic()
    assert set(payload) == {"mode", "events"}  # Never expected answers or hidden data.
    output.mkdir(parents=True)
    return {"status": "completed", "elapsed_seconds": 2.0 if source == BASELINE else 1.0,
            "metric": None, "metric_error": None}, copy.deepcopy(EXPECTED)


def test_scripted_edit_check_abba_rewrite_submit_hidden_grade(tmp_path, monkeypatch):
    root, plan = stage(tmp_path)
    monkeypatch.setattr(kv, "invoke", fake_sandbox)
    bench = workbench.VisibleWorkbench(plan, suite(), BASELINE, tmp_path / "private")
    scripts = [read_task(), work(CANDIDATE, "1"), work(CANDIDATE + "# final\n", "2"), submit()]
    payloads, traces = [], []
    def send(payload, spec, remaining):
        payloads.append(copy.deepcopy(payload))
        return scripts[len(payloads) - 1]
    spec = {"kind": edit.KIND, "provider": "yibuapi", "endpoint": edit.provider.ENDPOINT,
            "api_version": "2023-06-01", "max_requests": 8, "max_output_tokens": 4096,
            "max_request_bytes": 1048576, "max_read_bytes": 65536, "max_tool_calls": 24}
    answer = edit.run_edit_agent(root, plan, "Optimize", "claude-opus-5-5", spec,
        time.monotonic() + 600, traces.append, arm="A2",
        slots=edit.RequestSlots("c" * 64, {"A2": 8, "A3": 8}, 10170000, 162720000,
                                execution_id="offline-1"),
        authorize=lambda *_: True, send=send, visible_checks=bench.visible_checks,
        visible_benchmark=bench.visible_benchmark, retain_revision=bench.retain_revision,
        input_token_ceiling=1000000)
    assert answer["artifact_source"] == CANDIDATE + "# final\n"
    assert len(list((tmp_path / "private/revisions").glob("*/candidate.py"))) == 3
    runs = sorted((tmp_path / "private").glob("benchmark-*/runs/*"))
    assert len(runs) == 2
    for run in runs:
        events = [json.loads(line) for line in (run / "events.jsonl").read_text().splitlines()]
        assert [e["side"] for e in events if e["phase"] == "measurement"] == [
            "baseline", "candidate", "candidate", "baseline"]
        evaluation = json.loads((run / "evaluation.json").read_text())
        assert evaluation["source_integrity"]["verified"]
        assert evaluation["improvement_pct"] == 50
    # Freeze actual returned bytes before the separate hidden grader; changing the
    # live actor path afterward must neither change grading input nor cause a retry.
    (root / "candidate.py").write_text("# later unrelated mutation\n")
    hidden = [{**TRACE, "split": "grader", "id": "hidden-id-not-for-actor"}]
    result = workbench.grade_final(answer["artifact_source"].encode(), answer["sha256"], hidden,
                                   tmp_path / "grading", time.monotonic() + 30)
    assert result["verdict"] == "PASS"
    assert "hidden-id-not-for-actor" not in edit.provider.canonical(payloads)
    assert "private" not in edit.provider.canonical(payloads)


def test_benchmark_validates_entire_output_before_accepting_host_metric(tmp_path, monkeypatch):
    _, plan = stage(tmp_path)
    def bad(source, payload, output, deadline):
        record, _ = fake_sandbox(source, payload, output, deadline)
        return record, {"observations": [], "pending": [], "fake_latency": 0.00001}
    monkeypatch.setattr(kv, "invoke", bad)
    bench = workbench.VisibleWorkbench(plan, suite(), BASELINE, tmp_path / "private")
    result = bench.visible_benchmark(CANDIDATE.encode(), time.monotonic() + 30)
    assert result["verdict"] == "INCONCLUSIVE"
    assert result["baseline_values"] == [] and result["candidate_values"] == []


def test_same_absolute_deadline_reaches_every_sandbox_call(tmp_path, monkeypatch):
    _, plan = stage(tmp_path)
    seen = []
    def invoke(source, payload, output, deadline):
        seen.append(deadline)
        return fake_sandbox(source, payload, output, deadline)
    monkeypatch.setattr(kv, "invoke", invoke)
    bench = workbench.VisibleWorkbench(plan, suite(), BASELINE, tmp_path / "private")
    deadline = time.monotonic() + 30
    bench.visible_checks(CANDIDATE.encode(), deadline)
    bench.visible_benchmark(CANDIDATE.encode(), deadline)
    assert len(seen) == 6 and all(value <= deadline for value in seen)


def test_unavailable_sandbox_is_inconclusive_without_fallback(tmp_path, monkeypatch):
    _, plan = stage(tmp_path)
    def unavailable(*_):
        raise kv.SandboxUnavailable("local permission denied")
    monkeypatch.setattr(kv, "invoke", unavailable)
    bench = workbench.VisibleWorkbench(plan, suite(), BASELINE, tmp_path / "private")
    for callback in (bench.visible_checks, bench.visible_benchmark):
        result = callback(CANDIDATE.encode(), time.monotonic() + 30)
        assert result["verdict"] == "INCONCLUSIVE"
        assert result["reason"] == "sandbox_unavailable"
        assert "permission" not in json.dumps(result)


def test_hidden_data_never_accepted_as_visible_suite():
    value = suite().read()
    value["development"][0]["split"] = "grader"
    with pytest.raises(ValueError):
        workbench.VisibleSuite(json.dumps(value).encode())


def test_hidden_grade_rejects_wrong_final_hash_before_execution(tmp_path, monkeypatch):
    monkeypatch.setattr(kv, "invoke", lambda *_: pytest.fail("must not execute"))
    with pytest.raises(ValueError, match="exact immutable"):
        workbench.grade_final(BASELINE, "a" * 64, [], tmp_path, time.monotonic() + 1)


def test_retention_is_exclusive_and_exact(tmp_path):
    _, plan = stage(tmp_path)
    bench = workbench.VisibleWorkbench(plan, suite(), BASELINE, tmp_path / "private")
    metadata = {"revision": 0, "sha256": edit.digest(BASELINE)}
    assert bench.retain_revision(BASELINE, metadata, time.monotonic() + 30)
    with pytest.raises(FileExistsError):
        bench.retain_revision(BASELINE, metadata, time.monotonic() + 30)
    with pytest.raises(ValueError):
        bench.retain_revision(BASELINE, {"revision": 1, "sha256": "a" * 64},
                              time.monotonic() + 30)


def test_does_not_call_candidate_import_or_trusted_observation_helpers():
    source = Path(workbench.__file__).read_text()
    assert "exec(" not in source and "importlib" not in source and "observe_trusted" not in source


def test_malformed_tool_measurement_arguments_fail_before_callback(tmp_path, monkeypatch):
    # Existing protocol strict tool validation is reused by the integration.
    from tests.test_anthropic_edit_agent import run
    root, plan = stage(tmp_path)
    spec = {"kind": edit.KIND, "provider": "yibuapi", "endpoint": edit.provider.ENDPOINT,
            "api_version": "2023-06-01", "max_requests": 8, "max_output_tokens": 4096,
            "max_request_bytes": 1048576, "max_read_bytes": 65536, "max_tool_calls": 24}
    with pytest.raises(edit.provider.AgentError, match="unsupported_tool"):
        run((root, plan, spec), [read_task(), response(call("run_visible_benchmark", {
            "command": "untrusted command", "workload": "hidden"}))])
