"""Portable search records require exact delivered passages and reviewed decisions."""

import hashlib
import json

import pytest

from inferrsi.harness.campaign_records import create_campaign
from inferrsi.harness.knowledge_capture import assemble_context_text, capture_context
from inferrsi.harness.search_attribution import import_search

REVISION = "f6d200" + "a" * 34
CORPUS = {"repository": "InferMatrixLab/InferRSI", "revision": REVISION,
          "root": "src/inferrsi/data/skill_library"}


def _review(path, *, decisions, **extra):
    document = {"task": "Review the search and explain the decision.",
                "corpus": CORPUS, "decisions": decisions, **extra}
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _archive_event(*, delivery_state="visible", passage_ref="cases/a.md", line=1,
                   text="Use the stable RoPE case.", archive_omitted=False):
    return {
        "action": "read", "tool": "cat", "id": "tool-event-7", "event_id": "tool-event-7",
        "trace_line": 2,
        "materials": [{"ref": "cases/a.md"}],
        "delivery": {"state": delivery_state, "return_line": 3,
                      "archive_omitted": archive_omitted,
                      "passages": [
            {"ref": passage_ref, "line": line, "text": text},
        ]},
    }


def _reader(monkeypatch, event):
    def read_window(trace, lines, corpus, *, archive=False, selections=None):
        window = {"session": "private-session", "lines": [2, 4]}
        if archive:
            return {**window, "archive": True}, [event], {
                4: "I will use the stable RoPE case for validation."}, [], []
        return window, [], {4: "I will use the stable RoPE case for validation."}, [], []

    monkeypatch.setattr("inferrsi.harness.search_attribution.read_window", read_window)


def _decision(**changes):
    return {"use": "used", "ref": "cases/a.md", "event_line": 2,
            "passage_line": 1, "decision_line": 4,
            "decision_quote": "use the stable RoPE case", **changes}


def _real_read_trace(path, corpus):
    output = "Use the stable RoPE case."
    rows = [
        {"type": "session_meta", "payload": {"id": "private-session"}},
        {"type": "response_item", "payload": {
            "type": "function_call", "name": "exec_command", "call_id": "call-1",
            "arguments": {"cmd": "cat case.md", "workdir": str(corpus)},
        }},
        {"type": "event_msg", "payload": {"type": "item_completed", "item": {
            "type": "CommandExecution", "id": "tool-event-7", "cwd": corpus.as_uri(),
            "command": ["/bin/sh", "-lc", "cat case.md"], "exit_code": 0,
            "aggregated_output": output,
        }}},
        {"type": "response_item", "payload": {
            "type": "function_call_output", "call_id": "call-1", "output": f"Output:\n{output}",
        }},
        {"type": "response_item", "payload": {
            "type": "message", "role": "assistant", "phase": "final_answer",
            "content": [{"type": "output_text",
                         "text": "I will use the stable RoPE case for validation."}],
        }},
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_archive_rejects_unavailable_or_mismatched_passage_before_writing(tmp_path, monkeypatch):
    campaign = tmp_path / "campaign"
    create_campaign(campaign, "example")
    trace, corpus = tmp_path / "rollout.jsonl", tmp_path / "corpus"
    trace.write_text("trace", encoding="utf-8")
    inputs = {"number": 1, "trace": trace, "lines": [2, 4],
              "knowledge_root": corpus, "complete": True}
    review = _review(tmp_path / "review.json", decisions=[_decision()])

    _reader(monkeypatch, _archive_event(delivery_state="unknown"))
    with pytest.raises(ValueError, match="verified delivered passage"):
        import_search(campaign, archive_review=review, **inputs)
    assert not (campaign / "search/round-1.json").exists()

    _reader(monkeypatch, _archive_event())
    # The selected event is visible, but the reviewed source line is absent.
    review.write_text(json.dumps({"task": "Review the search and explain the decision.",
                                  "corpus": CORPUS, "decisions": [
                                      _decision(passage_line=3),
                                  ]}), encoding="utf-8")
    with pytest.raises(ValueError, match="exact delivered source passage"):
        import_search(campaign, archive_review=review, **inputs)
    assert not (campaign / "search/round-1.json").exists()

    review = _review(tmp_path / "review.json", decisions=[
        _decision(decision_quote="a quote not in the assistant response")])
    with pytest.raises(ValueError, match="decision_quote"):
        import_search(campaign, archive_review=review, **inputs)
    assert not (campaign / "search/round-1.json").exists()


def test_archive_requires_decision_after_visible_return_and_unique_locator(tmp_path, monkeypatch):
    campaign = tmp_path / "campaign"
    create_campaign(campaign, "example")
    trace, corpus = tmp_path / "rollout.jsonl", tmp_path / "corpus"
    trace.write_text("trace", encoding="utf-8")
    inputs = {"number": 1, "trace": trace, "lines": [2, 4],
              "knowledge_root": corpus, "complete": True}

    _reader(monkeypatch, _archive_event())
    review = _review(tmp_path / "review.json", decisions=[
        _decision(decision_line=3)])
    with pytest.raises(ValueError, match="follow the visible tool return"):
        import_search(campaign, archive_review=review, **inputs)

    _reader(monkeypatch, _archive_event(line=None, archive_omitted=True))
    review = _review(tmp_path / "review.json", decisions=[
        _decision(passage_line=None)])
    with pytest.raises(ValueError, match="line-numbered read"):
        import_search(campaign, archive_review=review, **inputs)


def test_legacy_flag_remains_a_noncounting_declaration_in_archive(tmp_path):
    campaign = tmp_path / "campaign"
    create_campaign(campaign, "example")
    trace, corpus = tmp_path / "rollout.jsonl", tmp_path / "corpus"
    _real_read_trace(trace, corpus)
    review = _review(tmp_path / "review.json", decisions=[])
    path = import_search(campaign, number=1, trace=trace, lines=[2, 5],
                         knowledge_root=corpus, used=[("case.md", 5)],
                         archive_review=review)
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["materials"]["case.md"]["use"] == "unknown"
    assert record["observed"]["used"] == 0
    assert record["declarations"] == [{
        "ref": "case.md", "use": "used", "basis": "caller_flag_declaration",
        "decision_line": 5, "delivery_state": "visible",
    }]
    local = json.loads((campaign / "search/round-1.json").read_text(encoding="utf-8"))
    assert local["materials"]["case.md"]["use"] == "used"


def test_archive_embeds_verified_quote_and_reimport_is_stable_and_correctable(tmp_path):
    campaign = tmp_path / "campaign"
    create_campaign(campaign, "example")
    trace, corpus = tmp_path / "rollout.jsonl", tmp_path / "corpus"
    _real_read_trace(trace, corpus)
    review = _review(tmp_path / "review.json", decisions=[_decision(
        ref="case.md", event_line=3, decision_line=5,
        decision_quote="I will use the stable RoPE case")],
                     result_note="Decision only; no device run.")
    inputs = {"number": 1, "trace": trace, "lines": [2, 5],
              "knowledge_root": corpus, "complete": True}

    path = import_search(campaign, archive_review=review, **inputs)
    assert path == campaign / "search/archive/round-1.json"
    original = path.read_bytes()
    assert import_search(campaign, archive_review=review, **inputs) == path
    assert path.read_bytes() == original

    document = json.loads(original)
    assert document["schema_version"] == 2
    assert document["task"] == "Review the search and explain the decision."
    assert document["corpus"] == CORPUS
    assert document["result_note"] == "Decision only; no device run."
    assert document["result_note_basis"] == "caller_reviewed"
    assert document["trace"] == {"lines": [2, 5], "archive": True}
    assert "session" not in document["trace"]
    evidence, = document["materials"]["case.md"]["evidence"]
    assert evidence == {
        "use": "used", "basis": "archive_reviewed",
        "event_id": document["events"][0]["id"],
        "passage_line": 1, "passage_text": "Use the stable RoPE case.",
        "decision_line": 5, "decision_quote": "I will use the stable RoPE case",
    }
    assert document["observed"]["used"] == 1
    assert document["candidates"] == []
    assert str(tmp_path) not in original.decode()

    review = _review(tmp_path / "review.json", decisions=[_decision(
        use="rejected", ref="case.md", event_line=3, decision_line=5,
        decision_quote="I will use the stable RoPE case")])
    import_search(campaign, archive_review=review, **inputs)
    corrected = json.loads(path.read_bytes())
    assert corrected["materials"]["case.md"]["use"] == "rejected"
    assert corrected["materials"]["case.md"]["evidence"][0]["use"] == "rejected"


class _Reader:
    def __init__(self, text):
        self.text = text

    def collect(self, query="", **options):
        return {
            "items": [{"ref": "package:manual", "revision": "sha256:" + "a" * 64,
                       "title": "manual", "kind": "knowledge"}],
            "omissions": [], "context_omissions": [],
            "selection": {"method": options.get("relevance_method"),
                          "cue": options.get("relevance") or query,
                          "scope": "generated-packaged-skills", "ranking_applied": True},
            "context_bytes": len(self.text.encode()), "context_budget": {"max_bytes": 4096},
            "contexts": [{"ref": "package:manual", "revision": "sha256:" + "a" * 64,
                          "content_bytes": len(self.text.encode()), "resources": [{
                              "path": "skills/manual/SKILL.md", "role": "core",
                              "sha256": hashlib.sha256(self.text.encode()).hexdigest(),
                              "content": self.text,
                          }], "omissions": [], "sources": []}],
        }


def _capture_trace(path, output, assistant_text="No adoption decision."):
    rows = [{"type": "session_meta", "payload": {"id": "private-session"}},
            {"type": "response_item", "payload": {"type": "custom_tool_call_output",
             "output": output}},
            {"type": "response_item", "payload": {"type": "message", "role": "assistant",
             "phase": "final_answer", "content": [{"type": "output_text",
                                                        "text": assistant_text}]}}]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _make_capture(tmp_path):
    campaign = tmp_path / "campaign"
    create_campaign(campaign, "example")
    capture, _ = capture_context(campaign, context_id="r1", reader=_Reader("Manual line.\n"),
                                 relevance="manual", context_bytes=4096)
    document = json.loads(capture.read_text(encoding="utf-8"))
    output = assemble_context_text(document["contexts"])
    return campaign, output


def test_indexer_capture_is_prepared_and_unknown_without_return(tmp_path):
    campaign, output = _make_capture(tmp_path)
    trace = tmp_path / "rollout.jsonl"
    _capture_trace(trace, output)
    review = _review(tmp_path / "review.json", decisions=[])

    path = import_search(campaign, number=1, trace=trace, lines=[2, 3],
                         knowledge_root=tmp_path / "corpus", context_ids=["r1"],
                         archive_review=review)
    record = json.loads(path.read_text(encoding="utf-8"))
    event, = record["events"]
    material, = event["materials"]
    assert event["capture"] == {"state": "verified", "source": "knowledge/r1.json",
                                "sha256": event["sha256"]}
    assert event["request"]["relevance"] == "manual"
    assert event["selection"] == {"method": "weighted-lexical-v1", "cue": "manual",
                                   "scope": "generated-packaged-skills",
                                   "ranking_applied": True}
    assert material["preparation_state"] == "prepared"
    assert event["delivery"]["state"] == "unknown"
    assert material["delivery_state"] == "unknown"
    assert record["materials"]["package:manual"]["use"] == "unknown"
    assert str(tmp_path) not in path.read_text(encoding="utf-8")


def test_indexer_archive_review_matches_exact_visible_resource_and_return(tmp_path):
    campaign, output = _make_capture(tmp_path)
    trace = tmp_path / "rollout.jsonl"
    _capture_trace(trace, output, "I will use Manual line for validation.")
    use = {
        "use": "used", "ref": "package:manual", "event_line": 2, "passage_line": 1,
        "passage_path": "skills/manual/SKILL.md", "decision_line": 3,
        "decision_quote": "I will use Manual line",
    }
    review = _review(tmp_path / "review.json", decisions=[use, use], capture_returns={"r1": 2})

    path = import_search(campaign, number=1, trace=trace, lines=[2, 3],
                         knowledge_root=tmp_path / "corpus", context_ids=["r1"],
                         archive_review=review)
    record = json.loads(path.read_text(encoding="utf-8"))
    event, = record["events"]
    material, = event["materials"]
    assert event["delivery"]["state"] == "visible"
    assert material["delivery_state"] == "visible"
    assert event["delivery"]["visible_resources"] == [
        {"ref": "package:manual", "path": "skills/manual/SKILL.md"}]
    assert event["delivery"]["passages"] == [{
        "ref": "package:manual", "path": "skills/manual/SKILL.md", "line": 1,
        "text": "Manual line.",
    }]
    assert record["materials"]["package:manual"]["use"] == "used"
    assert record["materials"]["package:manual"]["evidence"][0]["basis"] == "archive_reviewed"
    assert str(tmp_path) not in path.read_text(encoding="utf-8")


def test_capture_only_archive_needs_no_trace_and_is_idempotent(tmp_path):
    campaign, _ = _make_capture(tmp_path)
    review = _review(tmp_path / "review.json", decisions=[])
    path = import_search(campaign, number=1, context_ids=["r1"], complete=True,
                         archive_review=review)
    original = path.read_bytes()
    import_search(campaign, number=1, context_ids=["r1"], complete=True,
                  archive_review=review)
    assert path.read_bytes() == original
    record = json.loads(original)
    assert record["trace"] is None
    assert record["coverage"] == "complete"
    assert record["counts"] is not None
    assert record["events"][0]["delivery"]["state"] == "unknown"
