"""Caller-reviewed optimization narratives preserve their bytes and provenance."""

import hashlib
import json
from pathlib import Path

import pytest

from inferrsi.cli import main
from inferrsi.harness import campaign_records, optimization_trace
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


def record(root, relative="optimization.json"):
    return record_candidate(root, candidate_id="candidate-a", run_id="run-a", round_number=1,
                            title="Candidate A", optimization_trace=relative)


def test_cli_preserves_full_reviewed_context_and_escapes_script(tmp_path, capsys):
    setup_campaign(tmp_path)
    document = trace_document()
    document["context"]["text"] += "\n</script><script>alert('fixture')</script>"
    digest = write_trace(tmp_path / "optimization.json", document)

    assert main(["campaign", "record", "--directory", str(tmp_path), "--candidate", "candidate-a",
                 "--run-id", "run-a", "--round", "1", "--title", "Candidate A",
                 "--optimization-trace", "optimization.json"]) == 0
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


def test_assembled_context_round_trips_from_actual_knowledge_command(tmp_path, capsys):
    setup_campaign(tmp_path)
    context_path = tmp_path / "reviewed-context.md"
    assert main(["context", "decode", "--repo-type", "vllm", "--backend", "cuda",
                 "--output", str(context_path)]) == 0
    exact_context = context_path.read_bytes().decode("utf-8")
    assert exact_context.startswith("# InferRSI knowledge context")
    document = trace_document()
    document["context"]["text"] = ""
    template = tmp_path / "template.json"
    template.write_text(json.dumps(document), encoding="utf-8")

    assert main(["campaign", "assemble-trace", "--directory", str(tmp_path),
                 "--template", str(template), "--context-file", str(context_path),
                 "--output", "optimization.json"]) == 0
    record(tmp_path, "optimization.json")
    row = load_dashboard(tmp_path)["candidates"][0]
    assert row["optimization_trace"]["context"]["text"] == exact_context
    assert row["artifacts"]["optimization_trace"]["state"] == "present"
    html = write_dashboard(tmp_path).read_text(encoding="utf-8")
    payload = html.split('<script id="dashboard-data" type="application/json">', 1)[1]
    payload = payload.split("</script>", 1)[0]
    assert json.loads(payload)["candidates"][0]["optimization_trace"]["context"]["text"] == (
        exact_context
    )
    assert capsys.readouterr().out


def test_assemble_requires_review_and_never_overwrites(tmp_path, capsys):
    setup_campaign(tmp_path)
    document = trace_document()
    document["context"]["text"] = ""
    document["reviewed_by_caller"] = False
    template = tmp_path / "template.json"
    template.write_text(json.dumps(document), encoding="utf-8")
    context_path = tmp_path / "context.txt"
    context_path.write_bytes(b"first line\r\nsecond line\n")
    args = ["campaign", "assemble-trace", "--directory", str(tmp_path),
            "--template", str(template), "--context-file", str(context_path),
            "--output", "optimization.json"]
    with pytest.raises(SystemExit):
        main(args)
    assert not (tmp_path / "optimization.json").exists()
    document["reviewed_by_caller"] = True
    template.write_text(json.dumps(document), encoding="utf-8")
    assert main(args) == 0
    raw = (tmp_path / "optimization.json").read_bytes()
    assert parse_optimization_trace(raw)["context"]["text"] == "first line\r\nsecond line\n"
    with pytest.raises(SystemExit):
        main(args)
    assert (tmp_path / "optimization.json").read_bytes() == raw
    assert capsys.readouterr().out


def test_assemble_rejects_subdirectories_and_traversal(tmp_path):
    setup_campaign(tmp_path)
    document = trace_document()
    document["context"]["text"] = ""
    template = tmp_path / "template.json"
    template.write_text(json.dumps(document), encoding="utf-8")
    context_path = tmp_path / "context.txt"
    context_path.write_text("Reviewed context", encoding="utf-8")
    args = ["campaign", "assemble-trace", "--directory", str(tmp_path),
            "--template", str(template), "--context-file", str(context_path), "--output"]
    for unsafe in ("subdir/optimization.json", "../outside.json", "C:\\outside.json"):
        with pytest.raises(SystemExit):
            main(args + [unsafe])


def test_assemble_cleans_temporary_file_if_publish_fails(tmp_path, monkeypatch):
    setup_campaign(tmp_path)
    document = trace_document()
    document["context"]["text"] = ""
    template = tmp_path / "template.json"
    template.write_text(json.dumps(document), encoding="utf-8")
    context = tmp_path / "context.txt"
    context.write_text("Reviewed context", encoding="utf-8")

    def fail_link(*args):
        raise OSError("simulated publish failure")

    monkeypatch.setattr(campaign_records.os, "link", fail_link)
    with pytest.raises(OSError):
        campaign_records.assemble_trace(tmp_path, template=template, context_file=context,
                                        output="optimization.json")
    assert not (tmp_path / "optimization.json").exists()
    assert not list(tmp_path.glob(".optimization-*.tmp"))


def test_run_binding_and_event_references_are_validated(tmp_path):
    setup_campaign(tmp_path)
    document = trace_document()
    document["run_id"] = "different-run"
    document["steps"]["items"][0]["event_ref"] = {
        "source": "events", "line": 1, "sha256": "a" * 64,
    }
    write_trace(tmp_path / "optimization.json", document)
    with pytest.raises(ValueError, match="identity_mismatch"):
        record(tmp_path)
    document["run_id"] = "run-a"
    write_trace(tmp_path / "optimization.json", document)
    record(tmp_path)
    row = load_dashboard(tmp_path)["candidates"][0]
    assert row["optimization_trace"]["run_id"] == "run-a"
    assert row["optimization_trace"]["steps"]["items"][0]["event_ref"]["sha256"] == "a" * 64
    document["steps"]["items"][0]["event_ref"]["line"] = 0
    with pytest.raises(TraceError):
        parse_optimization_trace(json.dumps(document).encode())


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
    write_trace(tmp_path / "optimization.json", document)
    record(tmp_path)
    trace = load_dashboard(tmp_path)["candidates"][0]["optimization_trace"]
    assert trace["round"] is None
    assert trace["context"]["state"] == "redacted"
    assert trace["context"]["missing_reason"] == "Private context withheld"


def test_hash_mismatch_and_invalid_format_do_not_expose_text(tmp_path):
    setup_campaign(tmp_path)
    path = tmp_path / "optimization.json"
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
    write_trace(tmp_path / "optimization.json", trace_document())
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
    write_trace(tmp_path / "optimization.json", document)
    with pytest.raises(ValueError, match="identity_mismatch") as error:
        record(tmp_path)
    assert "FIXTURE_PRIVATE_TEXT" not in str(error.value)
    assert not (tmp_path / "candidates/candidate-a/candidate.json").exists()
    assert not (tmp_path / "rounds.jsonl").exists()


def test_duplicate_candidate_and_ambiguous_round_withhold_trace(tmp_path):
    setup_campaign(tmp_path)
    write_trace(tmp_path / "optimization.json", trace_document())
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


def test_replacement_between_lstat_and_open_is_withheld(tmp_path, monkeypatch):
    root = tmp_path / "campaign"
    root.mkdir()
    target = root / "optimization.json"
    outside = tmp_path / "outside.json"
    write_trace(target, trace_document())
    outside.write_text('{"private":"FIXTURE_PRIVATE_TEXT"}', encoding="utf-8")
    probe = root / "probe-link"
    try:
        probe.symlink_to(outside)
    except OSError:
        pytest.skip("file symlinks are unavailable")
    probe.unlink()
    original_open = optimization_trace.os.open
    swapped = False

    def swap_before_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if Path(path) == target and not swapped:
            swapped = True
            target.unlink()
            target.symlink_to(outside)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(optimization_trace.os, "open", swap_before_open)
    value, ref = read_optimization_trace(
        root, {"path": "optimization.json"}, campaign_id="campaign",
        candidate_id="candidate-a", round_number=1, unique_candidate=True, require_hash=False,
    )
    assert swapped
    assert value is None
    assert ref["missing_reason"] in {"unsafe_path", "unreadable"}
    assert "FIXTURE_PRIVATE_TEXT" not in json.dumps(ref)


def test_missing_run_does_not_read_placeholder_directory(tmp_path):
    setup_campaign(tmp_path)
    directory = tmp_path / "candidates" / "candidate-a"
    fake_run = directory / "missing-run"
    fake_run.mkdir(parents=True)
    (directory / "candidate.json").write_text(
        json.dumps({"candidate_id": "candidate-a", "title": "Candidate A", "round": 1}),
        encoding="utf-8",
    )
    (fake_run / "events.jsonl").write_text(
        json.dumps({"phase": "measurement", "side": "candidate", "trial": 1}) + "\n",
        encoding="utf-8",
    )
    (fake_run / "evaluation.json").write_text(
        json.dumps({"verdict": "PASS", "improvement_pct": 999}), encoding="utf-8",
    )
    row = load_dashboard(tmp_path)["candidates"][0]
    assert row["run_id"] is None
    assert row["events"] == []
    assert row["improvement_pct"] is None
    assert row["artifacts"]["events"]["missing_reason"] == "not_collected"


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
    path = tmp_path / "optimization.json"
    path.parent.mkdir(parents=True, exist_ok=True)
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
