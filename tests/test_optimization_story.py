"""The optimization story keeps captured knowledge exact and flags narrative conflicts."""

import copy
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from inferrsi.cli import main
from inferrsi.harness.campaign_records import create_campaign, record_candidate, record_decision
from inferrsi.harness.knowledge_capture import capture_context, verify_capture
from inferrsi.harness.optimization_log import LogError, parse_optimization_log, record_log
from inferrsi.knowledge_operations import KnowledgeReader
from inferrsi.observability.dashboard import write_dashboard
from inferrsi.observability.dashboard_data import load_dashboard


class FakeReader:
    """Mimics KnowledgeReader.collect's context envelope."""

    def __init__(self, contexts, items=None, omissions=None):
        self.contexts, self.items = contexts, items
        self.context_omissions = omissions or []

    def collect(self, query="", **options):
        return {"items": self.items or [{"ref": c["ref"], "revision": c["revision"],
                                          "title": c["ref"], "kind": "knowledge"}
                                         for c in self.contexts],
                "omissions": [], "contexts": copy.deepcopy(self.contexts),
                "context_omissions": self.context_omissions,
                "context_bytes": sum(c["content_bytes"] for c in self.contexts),
                "context_budget": {"max_bytes": options["context_bytes"]},
                "selection": {"cue": options.get("relevance")}}


def context(ref, text):
    return {"ref": ref, "revision": "sha256:" + "1" * 64,
            "content_bytes": len(text.encode()),
            "resources": [{"path": f"skills/{ref.split(':')[1]}/SKILL.md", "role": "core",
                           "sha256": hashlib.sha256(text.encode()).hexdigest(),
                           "content": text, "locator": "whole-resource"}],
            "omissions": [{"path": "skills/x/metadata.json", "reason": "not_context_resource"}],
            "sources": []}


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def make_run(root: Path, name: str, gain: float, quality: str = "completed") -> None:
    directory = root / "runs" / name
    write_json(directory / "run.lock.json", {"workload_id": "w", "scenario": "http"})
    write_json(directory / "status.json", {"state": "completed"})
    write_json(directory / "evaluation.json", {
        "verdict": "PASS", "metric_key": "throughput", "metric_unit": "tokens/s",
        "direction": "maximize", "improvement_pct": gain,
        "baseline": {"median": 100, "range_pct_of_median": 0.5},
        "candidate": {"median": 100 + gain, "range_pct_of_median": 0.5},
        "source_integrity": {"verified": True}})
    write_json(directory / "validation" / "execution.json",
               {"status": quality, "returncode": 0 if quality == "completed" else 1})


def campaign(tmp_path):
    create_campaign(tmp_path, "camp", noise=1.5)
    _, digest = capture_context(tmp_path, context_id="r1", reader=FakeReader([
        context("package:graphs", "Capture repeated decode launches.\n"),
        context("package:kv", "Tune the KV block size.\n")]),
        relevance="decode launch", context_bytes=4096)
    make_run(tmp_path, "run-a", 4.0)
    make_run(tmp_path, "run-b", 3.0, quality="failed")
    record_candidate(tmp_path, candidate_id="a", run_id="run-a", round_number=1, title="A")
    record_candidate(tmp_path, candidate_id="b", run_id="run-b", round_number=2, title="B")
    record_decision(tmp_path, candidate_id="a", round_number=1, outcome="adopted")
    return digest


def log_document(digest):
    return {
        "schema_version": 2, "reviewed_by_caller": True, "campaign_id": "camp",
        "goal": {"statement": "Raise decode throughput", "metric": "tokens/s"},
        "knowledge": [{"context_id": "r1", "sha256": digest, "stage": "diagnosis",
                       "purpose": "Find launch overhead fixes", "used_refs": ["package:graphs"],
                       "takeaways": ["Graphs remove repeated launches"],
                       "rejected_refs": [{"ref": "package:kv", "reason": "Not the bottleneck"}]}],
        "search_space": {"state": "complete", "missing_reason": "", "dimensions": [
            {"id": "launch", "name": "Launch", "options": [
                {"id": "graph", "description": "CUDA graph", "status": "tried",
                 "reason": "Profile shows launches", "source_refs": ["package:graphs"]},
                {"id": "fuse", "description": "Fusion", "status": "untried",
                 "reason": "Out of budget"}]},
            {"id": "precision", "name": "Precision", "options": [
                {"id": "fp8", "description": "FP8 KV", "status": "tried",
                 "reason": "Memory bound"}]}]},
        "iterations": [
            {"round": 1, "hypothesis": "Launches dominate", "rationale": "Profile",
             "knowledge_refs": ["package:graphs"], "context_ids": ["r1"],
             "candidates": [{"candidate_id": "a", "option_ids": ["launch.graph"],
                             "why": "Direct fix"}],
             "decision": {"outcome": "adopted", "candidate_id": "a", "reason": "+4%"}},
            {"round": 2, "hypothesis": "KV memory", "rationale": "Next bottleneck",
             "knowledge_refs": [],
             "candidates": [{"candidate_id": "b", "option_ids": ["precision.fp8"],
                             "why": "Halve KV bytes"}],
             "decision": {"outcome": "rejected", "candidate_id": "b",
                          "reason": "Quality failed"}}],
        "summary": {"state": "complete", "missing_reason": "",
                    "successes": [{"text": "Graphs helped", "evidence": ["candidate:a"]}],
                    "failures": [{"text": "FP8 broke quality", "evidence": ["candidate:b"],
                                  "cause_stage": "search"}],
                    "lessons": ["Gate precision changes on quality first"],
                    "limitations": ["One workload"]}}


def write_log(tmp_path, document):
    path = tmp_path / "log-input.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return record_log(tmp_path, path)


def test_capture_keeps_exact_context_and_detects_tampering(tmp_path):
    create_campaign(tmp_path, "camp")
    path, digest = capture_context(tmp_path, context_id="r1",
                                   reader=FakeReader([context("package:g", "Body </script>\n")]),
                                   context_bytes=4096)
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == digest
    document, state = verify_capture(raw)
    assert state == "verified"
    assert "--- begin context package:g" in document["assembled_text"]
    assert "Body </script>" in document["assembled_text"]
    tampered = json.loads(raw)
    tampered["contexts"][0]["resources"][0]["content"] = "Edited\n"
    assert verify_capture(json.dumps(tampered).encode())[1] == "resource_hash_mismatch"
    tampered = json.loads(raw)
    tampered["assembled_text"] += "extra"
    assert verify_capture(json.dumps(tampered).encode())[1] == "assembly_mismatch"
    with pytest.raises(ValueError, match="already exists"):
        capture_context(tmp_path, context_id="r1", reader=FakeReader([]), context_bytes=1)


def test_capture_matches_real_collect_output(tmp_path):
    create_campaign(tmp_path, "camp")
    path, _ = capture_context(tmp_path, context_id="real", reader=KnowledgeReader(),
                              relevance="kv cache block size", context_bytes=40000, limit=2)
    document, state = verify_capture(path.read_bytes())
    assert state == "verified"
    assert document["contexts"], "the packaged library should supply a context"
    assert document["request"]["sources"] == ["package"]


def test_story_joins_log_with_captures_and_runs_without_conflicts(tmp_path):
    digest = campaign(tmp_path)
    write_log(tmp_path, log_document(digest))
    story = load_dashboard(tmp_path)["story"]
    assert story["state"] == "present"
    assert story["checks"] == []
    retrieval = story["retrievals"][0]
    assert retrieval["state"] == "verified"
    assert "Capture repeated decode launches." in retrieval["assembled_text"]
    first = story["iterations"][0]["candidates"][0]["measured"]
    assert first["outcome"] == "improved" and first["improvement_pct"] == 4.0
    options = {o["qualified_id"]: o for d in story["search_space"]["dimensions"]
               for o in d["options"]}
    assert options["launch.graph"]["uses"][0]["candidate_id"] == "a"
    assert options["launch.fuse"]["uses"] == []


def test_story_keeps_candidate_but_flags_its_missing_run(tmp_path):
    digest = campaign(tmp_path)
    write_log(tmp_path, log_document(digest))
    run = tmp_path / "runs" / "run-b"
    unavailable = tmp_path / "unavailable-run-b"
    assert run.resolve().is_relative_to(tmp_path.resolve())
    assert unavailable.resolve().is_relative_to(tmp_path.resolve())
    run.rename(unavailable)

    view = load_dashboard(tmp_path)
    assert any(row["candidate_id"] == "b" for row in view["candidates"])
    story = view["story"]
    assert story["iterations"][0]["candidates"][0]["measured"]["state"] == "recorded"
    assert story["iterations"][1]["candidates"][0]["measured"]["state"] == "not_recorded"
    assert story["summary"]["failures"][0]["links"][0]["state"] == "not_recorded"
    messages = [check["message"] for check in story["checks"]]
    assert "candidate b has no recorded run" in messages
    assert "evidence candidate:b has no recorded run" in messages


def test_story_marks_corrupt_run_evidence_as_unavailable(tmp_path):
    digest = campaign(tmp_path)
    write_log(tmp_path, log_document(digest))
    run = tmp_path / "runs" / "run-b"
    for relative in (
        "run.lock.json", "status.json", "evaluation.json", "validation/execution.json"
    ):
        (run / relative).write_text("{not valid json", encoding="utf-8")
    (run / "events.jsonl").write_text("{not valid json\n", encoding="utf-8")

    story = load_dashboard(tmp_path)["story"]
    assert story["iterations"][1]["candidates"][0]["measured"]["state"] == "unavailable"
    assert story["summary"]["failures"][0]["links"][0]["state"] == "unavailable"
    messages = [check["message"] for check in story["checks"]]
    assert "candidate b has unavailable run evidence" in messages
    assert "evidence candidate:b has unavailable run evidence" in messages


def test_story_does_not_treat_a_running_candidate_as_a_recorded_failure(tmp_path):
    digest = campaign(tmp_path)
    write_log(tmp_path, log_document(digest))
    run = tmp_path / "runs" / "run-b"
    write_json(run / "status.json", {"state": "running"})
    write_json(run / "evaluation.json", {})
    write_json(run / "validation" / "execution.json", {"status": "pending"})

    story = load_dashboard(tmp_path)["story"]
    measured = story["iterations"][1]["candidates"][0]["measured"]
    assert measured["state"] == "recorded" and measured["outcome"] == "not_recorded"
    assert story["summary"]["failures"][0]["links"][0]["state"] == "outcome_not_recorded"
    assert any(check["message"] == "evidence candidate:b has no recorded outcome"
               for check in story["checks"])


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is needed for the UI regression")
def test_summary_navigates_to_run_without_outcome_but_not_missing_runs(tmp_path):
    digest = campaign(tmp_path)
    write_log(tmp_path, log_document(digest))
    run = tmp_path / "runs" / "run-b"
    write_json(run / "status.json", {"state": "running"})
    write_json(run / "evaluation.json", {})
    write_json(run / "validation" / "execution.json", {"status": "pending"})

    data = load_dashboard(tmp_path)
    story = data["story"]
    link = story["summary"]["failures"][0]["links"][0]
    assert link["state"] == "outcome_not_recorded" and link["run_id"] == "run-b"
    assert any(check["message"] == "evidence candidate:b has no recorded outcome"
               for check in story["checks"])
    story["summary"]["failures"][0]["links"].extend([
        {"ref": "candidate:missing", "state": "not_recorded"},
        {"ref": "candidate:corrupt", "state": "unavailable"},
        {"ref": "candidate:duplicate", "state": "ambiguous"},
    ])

    template = Path(__file__).parents[1] / "src/inferrsi/observability/template.html"
    script = r"""
const fs = require('node:fs'), assert = require('node:assert/strict');
const data = JSON.parse(fs.readFileSync(0, 'utf8'));
const html = fs.readFileSync(process.argv[1], 'utf8');
const selectStart = html.indexOf('  function selectCandidate(');
const selectEnd = html.indexOf('  function renderIterations(', selectStart);
const summaryStart = html.indexOf('  function renderSummary(');
const summaryEnd = html.indexOf('  function renderStory(', summaryStart);
assert(selectStart >= 0 && selectEnd > selectStart);
assert(summaryStart >= 0 && summaryEnd > summaryStart);
const source = html.slice(selectStart, selectEnd) + html.slice(summaryStart, summaryEnd);
function node(tag, text, cls) {
  return {tag, text, cls, children: [], style: {}, disabled: false, listeners: {},
    appendChild(child) { this.children.push(child); },
    setAttribute() {}, addEventListener(type, fn) { this.listeners[type] = fn; },
    click() { if (!this.disabled) this.listeners.click(); }};
}
const target = {setAttribute(name, value) { this[name] = value; },
  focus() { this.focused = true; }, scrollIntoView() { this.scrolled = true; }};
const runSelect = {value: 'old'}, stageSelect = {value: 'old'}, candidateSelect = {value: 'old'};
const api = new Function('data', 'node', 'narrativeNode', 'translatedNarrative',
  'stageNames', 'runSelect', 'stageSelect', 'candidateSelect', 'byId', 'render', 'detailLine',
  'let selected = -1, jumpNotice = "old";\n' + source +
  '\nreturn {renderSummary, selected: () => selected, jumpNotice: () => jumpNotice};')(
  data, node, node, value => value, {search: 'Search'}, runSelect, stageSelect,
  candidateSelect, id => { assert.equal(id, 'candidate-inspection'); return target; },
  () => {}, () => {});
const root = node('div'); api.renderSummary(root, data.story);
const buttons = [];
function visit(element) {
  if (element.tag === 'button') buttons.push(element);
  element.children.forEach(visit);
}
visit(root);
const button = id => buttons.find(b => b.text.startsWith(id + ' · '));
assert.equal(button('a').disabled, false);
assert.equal(button('b').text, 'b · No recorded outcome');
assert.equal(button('b').disabled, false);
button('b').click();
assert.equal(data.candidates[api.selected()].candidate_id, 'b');
assert.equal(api.jumpNotice(), '');
assert.equal(runSelect.value, ''); assert.equal(stageSelect.value, '');
assert.equal(candidateSelect.value, '');
assert.equal(target.tabindex, '-1'); assert(target.focused && target.scrolled);
for (const id of ['missing', 'corrupt', 'duplicate']) {
  assert.equal(button(id).disabled, true); button(id).click();
  assert.equal(data.candidates[api.selected()].candidate_id, 'b');
}
"""
    subprocess.run([shutil.which("node"), "-e", script, str(template)], input=json.dumps(data),
                   check=True, capture_output=True, text=True)


def test_story_retains_a_recorded_failure_when_other_run_files_are_corrupt(tmp_path):
    digest = campaign(tmp_path)
    write_log(tmp_path, log_document(digest))
    run = tmp_path / "runs" / "run-b"
    for relative in ("run.lock.json", "evaluation.json", "validation/execution.json"):
        (run / relative).write_text("{not valid json", encoding="utf-8")
    write_json(run / "status.json", {"state": "failed"})

    story = load_dashboard(tmp_path)["story"]
    measured = story["iterations"][1]["candidates"][0]["measured"]
    assert measured["state"] == "recorded" and measured["outcome"] == "failed"
    assert story["summary"]["failures"][0]["links"][0]["state"] == "recorded"
    assert not any("unavailable run evidence" in check["message"] for check in story["checks"])


def test_story_keeps_a_valid_event_without_inventing_a_result(tmp_path):
    digest = campaign(tmp_path)
    write_log(tmp_path, log_document(digest))
    run = tmp_path / "runs" / "run-b"
    for relative in (
        "run.lock.json", "status.json", "evaluation.json", "validation/execution.json"
    ):
        (run / relative).write_text("{not valid json", encoding="utf-8")
    (run / "events.jsonl").write_text(json.dumps({"phase": "crashed"}) + "\n", encoding="utf-8")

    story = load_dashboard(tmp_path)["story"]
    measured = story["iterations"][1]["candidates"][0]["measured"]
    assert measured["state"] == "recorded" and measured["outcome"] == "not_recorded"
    assert story["summary"]["failures"][0]["links"][0]["state"] == "outcome_not_recorded"


def test_story_flags_narrative_that_disagrees_with_evidence(tmp_path):
    digest = campaign(tmp_path)
    document = log_document(digest)
    document["knowledge"][0]["used_refs"].append("package:never-retrieved")
    document["iterations"][1]["decision"] = {"outcome": "adopted", "candidate_id": "b",
                                             "reason": "Looked fine"}
    document["search_space"]["dimensions"][0]["options"][1]["status"] = "tried"
    document["summary"]["successes"].append({"text": "FP8 worked",
                                             "evidence": ["candidate:b"]})
    document["summary"]["failures"] = []
    write_log(tmp_path, document)
    messages = [check["message"] for check in load_dashboard(tmp_path)["story"]["checks"]]
    assert any("package:never-retrieved" in m and "was not retrieved" in m for m in messages)
    assert any("b is adopted but its recorded outcome is quality failed" in m for m in messages)
    assert any("marked tried, but no iteration" in m for m in messages)
    assert any("candidate:b recorded quality failed, not an improvement" in m for m in messages)
    assert any("b recorded quality failed, but no failure cites it" in m for m in messages)


def test_citing_selected_but_omitted_knowledge_is_flagged(tmp_path):
    create_campaign(tmp_path, "camp")
    reader = FakeReader([context("package:graphs", "Graphs.\n")],
                        items=[{"ref": "package:graphs"}, {"ref": "package:kernels"}],
                        omissions=[{"ref": "package:kernels", "reason": "context_limit"}])
    _, digest = capture_context(tmp_path, context_id="r1", reader=reader, context_bytes=64)
    make_run(tmp_path, "run-a", 4.0)
    record_candidate(tmp_path, candidate_id="a", run_id="run-a", round_number=1, title="A")
    document = log_document(digest)
    document["knowledge"][0].pop("rejected_refs")
    document["iterations"] = document["iterations"][:1]
    document["iterations"][0]["knowledge_refs"] = ["package:kernels"]
    document["search_space"]["dimensions"] = document["search_space"]["dimensions"][:1]
    document["summary"]["failures"] = []
    write_log(tmp_path, document)
    checks = load_dashboard(tmp_path)["story"]["checks"]
    assert {"severity": "warning", "where": "round 1",
            "message": "package:kernels is cited, but it was selected by search but its "
                       "text was omitted from the context"} in checks


def test_round_decision_conflict_with_rounds_file_is_an_error(tmp_path):
    digest = campaign(tmp_path)
    document = log_document(digest)
    document["iterations"][0]["decision"]["outcome"] = "rolled_back"
    write_log(tmp_path, document)
    checks = load_dashboard(tmp_path)["story"]["checks"]
    assert {"severity": "error", "where": "round 1",
            "message": "the log says rolled back, rounds.jsonl records adopted"} in checks


def test_tampered_capture_text_is_withheld(tmp_path):
    digest = campaign(tmp_path)
    write_log(tmp_path, log_document(digest))
    path = tmp_path / "knowledge" / "r1.json"
    path.write_bytes(path.read_bytes().replace(b"Capture repeated", b"Capture CHANGED"))
    story = load_dashboard(tmp_path)["story"]
    assert story["retrievals"][0]["state"] == "hash_mismatch"
    assert "assembled_text" not in story["retrievals"][0]
    assert story["checks"][0]["severity"] == "error"


def test_log_versions_are_kept_and_latest_wins(tmp_path):
    digest = campaign(tmp_path)
    write_log(tmp_path, log_document(digest))
    second = log_document(digest)
    second["summary"]["lessons"] = ["Revised lesson"]
    write_log(tmp_path, second)
    story = load_dashboard(tmp_path)["story"]
    assert [v["version"] for v in story["versions"]] == [1, 2]
    assert story["summary"]["lessons"] == ["Revised lesson"]
    assert (tmp_path / "optimization-log-v1.json").exists()


def test_edited_log_is_not_shown(tmp_path):
    digest = campaign(tmp_path)
    write_log(tmp_path, log_document(digest))
    path = tmp_path / "optimization-log-v1.json"
    path.write_text(path.read_text().replace("Graphs helped", "Everything worked"))
    story = load_dashboard(tmp_path)["story"]
    assert story["state"] == "latest_hash_mismatch"


@pytest.mark.parametrize("mutate, message", [
    (lambda d: d.update(reviewed_by_caller=False), "reviewed_by_caller"),
    (lambda d: d["iterations"].reverse(), "round must increase"),
    (lambda d: d["iterations"][0]["candidates"][0]["option_ids"].append("launch.missing"),
     "unknown option"),
    (lambda d: d["search_space"].update(state="partial"), "missing_reason"),
    (lambda d: d["summary"]["failures"][0].update(cause_stage="luck"), "cause_stage"),
    (lambda d: d["iterations"][0].update(context_ids=["nope"]), "unknown capture"),
    (lambda d: d["goal"].update(statement="\ud800"), "valid Unicode"),
])
def test_log_validation_names_the_bad_field(mutate, message):
    document = log_document("a" * 64)
    mutate(document)
    with pytest.raises(LogError, match=message):
        parse_optimization_log(json.dumps(document).encode())


def test_cli_capture_log_and_dashboard_escape_untrusted_text(tmp_path, capsys):
    digest = campaign(tmp_path)
    document = log_document(digest)
    document["iterations"][0]["rationale"] = "</script><script>alert(1)</script>"
    source = tmp_path / "input.json"
    source.write_text(json.dumps(document), encoding="utf-8")
    assert main(["campaign", "log", "--directory", str(tmp_path), "--file", str(source)]) == 0
    assert json.loads(capsys.readouterr().out)["log"] == "optimization-log-v1.json"
    html = write_dashboard(tmp_path).read_text(encoding="utf-8")
    assert "<script>alert(1)" not in html
    assert '"assembled_text"' in html


def test_cli_capture_context_reports_relative_path(tmp_path, capsys):
    create_campaign(tmp_path, "camp")
    assert main(["campaign", "capture-context", "--directory", str(tmp_path), "--id", "r1",
                 "--relevance", "kv cache block size", "--context-bytes", "40000",
                 "--limit", "2"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["context"] == "knowledge/r1.json"
    assert str(tmp_path) not in json.dumps(output)


def test_single_run_story_is_not_applicable(tmp_path):
    make_run(tmp_path, "solo", 1.0)
    assert load_dashboard(tmp_path / "runs" / "solo")["story"]["state"] == "not_applicable"


def test_round_checks_knowledge_against_its_named_capture(tmp_path):
    create_campaign(tmp_path, "camp")
    _, digest1 = capture_context(tmp_path, context_id="r1", reader=FakeReader(
        [context("package:graphs", "Graphs.\n")],
        items=[{"ref": "package:graphs"}, {"ref": "package:other"}]), context_bytes=4096)
    _, digest2 = capture_context(tmp_path, context_id="r2", reader=FakeReader(
        [context("package:other", "Only in the other capture.\n")]), context_bytes=4096)
    document = log_document(digest1)
    document["knowledge"].append({"context_id": "r2", "sha256": digest2,
                                  "stage": "review", "purpose": "Later review",
                                  "used_refs": [], "takeaways": []})
    document["iterations"][0]["knowledge_refs"] = ["package:other"]
    document["iterations"][0]["context_ids"] = ["r1"]
    write_log(tmp_path, document)

    checks = load_dashboard(tmp_path)["story"]["checks"]
    assert any(check["where"] == "round 1" and "package:other" in check["message"]
               and "omitted" in check["message"] for check in checks)


def test_unavailable_named_capture_does_not_fall_back_to_another_capture(tmp_path):
    create_campaign(tmp_path, "camp")
    _, digest1 = capture_context(tmp_path, context_id="r1", reader=FakeReader(
        [context("package:graphs", "Graphs.\n")]), context_bytes=4096)
    _, digest2 = capture_context(tmp_path, context_id="r2", reader=FakeReader(
        [context("package:graphs", "Other capture.\n")]), context_bytes=4096)
    document = log_document(digest1)
    document["knowledge"].append({"context_id": "r2", "sha256": digest2,
                                  "stage": "review", "purpose": "Later review",
                                  "used_refs": [], "takeaways": []})
    write_log(tmp_path, document)
    (tmp_path / "knowledge/r1.json").unlink()

    checks = load_dashboard(tmp_path)["story"]["checks"]
    assert any(check["where"] == "round 1" and "package:graphs" in check["message"]
               and "not retrieved by the captures this round names" in check["message"]
               for check in checks)


def test_capture_identity_must_match_campaign_and_context_id(tmp_path):
    digest = campaign(tmp_path)
    document = log_document(digest)
    path = tmp_path / "knowledge/r1.json"
    capture = json.loads(path.read_text(encoding="utf-8"))
    capture.update(campaign_id="another-campaign", context_id="another-context")
    raw = json.dumps(capture).encode()
    path.write_bytes(raw)
    document["knowledge"][0]["sha256"] = hashlib.sha256(raw).hexdigest()
    write_log(tmp_path, document)

    retrieval = load_dashboard(tmp_path)["story"]["retrievals"][0]
    assert retrieval["state"] == "identity_mismatch"
    assert "assembled_text" not in retrieval


def test_story_does_not_mark_technical_stages_as_recorded(tmp_path):
    digest = campaign(tmp_path)
    write_log(tmp_path, log_document(digest))
    stages = {stage["name"]: stage["state"] for stage in load_dashboard(tmp_path)["stages"]}
    assert stages["diagnosis"] == "stage_not_recorded"
    assert stages["search"] == "stage_not_recorded"
    assert stages["review"] == "stage_not_recorded"


def test_malformed_log_index_does_not_crash_dashboard(tmp_path):
    create_campaign(tmp_path, "camp")
    (tmp_path / "optimization-log.jsonl").write_text("null\n", encoding="utf-8")
    assert load_dashboard(tmp_path)["story"]["state"] == "corrupt_index"


def test_capture_rejects_symlinked_knowledge_directory(tmp_path):
    root = tmp_path / "campaign"
    outside = tmp_path / "outside"
    outside.mkdir()
    create_campaign(root, "camp")
    try:
        (root / "knowledge").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")
    with pytest.raises(ValueError, match="knowledge"):
        capture_context(root, context_id="r1", reader=FakeReader([]), context_bytes=4096)
    assert not list(outside.iterdir())


def test_dashboard_withholds_capture_through_symlinked_directory(tmp_path):
    digest = campaign(tmp_path)
    write_log(tmp_path, log_document(digest))
    outside = tmp_path / "other-directory"
    (tmp_path / "knowledge").rename(outside)
    try:
        (tmp_path / "knowledge").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")
    retrieval = load_dashboard(tmp_path)["story"]["retrievals"][0]
    assert retrieval["state"] == "unsafe_path"
    assert "assembled_text" not in retrieval


def test_log_index_symlink_is_not_read_or_appended(tmp_path):
    root = tmp_path / "campaign"
    create_campaign(root, "camp")
    outside = tmp_path / "outside.jsonl"
    outside.write_text("outside data\n", encoding="utf-8")
    try:
        (root / "optimization-log.jsonl").symlink_to(outside)
    except OSError:
        pytest.skip("file symlinks are unavailable")
    assert load_dashboard(root)["story"]["state"] == "corrupt_index"
    source = root / "input.json"
    source.write_text(json.dumps(log_document("a" * 64)), encoding="utf-8")
    with pytest.raises(ValueError, match="index"):
        record_log(root, source)
    assert outside.read_text(encoding="utf-8") == "outside data\n"


def test_dashboard_withholds_log_from_another_campaign(tmp_path):
    digest = campaign(tmp_path)
    path, _ = write_log(tmp_path, log_document(digest))
    document = json.loads(path.read_text(encoding="utf-8"))
    document["campaign_id"] = "other-campaign"
    raw = json.dumps(document).encode()
    path.write_bytes(raw)
    index = tmp_path / "optimization-log.jsonl"
    entry = json.loads(index.read_text(encoding="utf-8"))
    entry["sha256"] = hashlib.sha256(raw).hexdigest()
    index.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    assert load_dashboard(tmp_path)["story"]["state"] == "identity_mismatch"


def test_malformed_capture_envelope_is_withheld(tmp_path):
    digest = campaign(tmp_path)
    document = log_document(digest)
    path = tmp_path / "knowledge/r1.json"
    capture = json.loads(path.read_text(encoding="utf-8"))
    capture["items"] = [None]
    raw = json.dumps(capture).encode()
    path.write_bytes(raw)
    document["knowledge"][0]["sha256"] = hashlib.sha256(raw).hexdigest()
    write_log(tmp_path, document)
    retrieval = load_dashboard(tmp_path)["story"]["retrievals"][0]
    assert retrieval["state"] == "invalid_format"
    assert "assembled_text" not in retrieval
