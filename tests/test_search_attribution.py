"""Round boundaries and adoption evidence must survive both public retrieval paths."""

import json
import runpy
from pathlib import Path

import pytest

from inferrsi.apps.cli import main
from inferrsi.apps.views.capture_delivery import load_campaign_capture, managed_envelopes
from inferrsi.apps.views.retrieval_projection import _valid_adoption
from inferrsi.apps.views.search_attribution import _adoption, import_search
from inferrsi.apps.workflows.campaign import capture_context, create_campaign
from inferrsi.harness.records.optimization_log import record_log

FIXTURE = runpy.run_path(str(Path(__file__).parent / "fixtures/knowledge_retrieval.py"))


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
    # The later read of a hit stays search-hit adoption, not a direct read.
    assert doc["adoption"] == {
        "search_hits": {"adopted": 1, "unique_hits": 1, "state": "complete"},
        "direct_reads": {"adopted": 0, "read_only": 0, "state": "not_applicable"},
        "unverified_reads": {"adopted": 0, "refs": 0},
        "other_adopted": 0, "attribution_unknown": 0, "unique_hit_revisions": None}
    assert main(args + ["--round", "2", "--lines", "6", "6"]) == 0
    second = json.loads((campaign / "search/round-2.json").read_bytes())
    assert second["counts"]["searches"] == 0
    assert second["adoption"]["search_hits"] == {
        "adopted": 0, "unique_hits": 0, "state": "not_applicable"}
    assert second["adoption"]["unique_hit_revisions"] == 0
    with pytest.raises(ValueError, match="overlaps"):
        import_search(campaign, number=3, trace=trace, lines=[5, 6], knowledge_root=corpus)
    with pytest.raises(ValueError, match="assistant message"):
        import_search(campaign, number=1, trace=trace, lines=[2, 5], knowledge_root=corpus,
                      used=[("case.md", "2")])


@pytest.mark.parametrize("complete", [True, False])
def test_direct_read_adoption_is_not_search_conversion(tmp_path, complete):
    create_campaign(tmp_path, "example")
    trace, corpus = tmp_path / "rollout.jsonl", tmp_path / "knowledge"
    rollout(trace, command(corpus, "rg -n absent .", "", "empty", exit_code=1),
            command(corpus, "cat case.md", "body", "read"),
            {"type": "response_item", "payload": {"type": "message", "role": "assistant",
             "phase": "final_answer", "content": [{"text": "Apply case.md."}]}})
    path = import_search(tmp_path, number=1, trace=trace, lines=[2, 4], knowledge_root=corpus,
                         complete=complete, used=[("case.md", 4)])
    doc = json.loads(path.read_bytes())
    assert doc["observed"] == {"searches": 1, "hits": 0, "unique_hits": 0, "used": 1}
    adoption = doc["adoption"]
    if complete:
        assert doc["counts"] == doc["observed"]
        # A zero search denominator is not applicable, never 0% or above 100%.
        assert adoption == {
            "search_hits": {"adopted": 0, "unique_hits": 0, "state": "not_applicable"},
            "direct_reads": {"adopted": 1, "read_only": 1, "state": "complete"},
            "unverified_reads": {"adopted": 0, "refs": 0},
            "other_adopted": 0, "attribution_unknown": 0, "unique_hit_revisions": 0}
    else:
        assert doc["coverage"] == "partial" and doc["counts"] is None
        assert {adoption[k]["state"] for k in ("search_hits", "direct_reads")} == {"unknown"}
        assert adoption["unique_hit_revisions"] is None


def test_version_count_is_separate_from_per_ref_adoption():
    def search(ref, revision=None):
        row = {"ref": ref} if revision is None else {"ref": ref, "revision": revision}
        return {"action": "search", "materials": [row]}

    events = [search("a", "r1"), search("a", "r2"), search("b", "r1"),
              {"action": "inventory", "materials": [{"ref": "c", "revision": "r1"}]},
              {"action": "read", "materials": [{"ref": "a", "revision": "r2"}]}]
    materials = {"a": {"use": "used"}, "b": {"use": "unknown"},
                 "c": {"use": "used_and_rejected"}}
    adoption = _adoption(events, materials, "complete")
    # Two revisions of one adopted ref are one adopted ref, not two.
    assert adoption == {
        "search_hits": {"adopted": 1, "unique_hits": 2, "state": "complete"},
        "direct_reads": {"adopted": 0, "read_only": 0, "state": "not_applicable"},
        "unverified_reads": {"adopted": 0, "refs": 0},
        "other_adopted": 1, "attribution_unknown": 0, "unique_hit_revisions": 3}
    assert sum(adoption[k]["adopted"] for k in ("search_hits", "direct_reads")) + adoption[
        "other_adopted"] == 2
    unversioned = _adoption([*events, search("d")], {**materials, "d": {"use": "unknown"}},
                            "complete")
    assert unversioned["search_hits"]["unique_hits"] == 3
    assert unversioned["unique_hit_revisions"] is None


def _observed(action, revision, **extra):
    row = {"ref": "a"} if revision is None else {"ref": "a", "revision": revision}
    return {"action": action, "materials": [row], **extra}


HIT = _observed("search", "r1", id="file-2", trace_line=2)
OTHER_REVISION = _observed("read", "r2", id="file-3", trace_line=3)
HIT_REVISION = _observed("read", "r1", id="file-3", trace_line=3)
PREPARED = _observed("read", "r2", context_id="explicit")
RETURN = {"delivery": {"state": "visible", "return_line": 3,
                       "visible_resources": [{"ref": "a", "path": "SKILL.md"}]}}
DELIVERED = {**PREPARED, **RETURN}
PREPARED_HIT = _observed("read", "r1", context_id="explicit")
DELIVERED_HIT = {**PREPARED_HIT, **RETURN}
REVIEWED = {"basis": "archive_reviewed", "decision_line": 4}
LOGGED = {"context_id": "explicit", "stage": "knowledge"}


@pytest.mark.parametrize(("second", "evidence", "credited", "read_only", "unverified"), [
    # Use cited from a read of another revision is not search conversion.
    (OTHER_REVISION, {**REVIEWED, "event_id": "file-3"}, "direct", 1, 0),
    (OTHER_REVISION, {**REVIEWED, "event_id": "file-2"}, "search", 1, 0),
    # A read of the hit's own revision stays search-hit adoption.
    (HIT_REVISION, {**REVIEWED, "event_id": "file-3"}, "search", 0, 0),
    # A decision after both observations cannot be attributed to either one.
    (OTHER_REVISION, {"basis": "caller_reviewed", "decision_line": 4}, "unknown", 1, 0),
    (OTHER_REVISION, {"basis": "caller_reviewed", "decision_line": 3}, "search", 1, 0),
    # Without a locator, use is matched to every observation of the ref.
    (OTHER_REVISION, None, "unknown", 1, 0),
    # A locator that names no observation does not fall back to the ref's others.
    (HIT_REVISION, {**REVIEWED, "event_id": "missing"}, "unknown", 0, 0),
    (DELIVERED_HIT, {**LOGGED, "context_id": "missing"}, "unknown", 0, 0),
    # An explicit-ID capture is a read only when its return of the ref was observed.
    (PREPARED, LOGGED, "unverified_read", 0, 1),
    (DELIVERED, LOGGED, "direct", 1, 0),
    (PREPARED, None, "search", 0, 1),
    # Delivery is checked before the revision match, so the hit keeps its
    # denominator but an unreturned capture of the same revision is not its read.
    (PREPARED_HIT, LOGGED, "unverified_read", 0, 1),
    (DELIVERED_HIT, LOGGED, "search", 0, 0),
], ids=["read-other-revision", "hit-other-revision", "read-hit-revision", "ambiguous-decision",
        "decision-after-hit", "no-locator", "unresolved-event", "unresolved-capture",
        "prepared-capture", "delivered-capture", "hit-outranks-prepared",
        "prepared-hit-revision", "delivered-hit-revision"])
def test_use_is_credited_to_the_observation_its_evidence_cites(
        second, evidence, credited, read_only, unverified):
    material = {"use": "used"}
    if evidence is not None:
        material["evidence"] = [{"use": "used", **evidence}]
    adoption = _adoption([HIT, second], {"a": material}, "complete")
    adopted = {"search": adoption["search_hits"]["adopted"],
               "direct": adoption["direct_reads"]["adopted"],
               "unverified_read": adoption["unverified_reads"]["adopted"],
               "other": adoption["other_adopted"], "unknown": adoption["attribution_unknown"]}
    assert adopted == {kind: int(kind == credited) for kind in adopted}
    # Ref-level totals do not change with the attribution.
    assert adoption["search_hits"]["unique_hits"] == 1
    assert adoption["direct_reads"]["read_only"] == read_only
    assert adoption["unverified_reads"]["refs"] == unverified
    states = {adoption[key]["state"] for key in ("search_hits", "direct_reads")}
    assert (states == {"unknown"}) == (credited == "unknown")
    assert _valid_adoption(adoption, "complete", {"unique_hits": 1, "used": 1})


@pytest.mark.parametrize(("hit", "read"), [(None, "r2"), ("r1", None), (None, None)])
@pytest.mark.parametrize("returned", [True, False])
def test_missing_revision_does_not_make_a_separate_direct_read(hit, read, returned):
    capture = _observed("read", read, context_id="explicit", **(RETURN if returned else {}))
    material = {"use": "used", "evidence": [{"use": "used", **LOGGED}]}
    adoption = _adoption([_observed("search", hit), capture], {"a": material}, "complete")
    # Only a wholly unversioned ref is matched as a whole. When one side records a
    # revision, the read is neither shown to be the hit's nor shown to differ.
    mixed = returned and (hit is None) != (read is None)
    state = "unknown" if mixed else None
    assert adoption["direct_reads"] == {"adopted": 0, "read_only": 0,
                                        "state": state or "not_applicable"}
    # The hit keeps its denominator either way.
    assert adoption["search_hits"] == {"adopted": int(returned and not mixed), "unique_hits": 1,
                                       "state": state or "complete"}
    assert adoption["attribution_unknown"] == int(mixed)
    assert adoption["unverified_reads"] == {"adopted": int(not returned),
                                            "refs": int(not returned)}
    assert adoption["unique_hit_revisions"] == (None if hit is None else 1)
    assert _valid_adoption(adoption, "complete", {"unique_hits": 1, "used": 1})


FIND = _observed("search", None, id="find", trace_line=2)
VERSIONED_READ = _observed("read", "r2", id="read", trace_line=3)


@pytest.mark.parametrize(("evidence", "credited"), [
    # Use evidence that names only the versioned Read does not show which
    # revision the unversioned Find returned.
    ({**REVIEWED, "event_id": "read"}, "unknown"),
    ({"basis": "caller_reviewed", "decision_line": 4}, "unknown"),
    (None, "unknown"),
    # Evidence that names the Find itself is the hit's adoption.
    ({**REVIEWED, "event_id": "find"}, "search"),
    ({"basis": "caller_reviewed", "decision_line": 3}, "search"),
], ids=["read-event", "decision-after-both", "no-locator", "find-event", "decision-after-find"])
def test_unversioned_find_then_versioned_read_is_not_search_adoption(evidence, credited):
    material = {"use": "used"}
    if evidence is not None:
        material["evidence"] = [{"use": "used", **evidence}]
    adoption = _adoption([FIND, VERSIONED_READ], {"a": material}, "complete")
    unknown = credited == "unknown"
    assert adoption["search_hits"] == {"adopted": int(not unknown), "unique_hits": 1,
                                       "state": "unknown" if unknown else "complete"}
    assert adoption["direct_reads"] == {"adopted": 0, "read_only": 0,
                                        "state": "unknown" if unknown else "not_applicable"}
    assert adoption["attribution_unknown"] == int(unknown)
    assert adoption["unique_hit_revisions"] is None
    assert _valid_adoption(adoption, "complete", {"unique_hits": 1, "used": 1})
    # Without use, the hit still counts once and no direct read is invented.
    unused = _adoption([FIND, VERSIONED_READ], {"a": {"use": "unknown"}}, "complete")
    assert unused["search_hits"] == {"adopted": 0, "unique_hits": 1, "state": "complete"}
    assert unused["direct_reads"] == {"adopted": 0, "read_only": 0, "state": "not_applicable"}
    assert unused["attribution_unknown"] == 0


def _explicit_capture(root):
    create_campaign(root, "example")
    with FIXTURE["reader"](root / "corpus") as source:
        ref = "package:" + next(iter(source.records()))
        capture_context(root, context_id="explicit", reader=source, ids=[ref],
                        context_bytes=4096)
    return load_campaign_capture(root, "example", "explicit")


@pytest.mark.parametrize("returned", [False, True])
def test_explicit_id_capture_is_a_direct_read_only_after_an_observed_return(tmp_path, returned):
    captured = _explicit_capture(tmp_path)
    inputs = {"number": 1, "context_ids": ["explicit"], "complete": True}
    if returned:
        trace = tmp_path / "rollout.jsonl"
        rollout(trace, {"type": "response_item", "payload": {
            "type": "function_call_output", "call_id": "example",
            "output": managed_envelopes({"explicit": captured})["explicit"]}})
        inputs.update(trace=trace, lines=[2, 2], knowledge_root=tmp_path / "corpus")
    doc = json.loads(import_search(tmp_path, **inputs).read_bytes())
    event, = doc["events"]
    assert doc["coverage"] == "complete" and event["action"] == "read"
    assert ("delivery" in event) == returned
    # A prepared selection with no observed return is not reported as 0 of 1 reads.
    assert doc["adoption"]["direct_reads"] == (
        {"adopted": 0, "read_only": 1, "state": "complete"} if returned
        else {"adopted": 0, "read_only": 0, "state": "not_applicable"})
    assert doc["adoption"]["unverified_reads"] == {"adopted": 0, "refs": int(not returned)}


def test_logged_use_of_an_unreturned_capture_of_a_hit_is_not_search_adoption(tmp_path):
    create_campaign(tmp_path, "example")
    digests = {}
    with FIXTURE["reader"](tmp_path / "corpus") as source:
        ref = "package:" + next(iter(source.records()))
        for key, options in (("search", {"relevance": "launch"}), ("explicit", {"ids": [ref]})):
            _, digests[key] = capture_context(tmp_path, context_id=key, reader=source,
                                              context_bytes=4096, **options)
    log = {"schema_version": 2, "reviewed_by_caller": True, "campaign_id": "example",
           "goal": {"statement": "Example", "metric": "latency"},
           "knowledge": [{"context_id": key, "sha256": digest, "stage": "knowledge",
                          "purpose": "Example", "takeaways": [],
                          "used_refs": [ref] if key == "explicit" else []}
                         for key, digest in digests.items()],
           "search_space": {"state": "partial", "missing_reason": "Example", "dimensions": []},
           "iterations": [{"round": 1, "hypothesis": "Example", "rationale": "Example",
                           "knowledge_refs": [], "context_ids": list(digests),
                           "candidates": [{"candidate_id": "a", "option_ids": [],
                                           "why": "Example"}],
                           "decision": {"outcome": "pending", "reason": "Example"}}],
           "summary": {"state": "partial", "missing_reason": "Example", "successes": [],
                       "failures": [], "lessons": [], "limitations": []}}
    (tmp_path / "log-input.json").write_text(json.dumps(log), encoding="utf-8")
    record_log(tmp_path, tmp_path / "log-input.json")
    doc = json.loads(import_search(tmp_path, number=1, context_ids=list(digests),
                                   complete=True).read_bytes())
    search, read = doc["events"]
    hits = {row["ref"]: row["revision"] for row in search["materials"]}
    # The log names the explicit-ID capture of the hit's own revision, which was never returned.
    assert search["action"] == "search" and read["action"] == "read" and "delivery" not in read
    assert [(row["ref"], row["revision"]) for row in read["materials"]] == [(ref, hits[ref])]
    assert doc["materials"][ref]["evidence"][0]["context_id"] == "explicit"
    adoption = doc["adoption"]
    assert adoption["search_hits"] == {"adopted": 0, "unique_hits": len(hits),
                                       "state": "complete"}
    assert adoption["direct_reads"] == {"adopted": 0, "read_only": 0, "state": "not_applicable"}
    assert adoption["unverified_reads"] == {"adopted": 1, "refs": 1}
    assert _valid_adoption(adoption, "complete", doc["counts"])


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


@pytest.mark.parametrize(("same_session", "same_event"), [
    (True, True), (True, False), (False, True),
])
def test_disjoint_rounds_cannot_reuse_one_session_command(tmp_path, same_session, same_event):
    create_campaign(tmp_path, "example")
    trace, corpus = tmp_path / "rollout.jsonl", tmp_path / "knowledge"
    rollout(trace, command(corpus, "rg -Hn key .", "guide.md:1:key\n", "search"),
            command(corpus, "rg -Hn key .", "guide.md:1:key\n",
                    "search" if same_event else "another-search"))
    inputs = {"trace": trace, "knowledge_root": corpus, "complete": True}
    first = import_search(tmp_path, number=1, lines=[2, 2], **inputs)
    original = first.read_bytes()
    assert json.loads(original)["counts"]["searches"] == 1
    if not same_session:
        rows = [json.loads(line) for line in trace.read_text().splitlines()]
        rows[0]["payload"]["id"] = "another-session"
        other_trace = tmp_path / "another-rollout.jsonl"
        other_trace.write_text("".join(json.dumps(row) + "\n" for row in rows))
        inputs["trace"] = other_trace
    if same_session and same_event:
        with pytest.raises(ValueError, match="command event.*another round"):
            import_search(tmp_path, number=2, lines=[3, 3], **inputs)
        assert not (tmp_path / "search/round-2.json").exists()
    else:
        second = import_search(tmp_path, number=2, lines=[3, 3], **inputs)
        assert json.loads(second.read_text())["counts"]["searches"] == 1
    assert first.read_bytes() == original


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


@pytest.mark.parametrize("status", ["used", "rejected"])
def test_local_decision_cannot_precede_its_first_observation(tmp_path, status):
    create_campaign(tmp_path, "example")
    trace, corpus = tmp_path / "rollout.jsonl", tmp_path / "knowledge"
    rollout(trace,
            {"type": "response_item", "payload": {"type": "message", "role": "assistant",
             "phase": "final_answer", "content": [{"text": "Decide about case.md."}]}},
            command(corpus, "pwd", str(corpus), "other"),
            command(corpus, "rg -nH key .", "case.md:1:key", "search"))
    with pytest.raises(ValueError, match="decision must follow.*observation"):
        import_search(tmp_path, number=1, trace=trace, lines=[2, 4],
                      knowledge_root=corpus, complete=True, **{status: [("case.md", 2)]})
    assert not (tmp_path / "search/round-1.json").exists()


def test_local_decision_can_precede_a_later_repeat_observation(tmp_path):
    create_campaign(tmp_path, "example")
    trace, corpus = tmp_path / "rollout.jsonl", tmp_path / "knowledge"
    rollout(trace, command(corpus, "rg -nH key .", "case.md:1:key", "first"),
            {"type": "response_item", "payload": {"type": "message", "role": "assistant",
             "phase": "final_answer", "content": [{"text": "Use case.md."}]}},
            command(corpus, "rg -nH key .", "case.md:1:key", "repeat"))
    path = import_search(tmp_path, number=1, trace=trace, lines=[2, 4],
                         knowledge_root=corpus, complete=True, used=[("case.md", 3)])
    assert json.loads(path.read_text())["counts"]["used"] == 1


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
