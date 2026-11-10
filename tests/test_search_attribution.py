"""Round boundaries and adoption evidence must survive both public retrieval paths."""

import json

import pytest

from inferrsi.cli import main
from inferrsi.harness.campaign_records import create_campaign
from inferrsi.harness.search_attribution import import_search


def command(corpus, cmd, output, event_id, exit_code=0):
    item = {"type": "CommandExecution", "id": event_id, "cwd": corpus.as_uri(),
            "command": ["/bin/sh", "-lc", cmd], "exit_code": exit_code,
            "aggregated_output": output}
    return {"type": "event_msg", "payload": {"type": "item_completed", "item": item}}


def rollout(path, *events):
    rows = [{"type": "session_meta", "payload": {"id": "example-session"}}, *events]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_cli_distinguishes_search_read_and_decision_in_two_rounds(tmp_path):
    campaign = tmp_path / "campaign"
    corpus, trace = tmp_path / "knowledge", tmp_path / "rollout.jsonl"
    create_campaign(campaign, "example")
    search = command(corpus, "rg -n 'RoPE' .", "case.md:3:private matched text", "search")
    rollout(trace, search, search, command(corpus, "cat case.md", "private body", "read"),
            {"type": "response_item", "payload": {"type": "message", "role": "assistant",
             "phase": "final_answer", "content": [{"type": "output_text", "text": "Apply case."}]}},
            command(corpus, "pwd", str(corpus), "other"))
    args = ["campaign", "import-search", "--directory", str(campaign), "--trace", str(trace),
            "--knowledge-root", str(corpus), "--complete"]
    first = args + ["--round", "1", "--lines", "2", "5", "--used", "case.md", "5"]
    assert main(first) == 0
    path = campaign / "search/round-1.json"
    original = path.read_bytes()
    assert main(first) == 0 and path.read_bytes() == original
    doc = json.loads(original)
    assert doc["counts"] == {"searches": 1, "hits": 1, "unique_hits": 1, "used": 1}
    assert [e["action"] for e in doc["events"]] == ["search", "read"]
    assert doc["events"][0]["materials"] == [{"ref": "case.md", "match_line": 3}]
    assert doc["materials"]["case.md"]["evidence"][0]["decision_line"] == 5
    assert b"private" not in original and str(tmp_path).encode() not in original
    assert main(args + ["--round", "2", "--lines", "6", "6"]) == 0
    assert json.loads((campaign / "search/round-2.json").read_bytes())["counts"]["searches"] == 0
    with pytest.raises(ValueError, match="overlaps"):
        import_search(campaign, number=3, trace=trace, lines=[5, 6], knowledge_root=corpus)
    with pytest.raises(ValueError, match="assistant message"):
        import_search(campaign, number=1, trace=trace, lines=[2, 5], knowledge_root=corpus,
                      used=[("case.md", "2")])


def test_partial_or_missing_capture_does_not_report_zero(tmp_path):
    create_campaign(tmp_path, "example")
    path = import_search(tmp_path, number=1)
    assert json.loads(path.read_bytes())["counts"] is None
    trace, corpus = tmp_path / "rollout.jsonl", tmp_path / "knowledge"
    rollout(trace, command(corpus, "rg --json needle .", "unsupported", "search"))
    path = import_search(tmp_path, number=1, trace=trace, lines=[1, 2],
                         knowledge_root=corpus, complete=True)
    doc = json.loads(path.read_bytes())
    assert doc["coverage"] == "partial" and doc["counts"] is None
    assert doc["unresolved_command_lines"] == [2]
    with pytest.raises(ValueError, match="boundary"):
        import_search(tmp_path, number=1, trace=trace, lines=[1, 3], knowledge_root=corpus)


def test_extend_live_window_and_keep_decision_on_retry(tmp_path):
    create_campaign(tmp_path, "example")
    trace, corpus = tmp_path / "rollout.jsonl", tmp_path / "knowledge"
    rollout(trace, command(corpus, "rg -nH key cases", "cases/a.md:2:key", "search"),
            {"type": "response_item", "payload": {"type": "message", "role": "assistant",
             "phase": "final_answer", "content": [{"text": "Use cases/a.md for validation."}]}})
    inputs = {"number": 1, "trace": trace, "knowledge_root": corpus, "complete": True}
    path = import_search(tmp_path, lines=[1, 2], **inputs)
    assert json.loads(path.read_bytes())["materials"]["cases/a.md"]["use"] == "unknown"
    import_search(tmp_path, lines=[1, 3], used=[("cases/a.md", 3)], **inputs)
    original = path.read_bytes()
    import_search(tmp_path, lines=[1, 3], **inputs)
    assert path.read_bytes() == original


def test_nonmatching_rg_and_incomplete_search_are_distinct(tmp_path):
    create_campaign(tmp_path, "example")
    trace, corpus = tmp_path / "rollout.jsonl", tmp_path / "knowledge"
    rollout(trace, command(corpus, "rg -n absent .", "", "empty", exit_code=1),
            command(corpus, "rg -n key . | head -1", "case.md:2:key", "pipe"))
    inputs = {"trace": trace, "knowledge_root": corpus, "complete": True}
    p = import_search(tmp_path, number=1, lines=[2, 2], **inputs)
    assert json.loads(p.read_bytes())["counts"] == {
        "searches": 1, "hits": 0, "unique_hits": 0, "used": 0}
    p = import_search(tmp_path, number=2, lines=[3, 3], **inputs)
    assert json.loads(p.read_bytes())["counts"] is None


@pytest.mark.parametrize(("cmd", "output", "exit_code", "searches"), [
    ("rg -C 2 key .", "./case.md-context: foo\n./case.md:key", 0, 1),
    ("cat case.md missing.md", "body\ncat: missing.md: not found", 1, 0),
], ids=["unnumbered-context", "partial-cat"])
def test_ambiguous_output_stays_unresolved(tmp_path, cmd, output, exit_code, searches):
    create_campaign(tmp_path, "example")
    trace, corpus = tmp_path / "rollout.jsonl", tmp_path / "knowledge"
    rollout(trace, command(corpus, cmd, output, "example", exit_code=exit_code))
    path = import_search(tmp_path, number=1, trace=trace, lines=[2, 2],
                         knowledge_root=corpus, complete=True)
    doc = json.loads(path.read_bytes())
    assert doc["coverage"] == "partial" and doc["counts"] is None
    assert doc["unresolved_command_lines"] == [2]
    assert doc["observed"]["searches"] == searches
    assert doc["materials"] == {}


def test_numbered_context_preserves_confirmed_hits_under_normalized_root(tmp_path):
    create_campaign(tmp_path, "example")
    trace, corpus = tmp_path / "rollout.jsonl", tmp_path / "knowledge"
    rollout(trace, command(corpus, "rg -Hn -C 1 key .",
                           "./case.md-1-context: foo\n./case.md:2:key", "search"))
    # The historical knowledge directory need not exist on the importing machine.
    path = import_search(tmp_path, number=1, trace=trace, lines=[2, 2],
                         knowledge_root=corpus / "old" / "..", complete=True)
    doc = json.loads(path.read_bytes())
    assert doc["coverage"] == "complete"
    assert doc["events"][0]["materials"] == [{"ref": "case.md", "match_line": 2}]


def test_ambiguous_numbered_context_cannot_invent_another_file(tmp_path):
    create_campaign(tmp_path, "example")
    trace, corpus = tmp_path / "rollout.jsonl", tmp_path / "knowledge"
    rollout(trace, command(corpus, "rg -n -C 1 key .",
                           "./case.md:1:key\n./case.md-2-context:42: more", "search"))
    path = import_search(tmp_path, number=1, trace=trace, lines=[2, 2],
                         knowledge_root=corpus, complete=True)
    doc = json.loads(path.read_bytes())
    assert doc["counts"] is None and doc["unresolved_command_lines"] == [2]
    assert set(doc["materials"]) == {"case.md"}


@pytest.mark.parametrize(("script", "output"), [
    ("rg -Hn key a.md\nrg -Hn key b.md", "a.md:1:key\nb.md:1:key"),
    ("cat a.md\ncat b.md", "first\nsecond"),
])
def test_multiline_shell_does_not_merge_separate_retrievals(tmp_path, script, output):
    create_campaign(tmp_path, "example")
    trace, corpus = tmp_path / "rollout.jsonl", tmp_path / "knowledge"
    rollout(trace, command(corpus, script, output, "compound"))
    path = import_search(tmp_path, number=1, trace=trace, lines=[2, 2],
                         knowledge_root=corpus, complete=True)
    doc = json.loads(path.read_bytes())
    assert doc["counts"] is None and doc["unresolved_command_lines"] == [2]
    assert doc["materials"] == {}


@pytest.mark.parametrize("script", ["rg -n -- --files .", "rg -n -e --files ."])
def test_literal_files_option_is_a_search(tmp_path, script):
    create_campaign(tmp_path, "example")
    trace, corpus = tmp_path / "rollout.jsonl", tmp_path / "knowledge"
    rollout(trace, command(corpus, "rg --files .", "case.md", "inventory"),
            command(corpus, script, "case.md:1:rg --files", "search"))
    path = import_search(tmp_path, number=1, trace=trace, lines=[2, 3],
                         knowledge_root=corpus, complete=True)
    doc = json.loads(path.read_bytes())
    assert doc["counts"] == {"searches": 1, "hits": 1, "unique_hits": 1, "used": 0}
    assert doc["events"][0]["query"] == "--files"
