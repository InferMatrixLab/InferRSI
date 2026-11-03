"""Caller-reviewed optimization narratives preserve their bytes and provenance."""

import hashlib
import json

import pytest

from inferrsi.cli import main
from inferrsi.harness import optimization_trace
from inferrsi.harness.campaign_records import create_campaign, record_candidate
from inferrsi.harness.dashboard import write_dashboard
from inferrsi.harness.dashboard_data import load_dashboard
from inferrsi.harness.optimization_trace import (
    MAX_OPTIMIZATION_TRACE_BYTES,
    TraceError,
    parse_optimization_trace,
    read_optimization_trace,
)


def trace_document():
    return {
        "schema_version": 1, "reviewed_by_caller": True,
        "campaign_id": "campaign", "candidate_id": "candidate-a", "round": 1,
        "context": {"state": "complete", "text": "Reviewed context " * 50,
                    "queries": ["search query"],
                    "sources": [{"ref": "package:example", "revision": "sha256:example",
                                 "locator": "core"}], "missing_reason": ""},
        "search_space": {"state": "complete", "items": [
            {"id": "option-a", "description": "A considered configuration"},
            {"id": "option-b", "description": "An option not yet attempted"},
        ], "missing_reason": ""},
        "steps": {"state": "complete", "items": [
            {"sequence": 1, "kind": "attempt", "action": "Measure option A",
             "motivation": "Check its hypothesis", "outcome": "failed",
             "result": "Quality check failed", "search_id": "option-a"},
        ], "missing_reason": ""},
        "summary": {"state": "partial", "successes": [], "failures": ["Quality failed"],
                    "limitations": ["Only one option measured"],
                    "missing_reason": "Remaining options were not run"},
    }


def write_trace(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(document, ensure_ascii=False).encode("utf-8")
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def setup_campaign(root):
    create_campaign(root, "campaign")
    run = root / "runs/run-a"
    run.mkdir(parents=True)
    (run / "run.lock.json").write_text("{}", encoding="utf-8")


def record(root, relative="review/optimization.json"):
    return record_candidate(root, candidate_id="candidate-a", run_id="run-a", round_number=1,
                            title="Candidate A", optimization_trace=relative)


def test_cli_preserves_full_reviewed_context_and_escapes_script(tmp_path, capsys):
    setup_campaign(tmp_path)
    document = trace_document()
    document["context"]["text"] += "\n</script><script>alert('fixture')</script>"
    digest = write_trace(tmp_path / "review/optimization.json", document)

    assert main(["campaign", "record", "--directory", str(tmp_path), "--candidate", "candidate-a",
                 "--run-id", "run-a", "--round", "1", "--title", "Candidate A",
                 "--optimization-trace", "review/optimization.json"]) == 0
    metadata = json.loads((tmp_path / "candidates/candidate-a/candidate.json").read_text())
    assert metadata["optimization_trace_ref"]["sha256"] == digest
    row = load_dashboard(tmp_path)["candidates"][0]
    assert row["optimization_trace"]["context"]["text"] == document["context"]["text"]
    assert len(row["optimization_trace"]["context"]["text"]) > 240
    assert row["optimization_trace"]["attribution"] == (
        "caller_declared_not_proof_of_model_consumption"
    )
    assert len(row["optimization_trace"]["search_space"]["items"]) == 2
    assert len(row["optimization_trace"]["steps"]["items"]) == 1
    assert row["artifacts"]["optimization_trace"]["sha256"] == digest
    html = write_dashboard(tmp_path).read_text(encoding="utf-8")
    assert "</script><script>alert('fixture')</script>" not in html
    payload = html.split('<script id="dashboard-data" type="application/json">', 1)[1]
    payload = payload.split("</script>", 1)[0]
    assert json.loads(payload)["candidates"][0]["optimization_trace"]["context"]["text"] == (
        document["context"]["text"]
    )
    assert capsys.readouterr().out


def test_old_candidates_and_explicit_redaction_stay_visible(tmp_path):
    setup_campaign(tmp_path)
    record_candidate(tmp_path, candidate_id="candidate-a", run_id="run-a", round_number=1,
                     title="Candidate A")
    row = load_dashboard(tmp_path)["candidates"][0]
    assert row["optimization_trace"] is None
    assert row["artifacts"]["optimization_trace"]["missing_reason"] == "not_collected"
    path = tmp_path / "candidates/candidate-a/candidate.json"
    metadata = json.loads(path.read_text(encoding="utf-8"))
    metadata["optimization_trace_ref"] = {"state": "missing", "missing_reason": "redacted",
                                          "sha256": "a" * 64}
    path.write_text(json.dumps(metadata), encoding="utf-8")
    row = load_dashboard(tmp_path)["candidates"][0]
    assert row["optimization_trace"] is None
    assert row["artifacts"]["optimization_trace"]["missing_reason"] == "redacted"
    assert row["artifacts"]["optimization_trace"]["sha256"] == "a" * 64


def test_optional_round_and_redacted_section_preserve_the_caller_explanation(tmp_path):
    setup_campaign(tmp_path)
    document = trace_document()
    del document["round"]
    document["context"].update(state="redacted", text="", missing_reason="Private context withheld")
    write_trace(tmp_path / "review/optimization.json", document)
    record(tmp_path)
    trace = load_dashboard(tmp_path)["candidates"][0]["optimization_trace"]
    assert trace["round"] is None
    assert trace["context"]["state"] == "redacted"
    assert trace["context"]["missing_reason"] == "Private context withheld"


def test_hash_mismatch_and_invalid_format_do_not_expose_text(tmp_path):
    setup_campaign(tmp_path)
    path = tmp_path / "review/optimization.json"
    write_trace(path, trace_document())
    record(tmp_path)
    path.write_text('{"private": "FIXTURE_PRIVATE_TEXT"}', encoding="utf-8")
    row = load_dashboard(tmp_path)["candidates"][0]
    assert row["optimization_trace"] is None
    assert row["artifacts"]["optimization_trace"]["missing_reason"] == "hash_mismatch"
    assert "FIXTURE_PRIVATE_TEXT" not in json.dumps(row)
    candidate = tmp_path / "candidates/candidate-a/candidate.json"
    metadata = json.loads(candidate.read_text(encoding="utf-8"))
    metadata["optimization_trace_ref"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    candidate.write_text(json.dumps(metadata), encoding="utf-8")
    row = load_dashboard(tmp_path)["candidates"][0]
    assert row["optimization_trace"] is None
    assert row["artifacts"]["optimization_trace"]["missing_reason"] == "invalid_format"
    assert "FIXTURE_PRIVATE_TEXT" not in json.dumps(row)


def test_invalid_reference_state_is_not_treated_as_present(tmp_path):
    setup_campaign(tmp_path)
    write_trace(tmp_path / "review/optimization.json", trace_document())
    record(tmp_path)
    candidate = tmp_path / "candidates/candidate-a/candidate.json"
    metadata = json.loads(candidate.read_text(encoding="utf-8"))
    metadata["optimization_trace_ref"]["state"] = "invalid"
    candidate.write_text(json.dumps(metadata), encoding="utf-8")
    row = load_dashboard(tmp_path)["candidates"][0]
    assert row["optimization_trace"] is None
    assert row["artifacts"]["optimization_trace"]["missing_reason"] == "invalid_format"


@pytest.mark.parametrize("identity", ["candidate_id", "campaign_id", "round"])
def test_record_rejects_wrong_identity_without_writing_or_echoing(tmp_path, identity):
    setup_campaign(tmp_path)
    document = trace_document()
    document[identity] = 2 if identity == "round" else "other"
    document["context"]["text"] = "FIXTURE_PRIVATE_TEXT"
    write_trace(tmp_path / "review/optimization.json", document)
    with pytest.raises(ValueError, match="identity_mismatch") as error:
        record(tmp_path)
    assert "FIXTURE_PRIVATE_TEXT" not in str(error.value)
    assert not (tmp_path / "candidates/candidate-a/candidate.json").exists()
    assert not (tmp_path / "rounds.jsonl").exists()


def test_duplicate_candidate_and_ambiguous_round_withhold_trace(tmp_path):
    setup_campaign(tmp_path)
    write_trace(tmp_path / "review/optimization.json", trace_document())
    record(tmp_path)
    original = tmp_path / "candidates/candidate-a/candidate.json"
    duplicate = tmp_path / "candidates/duplicate/candidate.json"
    duplicate.parent.mkdir(parents=True)
    duplicate.write_text(original.read_text(encoding="utf-8"), encoding="utf-8")
    for row in load_dashboard(tmp_path)["candidates"]:
        assert row["optimization_trace"] is None
        assert row["artifacts"]["optimization_trace"]["missing_reason"] == "identity_ambiguous"
    duplicate.unlink()
    with (tmp_path / "rounds.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"round": 2, "candidates": ["candidate-a"]}) + "\n")
    row = load_dashboard(tmp_path)["candidates"][0]
    assert row["round_state"] == "ambiguous"
    assert row["artifacts"]["optimization_trace"]["missing_reason"] == "identity_ambiguous"


@pytest.mark.parametrize("relative", ["../outside.json", "/outside.json", "C:\\outside.json",
                                      "review\\..\\outside.json"])
def test_unsafe_reference_never_reads_outside_campaign(tmp_path, relative):
    setup_campaign(tmp_path)
    with pytest.raises(ValueError, match="unsafe_path"):
        record(tmp_path, relative)
    assert not (tmp_path / "candidates/candidate-a/candidate.json").exists()


def test_symlink_escape_is_refused(tmp_path):
    root = tmp_path / "campaign"
    setup_campaign(root)
    outside = tmp_path / "outside.json"
    write_trace(outside, trace_document())
    link = root / "outside-link.json"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("file symlinks are unavailable")
    with pytest.raises(ValueError, match="unsafe_path"):
        record(root, "outside-link.json")


@pytest.mark.parametrize("field", ["review", "partial", "contradiction", "order", "duplicate_key"])
def test_invalid_review_state_and_malformed_records_are_rejected(field):
    document = trace_document()
    if field == "review":
        document["reviewed_by_caller"] = False
    elif field == "partial":
        document["context"]["state"] = "partial"
    elif field == "contradiction":
        document["context"]["missing_reason"] = "Some context was withheld"
    elif field == "order":
        document["steps"]["items"].append({**document["steps"]["items"][0]})
    raw = json.dumps(document).encode("utf-8")
    if field == "duplicate_key":
        raw = raw[:-1] + b', "schema_version": 1}'
    with pytest.raises(TraceError):
        parse_optimization_trace(raw)


def test_oversized_trace_is_rejected_without_partial_record(tmp_path):
    setup_campaign(tmp_path)
    path = tmp_path / "review/optimization.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"x" * (MAX_OPTIMIZATION_TRACE_BYTES + 1))
    with pytest.raises(ValueError, match="too_large"):
        record(tmp_path)
    assert not (tmp_path / "candidates/candidate-a/candidate.json").exists()


def test_hash_and_parse_use_same_snapshot_even_if_file_changes(tmp_path, monkeypatch):
    path = tmp_path / "optimization.json"
    original = trace_document()
    digest = write_trace(path, original)
    reader = optimization_trace._read

    def changing_reader(root, relative):
        data, reference = reader(root, relative)
        path.write_text('{"changed": true}', encoding="utf-8")
        return data, reference

    monkeypatch.setattr(optimization_trace, "_read", changing_reader)
    value, ref = read_optimization_trace(
        tmp_path, {"path": "optimization.json", "sha256": digest}, campaign_id="campaign",
        candidate_id="candidate-a", round_number=1, unique_candidate=True,
    )
    assert value["context"]["text"] == original["context"]["text"]
    assert ref["sha256"] == digest
