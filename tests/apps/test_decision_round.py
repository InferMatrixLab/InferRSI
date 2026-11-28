"""Issue 529 round acceptance against the actual offline corpus and pinned evidence."""

import json
from hashlib import sha256
from pathlib import Path

import pytest

from inferrsi.apps.cli import main
from inferrsi.apps.workflows.decision_round import decision_round
from inferrsi.knowledge.knowledge_operations import (
    KnowledgeReader,
    PageBudgetTooSmall,
    UnavailableResource,
    UnavailableRevision,
)

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / "docs/reviews/knowledge-retrieval"
QUERY = "first audio packet streaming measurement chunk gaps"
REF = "package:vllm_omni.common.audio.streaming_serving_measurement"


def request(query=QUERY, **kwargs):
    return dict(
        task="task-accuracy",
        round=1,
        decision="Choose a timing endpoint.",
        query=query,
        questions=["Endpoint?"],
        next_action="Collect event timestamps.",
        **kwargs,
    )


def pick(**kwargs):
    return dict(
        ref=REF, purpose="method", question="Endpoint?", reason="Defines endpoints.", **kwargs
    )


@pytest.mark.parametrize("name", ["tts-regression", "version-migration"])
def test_reviewed_pilots_read_back_the_quoted_bytes(name, capsys):
    path = REVIEW / "pilots" / (name + ".json")
    assert main(["knowledge", "round", str(path)]) == 0
    run = json.loads(capsys.readouterr().out)
    review = path.with_suffix(".md").read_text()
    assert run["stop"] == "awaiting_measurement" and run["retrieval_stop"] == "questions_addressed"
    assert run["unanswered"] == [] and run["missing_measurements"] and run["next_action"]
    for answers in run["questions"].values():
        for answer in answers:
            resource = run["resources"][answer["resource_index"]]
            assert resource["revision"] in review and resource["ref"] in review
            assert answer["quote"] in resource["content"] and answer["quote"] in review
            assert resource["sha256"] == sha256(resource["content"].encode()).hexdigest()


def test_no_hits_and_budgeted_followup():
    query = "zzzxqvwyzzzx qzxvvx"
    queries = [{"query": query}, {"query": "ZZZXQVWYZZZX  qzxvvx"}, {"query": QUERY}]
    out = decision_round(KnowledgeReader(), request(query, queries=queries, budget={"queries": 1}))
    assert out["retrieval_stop"] == "query_budget" and out["bytes_used"] == 0
    assert [a["status"] for a in out["attempts"]] == ["no_hits", "duplicate_query"]
    empty = decision_round(KnowledgeReader(), request(query))
    assert empty["stop"] == "no_hits" and empty["unanswered_verdict"] == {"Endpoint?": "unknown"}


def test_reject_stale_missing_and_unlisted_without_delivery():
    selects = [
        pick(revision="sha256:" + "0" * 64),
        pick(resource="absent.md"),
        {**pick(), "ref": "package:unlisted"},
    ]
    out = decision_round(
        KnowledgeReader(), request(queries=[dict(query=QUERY, selections=selects)])
    )
    assert [s["status"] for s in out["attempts"][0]["selections"]] == [
        "unavailable_revision",
        "unavailable_resource",
        "outside_results",
    ]
    assert out["unanswered"] and out["bytes_used"] == 0


def test_duplicate_resource_across_queries_and_only_delivered_passages_can_be_adopted():
    queries = [{"query": QUERY}, {"query": "first audio packet streaming quality"}]

    def select(query, hits, answers):
        assert any(h["material_ref"] == REF for h in hits)
        return [pick()]

    def assess(choice, resource):
        # A fresh decision uses bytes actually delivered, after the selection step.
        return dict(
            quote="absent from the source",
            claim="Both endpoints are the same.",
            verdict="match",
            adopted=True,
        )

    out = decision_round(KnowledgeReader(), request(queries=queries), select=select, assess=assess)
    first, second = [a["selections"][0] for a in out["attempts"]]
    assert first["status"] == "delivered" and second["status"] == "reused"
    assert second["assessment_error"] == "quote_not_delivered" and not second["adopted"]
    (resource,) = out["resources"]
    assert out["unanswered"] and out["bytes_used"] == len(resource["content"].encode())


def test_partial_delivery_obeys_byte_budget():
    req = request(budget={"bytes": 17}, queries=[dict(query=QUERY, selections=[pick()])])
    out = decision_round(KnowledgeReader(), req)
    assert out["bytes_used"] == 17 and out["resources"][0]["partial"]
    assert out["stop"] == "byte_budget" and out["unanswered"]


@pytest.mark.parametrize(("error_type", "reason"), [
    (FileNotFoundError, "unavailable_resource"),
    (UnavailableResource, "unavailable_resource"),
    (UnavailableRevision, "unavailable_revision"),
    (PageBudgetTooSmall, "byte_budget"),
])
def test_later_page_failure_preserves_delivered_bytes_without_error_text(
    error_type, reason, monkeypatch, tmp_path,
):
    reader = KnowledgeReader()
    read_hit = reader.read_hit
    private_path = str(tmp_path / "private-source.md")
    first_page = []

    def fail_after_first_page(hit, *, resource, byte_range):
        start, length = byte_range
        if start:
            raise error_type(private_path)
        view, context = read_hit(hit, resource=resource, byte_range=(0, min(length, 17)))
        assert view["next_byte_range"]
        first_page.append(view["content"])
        return view, context

    monkeypatch.setattr(reader, "read_hit", fail_after_first_page)
    out = decision_round(reader, request(queries=[dict(query=QUERY, selections=[pick()])]))
    body, = out["resources"]
    assert body["partial"] and body["omission"] == reason
    assert [body["content"]] == first_page
    assert 0 < body["bytes"] == len(body["content"].encode()) == out["bytes_used"]
    assert body["sha256"] == sha256(body["content"].encode()).hexdigest()
    assert private_path not in json.dumps(out)
    stop = "byte_budget" if reason == "byte_budget" else "query_plan_exhausted"
    assert out["retrieval_stop"] == stop


def test_hardware_and_task_directories_open_one_pinned_source():
    nav = ROOT / "docs/guides/knowledge/navigation"
    entries = json.loads((REVIEW / "inventory.json").read_text())["entries"]
    ids = [e["discovery_ref"] for e in entries]
    assert ids == sorted(set(ids))
    row = next(e for e in entries if e["id"] == "ascend-aclgraph-capture-replay")
    for directory in ("tasks", "hardware/ascend"):
        page = nav / directory / "index.md"
        (card,) = [line for line in page.read_text().splitlines() if row["ref"] in line]
        assert row["revision"] in card and row["resource"] in card
        target = card.split("](", 1)[1].split(")", 1)[0]
        assert (page.parent / target).resolve() == ROOT / row["source"]
    reader = KnowledgeReader()
    body = reader.resource(row["ref"], row["resource"], revision=row["revision"])
    assert body == (ROOT / row["source"]).read_bytes()


def test_manual_campaign_retains_round_and_search_reference(tmp_path):
    (tmp_path / "campaign.json").write_text(json.dumps({"campaign_id": "pilot"}))
    plan = request(queries=[dict(query=QUERY, selections=[pick()])])
    run = decision_round(KnowledgeReader(), plan, session=tmp_path)
    search = run["attempts"][0]["receipt"]
    (read,) = run["resources"][0]["receipts"]
    captured = json.loads((tmp_path / read["path"]).read_bytes())
    assert captured["request"]["decision_round"] == run["round"]
    assert captured["request"]["search_ref"] == search["path"]


def test_assessor_cannot_change_stored_source_bytes():
    def edit(choice, resource):
        resource["content"] = "invented evidence"
        return dict(quote=resource["content"], claim="Adopt", verdict="match", adopted=True)

    plan = request(queries=[dict(query=QUERY, selections=[pick()])])
    run = decision_round(KnowledgeReader(), plan, assess=edit)
    assert "invented evidence" not in run["resources"][0]["content"]
    assert run["unanswered"] == ["Endpoint?"]


def test_unknown_assessment_keeps_followup_open():
    quote = "first media packet"
    queries = [
        dict(
            query=QUERY,
            selections=[
                pick(
                    assessment=dict(
                        quote=quote, claim="Local timing boundary is unknown.", verdict="unknown"
                    )
                )
            ],
        ),
        dict(
            query="first audio packet streaming quality",
            selections=[
                pick(
                    assessment=dict(
                        quote=quote, claim="Measure first media packet.", verdict="analogue"
                    )
                )
            ],
        ),
    ]
    run = decision_round(KnowledgeReader(), request(queries=queries))
    assert [a["verdict"] for a in run["questions"]["Endpoint?"]] == ["unknown", "analogue"]
    assert run["attempts"][1]["selections"][0]["status"] == "reused"
