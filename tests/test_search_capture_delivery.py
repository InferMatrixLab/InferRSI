import json

import pytest

from inferrsi.apps.views.capture_delivery import (
    capture_event,
    capture_return_texts,
    visible_capture_resources,
)
from inferrsi.apps.views.search_attribution import import_search
from inferrsi.apps.workflows.campaign import capture_context, create_campaign, save_retrieval
from inferrsi.knowledge.catalog import search_knowledge
from inferrsi.knowledge.context_projection import assemble_context_text
from inferrsi.knowledge.knowledge_operations import KnowledgeReader


def _review(path, **fields):
    path.write_text(json.dumps({
        "task": "Check knowledge delivery.",
        "corpus": {"repository": "example/knowledge", "revision": "a" * 40, "root": "."},
        "decisions": [],
        **fields,
    }), encoding="utf-8")
    return path


def test_delivery_requires_a_versioned_resource_block_in_a_model_tool_return(tmp_path):
    context = {
        "ref": "package:case", "revision": "r1", "omissions": [],
        "resources": [
            {"path": "case.md", "content": "Check residency before initializing."},
            {"path": "other.md", "content": "Second resource."},
        ],
    }
    doc = {"contexts": [context]}
    block = assemble_context_text([{**context, "resources": context["resources"][:1]}])
    trace = tmp_path / "trace.jsonl"

    def output(text):
        return {"type": "response_item", "payload": {"type": "custom_tool_call_output",
                "output": [{"type": "input_text", "text": text}]}}

    trace.write_text("\n".join(json.dumps(row) for row in [
        {"type": "session_meta"}, output("knowledge/r1.json"),
        output(block.replace("@ r1", "@ r2")), output(block.rstrip("\n")),
        {"type": "response_item", "payload": {"type": "message", "role": "assistant"}},
    ]))
    for number in (2, 3, 4):
        texts = capture_return_texts(trace, (2, 5), {"r1": number}, ["r1"])
        expected = [{"ref": "package:case", "path": "case.md"}] if number == 4 else []
        assert visible_capture_resources(doc, texts["r1"]) == expected
    with pytest.raises(ValueError, match="model-facing"):
        capture_return_texts(trace, (2, 5), {"r1": 5}, ["r1"])
    with pytest.raises(ValueError, match="outside the round"):
        capture_return_texts(trace, (2, 3), {"r1": 4}, ["r1"])


def test_round_counts_search_but_retains_exact_reads_and_inventory(tmp_path):
    root = tmp_path / "campaign"
    create_campaign(root, "capture-counts")
    reader = KnowledgeReader()
    record = "package:inferrsi.common.skills.cgroup_resource_controls"
    revision = reader.read(record).revision
    capture_context(root, context_id="pin", reader=reader, ids=[record],
                    revisions={record: revision})
    save_retrieval(root, context_id="catalog", result=search_knowledge(limit=1, explain=True))
    capture_context(root, context_id="query", reader=reader, query="cgroupv2", limit=1)

    archive = import_search(
        root, number=1, context_ids=["pin", "catalog", "query"], complete=True,
        archive_review=_review(tmp_path / "review.json"),
    )
    for path in (root / "search/round-1.json", archive):
        saved = json.loads(path.read_bytes())
        assert saved["counts"] == {"searches": 1, "hits": 1, "unique_hits": 1, "used": 0}
        pinned, inventory, discovery = saved["events"]
        assert [event["action"] for event in (pinned, inventory, discovery)] == [
            "read", "inventory", "search",
        ]
        assert pinned["materials"][0]["revision"] == revision
        assert inventory["materials"][0]["revision"].startswith("catalog-sha256:")
        assert discovery["tool"] == "find"


@pytest.mark.parametrize("observation", [
    None,
    {
        "schema_version": 1,
        "request": {"query": "cgroupv2"},
        "selection": {"state": "not_requested", "ranking_applied": False},
    },
])
def test_legacy_capture_remains_search_when_ranking_is_unknown_or_unrequested(observation):
    doc = {"items": [], "contexts": [], "request": {}, "retrieval": observation}
    assert capture_event("legacy", (doc, "knowledge/legacy.json", "a" * 64))["action"] == "search"


def test_archive_accepts_complete_managed_json_at_the_matching_capture(tmp_path):
    root = tmp_path / "campaign"
    create_campaign(root, "managed-return")
    path, digest = capture_context(root, context_id="r1", reader=KnowledgeReader(),
                                   query="NPU OOM after caching per-step masks",
                                   kind="case", limit=1)
    capture = json.loads(path.read_bytes())
    context, = capture["contexts"]
    resource = next(item for item in context["resources"] if item["path"].endswith(".md"))
    reference = {"path": "knowledge/r1.json", "sha256": digest, "kind": "delivered_context"}
    response = {"reference": reference, "context": capture}
    trace = tmp_path / "trace.jsonl"
    quote = "Check the observed residency before choosing a mitigation."

    def write_trace(output):
        rows = [
            {"type": "session_meta", "payload": {"id": "managed-session"}},
            {"type": "response_item", "payload": {"type": "custom_tool_call_output",
              "output": [{"type": "input_text", "text": "Output:\n" + output}]}},
            {"type": "response_item", "payload": {"type": "message", "role": "assistant",
              "phase": "final_answer", "content": [{"type": "output_text", "text": quote}]}},
        ]
        trace.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    review = _review(
        tmp_path / "review.json", capture_returns={"r1": 2},
        decisions=[{"use": "used", "ref": context["ref"], "event_line": 2,
                    "passage_path": resource["path"], "passage_line": 1,
                    "decision_line": 3, "decision_quote": quote}],
    )
    inputs = {
        "number": 1, "context_ids": ["r1"], "trace": trace, "lines": (2, 3),
        "knowledge_root": tmp_path.resolve(), "archive_review": review,
    }
    exact = json.dumps(response, ensure_ascii=False, indent=2)
    for invalid in (
        json.dumps(reference),
        exact.replace(digest, "0" * 64, 1),
        json.dumps({**response, "context": {**capture, "assembled_text": ""}},
                   ensure_ascii=False, indent=2),
        exact[:-1],
    ):
        write_trace(invalid)
        with pytest.raises(ValueError, match="matching visible captured resource"):
            import_search(root, **inputs)
        assert not (root / "search/archive/round-1.json").exists()

    write_trace(exact)
    saved = json.loads(import_search(root, **inputs).read_bytes())
    event, = saved["events"]
    assert event["delivery"]["state"] == "visible"
    assert event["delivery"]["return_line"] == 2
    evidence, = saved["materials"][context["ref"]]["evidence"]
    assert evidence["basis"] == "archive_reviewed"
    assert evidence["passage_path"] == resource["path"]
    assert evidence["passage_text"] == resource["content"].splitlines()[0]
    write_trace(exact.replace("\n", "\r\n"))
    assert json.loads(import_search(root, **inputs).read_bytes()) == saved
