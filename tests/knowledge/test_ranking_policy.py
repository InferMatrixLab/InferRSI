import math

import pytest

from inferrsi.knowledge._skill_selection import FIND_RELEVANCE
from inferrsi.knowledge.knowledge_find import Corpus, Document, rank
from inferrsi.knowledge.knowledge_operations import KnowledgeReader
from inferrsi.knowledge.ranking_policy import DEFAULT_RANKING_POLICY, RankingPolicy


def test_effective_weights_are_immutable_and_canonical():
    overrides = {"body": -0.0, "applicability": 3}
    policy = RankingPolicy("trial", overrides)
    overrides["body"] = 8
    same = RankingPolicy("trial", {"applicability": 3.0, "body": 0})
    assert policy.receipt() == same.receipt()
    assert policy.configuration()["weights"] == {
        "title": 5, "summary": 4, "tags": 4, "findings": 4, "applicability": 3, "body": 0,
    }
    assert policy.configuration()["version"] == 1
    assert policy.receipt()["config_sha256"] != RankingPolicy("trial").receipt()["config_sha256"]
    with pytest.raises(TypeError):
        policy.weights["title"] = 1


@pytest.mark.parametrize("weights", [
    {"typo": 1}, {"body": False}, {"tags": -1}, {"title": float("nan")}, {"body": float("inf")},
    {"summary": 10**400},
])
def test_invalid_policy_rejected(weights):
    with pytest.raises(ValueError, match="weight"):
        RankingPolicy("trial", weights)


def test_default_preserves_body_length_idf_backend_and_all_tie_breaks():
    docs = [
        Document(name, "record", state, None, name, "", fields, qualified=ref, backend=backend)
        for name, ref, state, fields, backend in [
            ("a", "checkout:a", "candidate", {"body": "probe"}, "ascend"),
            ("b", "checkout:b", "validated", {"body": "probe"}, "ascend"),
            ("a", "store:a", "validated", {"body": "probe"}, "ascend"),
            ("a", "package:a", "validated", {"body": "probe"}, "ascend"),
            ("long", "store:long", "validated", {"body": "probe a b c"}, "cuda"),
            ("none", "store:none", "validated", {"body": "other"}, "ascend"),
        ]
    ]
    corpus = Corpus(docs)
    idf = math.log(7 / 6) + 1
    assert corpus.score(4, ["probe"], query_backend="ascend")[0] == pytest.approx(idf / 4)
    for args in [(), (DEFAULT_RANKING_POLICY,)]:
        _, _, rows = rank("probe", corpus, *args)
        assert [docs[i].qualified for _, _, i, _ in rows] == [
            "package:a", "store:a", "checkout:b", "checkout:a", "store:long",
        ]
        assert [r[0] for r in rows] == pytest.approx([idf] * 4 + [idf / 2])


def test_packaged_service_uses_same_weights_without_content_fingerprints():
    reader = KnowledgeReader()
    args = {"relevance_method": FIND_RELEVANCE, "limit": 1, "context_bytes": 65536}
    implicit = reader.collect_service_context("cgroupv2", **args)
    explicit = reader.collect_service_context(
        "cgroupv2", **args, ranking_policy=DEFAULT_RANKING_POLICY,
    )
    assert implicit == explicit
    context, = implicit["contexts"]
    assert context["ref"] == "package:inferrsi.common.skills.cgroup_resource_controls"
    assert implicit["request"]["ranking_policy"] == DEFAULT_RANKING_POLICY.configuration()
    zero = RankingPolicy("zero", dict.fromkeys(DEFAULT_RANKING_POLICY.weights, 0))
    other = reader.collect_service_context("cgroupv2", **args, ranking_policy=zero)
    assert other["request"]["ranking_policy"] == zero.configuration()
    assert other["contexts"] == []
