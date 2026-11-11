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


def _real_read_trace(path, corpus, *, command="cat case.md", output="Use the stable RoPE case."):
    rows = [
        {"type": "session_meta", "payload": {"id": "private-session"}},
        {"type": "response_item", "payload": {
            "type": "function_call", "name": "exec_command", "call_id": "call-1",
            "arguments": {"cmd": command, "workdir": str(corpus)},
        }},
        {"type": "event_msg", "payload": {"type": "item_completed", "item": {
            "type": "CommandExecution", "id": "tool-event-7", "cwd": corpus.as_uri(),
            "command": ["/bin/sh", "-lc", command], "exit_code": 0,
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


@pytest.mark.parametrize(("command", "output", "source_line"), [
    ("rg needle .", "./case.md:42:needle\n", None),
    ("rg -Hn needle .", "./case.md:1:42:needle\n", 1),
])
def test_rg_numeric_body_prefix_is_not_an_invented_source_line(
    tmp_path, command, output, source_line,
):
    campaign = tmp_path / "campaign"
    create_campaign(campaign, "example")
    trace, corpus = tmp_path / "rollout.jsonl", tmp_path / "corpus"
    _real_read_trace(trace, corpus, command=command, output=output)
    inputs = {"number": 1, "trace": trace, "lines": [2, 5],
              "knowledge_root": corpus, "complete": True}
    use = _decision(ref="case.md", event_line=3, decision_line=5, passage_line=42)
    review = _review(tmp_path / "review.json", decisions=[use])
    with pytest.raises(ValueError, match="exact delivered source passage"):
        import_search(campaign, archive_review=review, **inputs)
    assert not (campaign / "search/round-1.json").exists()

    review = _review(tmp_path / "review.json", decisions=[{**use, "passage_line": source_line}])
    path = import_search(campaign, archive_review=review, **inputs)
    record = json.loads(path.read_text())
    evidence, = record["materials"]["case.md"]["evidence"]
    assert evidence["passage_line"] == source_line
    assert evidence["passage_text"] == "42:needle"
    assert record["events"][0]["materials"][0]["match_line"] == source_line
    assert record["counts"]["used"] == 1


@pytest.mark.parametrize(("command", "output", "ref", "line", "text"), [
    ("rg -Hn needle 42", "42:1:needle\n", "42", 1, "needle"),
    ("rg --with-filename --line-number needle 42", "42:1:needle\n", "42", 1, "needle"),
    ("rg -H needle guide.md", "guide.md:guide.md:needle\n", "guide.md", None, "guide.md:needle"),
    ("rg --with-filename needle guide.md", "guide.md:guide.md:needle\n",
     "guide.md", None, "guide.md:needle"),
])
def test_rg_explicit_filename_preserves_numeric_names_and_body_prefixes(
    tmp_path, command, output, ref, line, text,
):
    campaign = tmp_path / "campaign"
    create_campaign(campaign, "example")
    trace, corpus = tmp_path / "rollout.jsonl", tmp_path / "corpus"
    _real_read_trace(trace, corpus, command=command, output=output)
    inputs = {"number": 1, "trace": trace, "lines": [2, 5],
              "knowledge_root": corpus, "complete": True}
    use = _decision(ref=ref, event_line=3, decision_line=5, passage_line=42)
    review = _review(tmp_path / "review.json", decisions=[use])
    with pytest.raises(ValueError, match="exact delivered source passage"):
        import_search(campaign, archive_review=review, **inputs)
    review = _review(tmp_path / "review.json", decisions=[{**use, "passage_line": line}])
    record = json.loads(import_search(campaign, archive_review=review, **inputs).read_text())
    evidence, = record["materials"][ref]["evidence"]
    assert (evidence["passage_line"], evidence["passage_text"]) == (line, text)
    assert record["coverage"] == "complete" and record["counts"]["used"] == 1


@pytest.mark.parametrize(("command", "output"), [
    ("rg needle guide.md", "guide.md:needle\n"),
    ("rg -n needle guide.md", "1:guide.md:needle\n"),
    ("rg -n needle cases", "cases/a.md:1:needle\n"),
])
def test_rg_unknown_single_operand_type_cannot_attribute_a_body(tmp_path, command, output):
    campaign = tmp_path / "campaign"
    create_campaign(campaign, "example")
    trace, corpus = tmp_path / "rollout.jsonl", tmp_path / "corpus"
    _real_read_trace(trace, corpus, command=command, output=output)
    review = _review(tmp_path / "review.json", decisions=[])
    inputs = {"number": 1, "trace": trace, "lines": [2, 5],
              "knowledge_root": corpus, "complete": True}
    record = json.loads(import_search(campaign, archive_review=review, **inputs).read_text())
    assert record["coverage"] == "partial" and record["counts"] is None
    assert record["observed"]["used"] == 0 and not record["materials"]
    assert record["events"][0]["delivery"]["passages"] == []


@pytest.mark.parametrize("transformation", ["redacted", "root_normalized", "truncated"])
def test_adoption_preserves_source_excerpt_transformations(tmp_path, transformation):
    campaign = tmp_path / "campaign"
    create_campaign(campaign, "example")
    trace, corpus = tmp_path / "rollout.jsonl", tmp_path / "corpus"
    outputs = {
        "redacted": "Use the stable RoPE case. See https://example.org/source.",
        "root_normalized": f"Use the stable RoPE case in {corpus}.",
        "truncated": "Use the stable RoPE case. " + "x" * 450,
    }
    _real_read_trace(trace, corpus, output=outputs[transformation])
    review = _review(tmp_path / "review.json", decisions=[_decision(
        ref="case.md", event_line=3, decision_line=5)])
    path = import_search(campaign, number=1, trace=trace, lines=[2, 5],
                         knowledge_root=corpus, archive_review=review)
    record = json.loads(path.read_text())
    passage, = record["events"][0]["delivery"]["passages"]
    evidence, = record["materials"]["case.md"]["evidence"]
    assert passage[transformation] is True
    assert evidence[f"passage_{transformation}"] is True
    assert evidence["passage_text"] == passage["text"]
    assert evidence["passage_text"] != outputs[transformation]
    assert record["observed"]["used"] == 1


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


@pytest.mark.parametrize("status", ["used", "rejected"])
def test_local_capture_flag_without_ordering_stays_a_declaration(tmp_path, status):
    campaign, output = _make_capture(tmp_path)
    trace = tmp_path / "rollout.jsonl"
    _capture_trace(trace, output, "I will use Manual line for validation.")
    inputs = {"number": 1, "trace": trace, "lines": [2, 3],
              "knowledge_root": tmp_path / "corpus", "context_ids": ["r1"],
              "complete": True}
    path = import_search(campaign, **{status: [("package:manual", 3)]}, **inputs)
    record = json.loads(path.read_text())
    material = record["materials"]["package:manual"]
    assert material["use"] == "unknown" and record["counts"]["used"] == 0
    assert material["declarations"] == [{
        "use": status, "basis": "caller_reviewed", "decision_line": 3,
        "reason": "observation_order_unknown",
    }]
    import_search(campaign, **inputs)
    assert json.loads(path.read_text()) == record


def _command_row(corpus, script, output, identity):
    return {"type": "event_msg", "payload": {"type": "item_completed", "item": {
        "type": "CommandExecution", "id": identity, "cwd": corpus.as_uri(),
        "command": ["/bin/sh", "-lc", script], "exit_code": 0,
        "aggregated_output": output,
    }}}


@pytest.mark.parametrize("status", ["used", "rejected"])
def test_extended_window_preserves_old_unknown_declaration_with_later_observation(tmp_path, status):
    campaign, output = _make_capture(tmp_path)
    trace, corpus = tmp_path / "rollout.jsonl", tmp_path / "corpus"
    _capture_trace(trace, output, "I will use Manual line for validation.")
    inputs = {"number": 1, "trace": trace, "knowledge_root": corpus,
              "context_ids": ["r1"], "complete": True}
    path = import_search(campaign, lines=[2, 3], **{status: [("package:manual", 3)]}, **inputs)
    original = json.loads(path.read_text())
    declaration, = original["materials"]["package:manual"]["declarations"]
    assert declaration["reason"] == "observation_order_unknown"

    rows = [_command_row(corpus, "pwd", str(corpus), "pwd-1"),
            _command_row(corpus, "pwd", str(corpus), "pwd-2"),
            _command_row(corpus, "cat package:manual", "Manual line.\n", "later-read")]
    with trace.open("a", encoding="utf-8") as stream:
        stream.writelines(json.dumps(row) + "\n" for row in rows)
    import_search(campaign, lines=[2, 6], **inputs)
    expanded = json.loads(path.read_text())
    assert expanded["trace"]["lines"] == [2, 6]
    read, = [event for event in expanded["events"] if event.get("trace_line") is not None]
    assert (read["tool"], read["trace_line"], read["materials"]) == (
        "cat", 6, [{"ref": "package:manual"}],
    )
    capture, = [event for event in expanded["events"] if event["tool"] == "collect"]
    assert capture.get("trace_line") is None
    assert expanded["materials"]["package:manual"]["use"] == "unknown"
    assert expanded["materials"]["package:manual"]["declarations"] == [
        {**declaration, "reason": "no_prior_ordered_observation"},
    ]
    assert expanded["counts"]["used"] == 0
    saved = path.read_bytes()
    import_search(campaign, lines=[2, 6], **inputs)
    assert path.read_bytes() == saved
    # Keeping an earlier accepted unknown does not accept a new reversed claim.
    with pytest.raises(ValueError, match="decision must follow.*observation"):
        import_search(campaign, lines=[2, 6], **{status: [("package:manual", 3)]}, **inputs)
    assert path.read_bytes() == saved


@pytest.mark.parametrize("status", ["used", "rejected"])
def test_corrected_corpus_promotes_declaration_without_stale_reason(tmp_path, status):
    campaign, output = _make_capture(tmp_path)
    trace, corpus = tmp_path / "rollout.jsonl", tmp_path / "corpus"
    _capture_trace(trace, output, "I will use Manual line for validation.")
    rows = [json.loads(line) for line in trace.read_text().splitlines()]
    rows.insert(2, _command_row(corpus, "cat package:manual", "Manual line.\n", "earlier-read"))
    later_corpus = tmp_path / "later-corpus"
    rows.append(_command_row(later_corpus, "cat package:manual", "Manual line.\n", "later-read"))
    trace.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    inputs = {"number": 1, "trace": trace, "lines": [2, 5],
              "context_ids": ["r1"], "complete": True}
    path = import_search(campaign, knowledge_root=tmp_path / "wrong-corpus",
                         **{status: [("package:manual", 4)]}, **inputs)
    original = json.loads(path.read_text())
    assert original["materials"]["package:manual"]["use"] == "unknown"

    import_search(campaign, knowledge_root=later_corpus, **inputs)
    later_only = json.loads(path.read_text())
    assert later_only["materials"]["package:manual"]["use"] == "unknown"
    declaration, = later_only["materials"]["package:manual"]["declarations"]
    assert declaration["reason"] == "no_prior_ordered_observation"
    assert later_only["counts"]["used"] == 0

    import_search(campaign, knowledge_root=corpus, **inputs)
    corrected = json.loads(path.read_text())
    material = corrected["materials"]["package:manual"]
    assert material["use"] == status and corrected["counts"]["used"] == int(status == "used")
    evidence, = material["evidence"]
    assert evidence["decision_line"] == 4 and "reason" not in evidence
    assert not material.get("declarations")
    saved = path.read_bytes()
    import_search(campaign, knowledge_root=corpus, **inputs)
    assert path.read_bytes() == saved


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
