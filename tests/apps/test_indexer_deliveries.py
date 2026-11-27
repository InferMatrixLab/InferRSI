import hashlib
import json
import shutil
from pathlib import Path

import pytest

from inferrsi.apps.workflows.campaign import create_campaign, save_retrieval, verify_capture
from inferrsi.knowledge.knowledge_find import Corpus, find, load_documents
from inferrsi.knowledge.knowledge_operations import KnowledgeReader
from inferrsi.knowledge.ranking_policy import DEFAULT_RANKING_POLICY, RankingPolicy
from inferrsi.knowledge.ranking_replay import (
    delivery_difference,
    replay_binding,
    replay_find,
    verify_replay,
)

CUE = "qxrankprobe"
A, B = "case.qxrankprobe", "case.alternate"
ALTERNATE = RankingPolicy("applicability", {"applicability": 3})
# An unregistered candidate with the same weights, frozen by value rather than by name.
CANDIDATE = RankingPolicy("trial-applicability-3", {"applicability": 3})
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
    hits = find(CUE, corpus, pin_material=True, **options)
    assert [(hit["id"], hit["score"]) for hit in hits["items"]] == list(zip(order, scores))

    hit = hits["items"][0]
    result = reader.pack_find_hits([hit], cue=CUE, limit=1, context_bytes=2048, **options)
    observed, = result["retrieval"]["items"]
    context, = result["contexts"]
    ref = "checkout:" + order[0]
    assert (observed["ref"], hit["score"], observed["revision"]) == (
        ref, scores[0], reader.read(ref).revision,
    )
    assert (context["ref"], context["revision"]) == (ref, hit["revision"])
    resource = next(r for r in context["resources"] if r["path"] == f"{source}.md")
    raw = reader.resource(ref, resource["path"], revision=observed["revision"])
    assert raw == resource["content"].encode() == f"source {source}\n".encode()
    assert hashlib.sha256(raw).hexdigest() == resource["sha256"]
    assert context["sources"] == result["items"][0]["sources"]
    assert hits["matched"] == 2 and result["retrieval"]["selection"]["state"] == "explicit_ids"

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

    bounded = reader.pack_find_hits([hit], cue=CUE, limit=1, context_bytes=1, **options)
    assert bounded["retrieval"]["items"] == [observed]
    assert bounded["contexts"] == []
    omission, = bounded["context_omissions"]
    assert (omission["ref"], omission["reason"]) == (ref, "context_limit")


def test_undelivered_corpus_change_preserves_capture_but_changes_ranking(library, tmp_path):
    query = f"{CUE} alpha"
    def discover_and_open():
        reader = KnowledgeReader(skill_root=library)
        found = find(query, Corpus(load_documents(library, kinds=("case",))), limit=1,
                     pin_material=True)
        packed = reader.pack_find_hits(found["items"], cue=query, limit=1, context_bytes=2048)
        return found, packed

    before, original = discover_and_open()
    campaign = tmp_path / "run"
    create_campaign(campaign, "replay")
    path, _ = save_retrieval(campaign, context_id="original", result=original)

    cases = library / "demo" / "cases"
    extra = json.loads((cases / "alpha.json").read_text(encoding="utf-8"))
    extra.update(id="case.extra", content="extra.md")
    (cases / "extra.json").write_text(json.dumps(extra), encoding="utf-8")
    (cases / "extra.md").write_bytes(f"{CUE}\n".encode())
    after, changed = discover_and_open()

    saved, state = verify_capture(path.read_bytes())
    assert state == "verified"
    assert saved["retrieval"]["items"] == original["retrieval"]["items"]
    first, second = before["items"][0], after["items"][0]
    assert first["material_ref"] == second["material_ref"] == "checkout:" + A
    assert first["revision"] == second["revision"] and first["score"] != second["score"]
    assert original["contexts"] == changed["contexts"]
    assert "source alpha\n" in saved["assembled_text"]
    assert before["matched"] == 2 and after["matched"] == 3


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



def _corpus(library):
    return Corpus(load_documents(library, kinds=("case",)))


def _packer(library, query, limit):
    reader = KnowledgeReader(skill_root=library)
    return lambda hits, policy, budget: reader.pack_find_hits(
        hits, cue=query, limit=limit, context_bytes=budget, ranking_policy=policy,
    )


def _retain(library, tmp_path, policy, *, query=CUE, limit=1, context_bytes=2048):
    """Run Find and delivery once, archive the capture and bind the replay inputs."""
    corpus = _corpus(library)
    found = find(query, corpus, limit=limit, pin_material=True, ranking_policy=policy)
    packed = _packer(library, query, limit)(found["items"], policy, context_bytes)
    campaign = tmp_path / f"run-{policy.policy_id}-{limit}-{context_bytes}"
    create_campaign(campaign, "replay")
    path, _ = save_retrieval(campaign, context_id="selected", result=packed)
    binding = replay_binding(query=query, limit=limit, ranking_policy=found["ranking_policy"],
                             corpus=corpus, context_bytes=context_bytes)
    retained = {
        "items": found["items"],
        "delivered": [c["ref"] for c in packed["contexts"]],
        "omitted": [o["ref"] for o in packed["context_omissions"]],
    }
    return binding, retained, path


@pytest.mark.parametrize(("limit", "context_bytes"), [(1, 2048), (2, 2048), (2, 1)])
def test_frozen_candidate_rule_replays_ranking_delivery_and_omissions(
    library, tmp_path, limit, context_bytes,
):
    replays = {}
    for policy in (DEFAULT_RANKING_POLICY, CANDIDATE):
        binding, retained, path = _retain(library, tmp_path, policy, limit=limit,
                                          context_bytes=context_bytes)
        assert verify_capture(path.read_bytes())[1] == "verified"
        assert binding["ranking_policy"] == policy.receipt()
        replay = verify_replay(binding, retained, _corpus(library),
                               pack=_packer(library, CUE, limit))
        assert replay["state"] == "reproduced" and replay["mismatches"] == []
        assert replay["replayed"]["delivered"] == retained["delivered"]
        assert replay["replayed"]["omitted"] == retained["omitted"]
        replays[policy.policy_id] = replay["replayed"]["items"]
    assert replays[CANDIDATE.policy_id][0]["ref"] == "checkout:" + B
    difference = delivery_difference(replays["default"], replays[CANDIDATE.policy_id])
    if limit == 1:
        assert difference == {
            "only_first": ["checkout:" + A], "only_second": ["checkout:" + B], "reordered": False,
        }
    else:
        assert difference == {"only_first": [], "only_second": [], "reordered": True}


def test_archival_verification_and_exact_replay_are_separate(library, tmp_path):
    query = f"{CUE} alpha"
    binding, retained, path = _retain(library, tmp_path, CANDIDATE, query=query, limit=2)
    cases = library / "demo" / "cases"
    extra = json.loads((cases / "alpha.json").read_text(encoding="utf-8"))
    extra.update(id="case.extra", content="extra.md")
    (cases / "extra.json").write_text(json.dumps(extra), encoding="utf-8")
    (cases / "extra.md").write_bytes(f"{CUE}\n".encode())

    # Archival check: the retained capture is intact even though the corpus changed.
    assert verify_capture(path.read_bytes())[1] == "verified"
    # Exact replay: the top delivered item is unchanged, but the corpus is not the one searched.
    pack = _packer(library, query, 2)
    replay = verify_replay(binding, retained, _corpus(library), pack=pack)
    assert replay["replayed"]["delivered"][0] == retained["delivered"][0]
    assert replay["state"] == "corpus_changed"

    for missing in ("corpus_sha256", "context_bytes", "scoring_version"):
        with pytest.raises(ValueError, match=f"lacks {missing}"):
            replay_find({k: v for k, v in binding.items() if k != missing}, _corpus(library))
    changed = {**binding["ranking_policy"], "weights": {
        **binding["ranking_policy"]["weights"], "applicability": 4.0,
    }}
    with pytest.raises(ValueError, match="digest does not match"):
        replay_find({**binding, "ranking_policy": changed}, _corpus(library))
    stale = verify_replay({**binding, "scoring_version": binding["scoring_version"] + 1},
                          retained, _corpus(library), pack=pack)
    assert stale["state"] == "scoring_changed"
