import hashlib
import json
import shutil
from pathlib import Path

import pytest

from inferrsi.apps.workflows.campaign import create_campaign, save_retrieval, verify_capture
from inferrsi.knowledge.knowledge_find import Corpus, find, load_documents
from inferrsi.knowledge.knowledge_operations import KnowledgeReader
from inferrsi.knowledge.ranking_policy import DEFAULT_RANKING_POLICY, RankingPolicy

CUE = "qxrankprobe"
A, B = "case.qxrankprobe", "case.alternate"
ALTERNATE = RankingPolicy("applicability", {"applicability": 3})
FROZEN_CORPUS = Path(__file__).resolve().parents[1] / "fixtures" / "indexer" / "ranking-corpus"


@pytest.fixture()
def library(tmp_path):
    return shutil.copytree(FROZEN_CORPUS, tmp_path / "library")


@pytest.mark.parametrize(("options", "order", "scores", "source"), [
    ({}, (A, B), (5, 4), "alpha"),
    ({"ranking_policy": ALTERNATE}, (B, A), (6, 5), "bravo"),
])
def test_find_collect_and_retained_context(library, tmp_path, options, order, scores, source):
    reader = KnowledgeReader(skill_root=library)
    corpus = Corpus(load_documents(library, kinds=("case",)))
    hits = find(CUE, corpus, **options)
    assert [(hit["id"], hit["score"]) for hit in hits["items"]] == list(zip(order, scores))

    result = reader.collect(CUE, kind="case", limit=1, context_bytes=2048, **options)
    observed, = result["retrieval"]["items"]
    context, = result["contexts"]
    ref = "checkout:" + order[0]
    assert (observed["ref"], observed["score"], observed["revision"]) == (
        ref, scores[0], reader.read(ref).revision,
    )
    assert (context["ref"], context["revision"]) == (ref, observed["revision"])
    resource = next(r for r in context["resources"] if r["path"] == f"{source}.md")
    raw = reader.resource(ref, resource["path"], revision=observed["revision"])
    assert raw == resource["content"].encode() == f"source {source}\n".encode()
    assert hashlib.sha256(raw).hexdigest() == resource["sha256"]
    assert context["sources"] == result["items"][0]["sources"]
    assert result["retrieval"]["counts"]["excluded"]["item_limit"] == 1

    campaign = tmp_path / "run"
    create_campaign(campaign, "replay")
    path, _ = save_retrieval(campaign, context_id="selected", result=result)
    saved, state = verify_capture(path.read_bytes())
    assert state == "verified"
    assert resource["content"] in saved["assembled_text"]
    assert saved["contexts"][0]["ref"] == ref
    assert saved["contexts"][0]["revision"] == observed["revision"]
    policy = options.get("ranking_policy", DEFAULT_RANKING_POLICY)
    assert hits["ranking_policy"] == saved["retrieval"]["selection"]["ranking_policy"]
    assert saved["selection"]["ranking_policy"] == policy.receipt()

    bounded = reader.collect(CUE, kind="case", limit=1, context_bytes=128, **options)
    assert bounded["retrieval"]["items"] == [observed]
    assert bounded["contexts"] == []
    omission, = bounded["context_omissions"]
    assert (omission["ref"], omission["reason"]) == (ref, "context_limit")


def test_undelivered_corpus_change_preserves_capture_but_changes_ranking(library, tmp_path):
    def collect():
        reader = KnowledgeReader(skill_root=library)
        return reader.collect(f"{CUE} alpha", kind="case", limit=1, context_bytes=2048)

    original = collect()
    campaign = tmp_path / "run"
    create_campaign(campaign, "replay")
    path, _ = save_retrieval(campaign, context_id="original", result=original)

    cases = library / "demo" / "cases"
    extra = json.loads((cases / "alpha.json").read_text(encoding="utf-8"))
    extra.update(id="case.extra", content="extra.md")
    (cases / "extra.json").write_text(json.dumps(extra), encoding="utf-8")
    (cases / "extra.md").write_bytes(f"{CUE}\n".encode())
    changed = collect()

    saved, state = verify_capture(path.read_bytes())
    assert state == "verified"
    assert saved["retrieval"]["items"] == original["retrieval"]["items"]
    before, = saved["retrieval"]["items"]
    after, = changed["retrieval"]["items"]
    assert before["ref"] == after["ref"] == "checkout:" + A
    assert before["revision"] == after["revision"]
    assert before["score"] != after["score"]
    assert original["contexts"] == changed["contexts"]
    assert "source alpha\n" in saved["assembled_text"]
    assert saved["retrieval"]["counts"]["excluded"]["item_limit"] == 1
    assert changed["retrieval"]["counts"]["excluded"]["item_limit"] == 2


def test_explicit_ids_keep_caller_order_under_alternative_policy(library):
    reader = KnowledgeReader(skill_root=library)
    refs = ["checkout:" + A, "checkout:" + B]
    pins = {ref: reader.read(ref).revision for ref in refs}
    result = reader.collect(
        ids=refs, revisions=pins, relevance=CUE, ranking_policy=ALTERNATE, context_bytes=2048,
    )
    assert [view["ref"] for view in result["items"]] == refs
    assert [context["ref"] for context in result["contexts"]] == refs
    assert result["selection"]["ranking_applied"] is False
