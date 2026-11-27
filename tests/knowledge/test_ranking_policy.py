import math
import sys

import pytest

from inferrsi.knowledge.knowledge_find import Corpus, Document, rank
from inferrsi.knowledge.knowledge_operations import KnowledgeReader
from inferrsi.knowledge.ranking_policy import (
    DEFAULT_RANKING_POLICY,
    MANAGED_RANKING_POLICIES,
    RankingPolicy,
    RankingSpace,
)


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


def test_packaged_service_uses_same_weights_without_content_fingerprints(tmp_path):
    from inferrsi.harness.records.service_io import no_fingerprints

    reader = KnowledgeReader()
    selected = reader.find(
        "cgroupv2", limit=1, retained_source=tmp_path / "find-default",
        ranking_policy=DEFAULT_RANKING_POLICY,
    )
    no_fingerprints(selected)
    hit, = selected["items"]
    assert hit["material_ref"] == "package:inferrsi.common.skills.cgroup_resource_controls"
    assert selected["ranking_policy"] == DEFAULT_RANKING_POLICY.configuration()
    zero = RankingPolicy("zero", dict.fromkeys(DEFAULT_RANKING_POLICY.weights, 0))
    other = reader.find(
        "cgroupv2", limit=1, retained_source=tmp_path / "find-zero", ranking_policy=zero,
    )
    assert other["ranking_policy"] == zero.configuration()
    assert other["items"] == []


def test_service_rejects_finite_weights_that_overflow_a_score(tmp_path):
    weights = dict.fromkeys(DEFAULT_RANKING_POLICY.weights, sys.float_info.max)
    policy = RankingPolicy("large", weights)
    with pytest.raises(ValueError, match="Ranking score overflow for policy 'large'"):
        KnowledgeReader().find(
            "cgroupv2", limit=1, retained_source=tmp_path / "find-overflow", ranking_policy=policy,
        )


@pytest.mark.parametrize(
    "policy", [*MANAGED_RANKING_POLICIES.values(), RankingPolicy("t", {"body": 0})]
)
def test_frozen_configuration_and_receipt_rebuild_the_same_policy(policy):
    for frozen in (policy.configuration(), policy.receipt()):
        rebuilt = RankingPolicy.from_configuration(frozen)
        assert rebuilt == policy
        assert rebuilt.receipt() == policy.receipt()


def test_named_policy_receipts_are_unchanged():
    assert DEFAULT_RANKING_POLICY.receipt() == {
        "id": "default", "version": 1,
        "weights": {"title": 5.0, "summary": 4.0, "tags": 4.0, "findings": 4.0,
                    "applicability": 2.0, "body": 1.0},
        "config_sha256": RankingPolicy.from_configuration(
            DEFAULT_RANKING_POLICY.configuration()).receipt()["config_sha256"],
    }
    applicability = MANAGED_RANKING_POLICIES["applicability"].configuration()
    assert applicability["weights"]["applicability"] == 3.0


def _receipt(**changes):
    receipt = RankingPolicy("candidate", {"applicability": 3}).receipt()
    return {**receipt, **changes}


@pytest.mark.parametrize("frozen, message", [
    ([], "mapping"),
    (_receipt(extra=1), "id, version and weights only"),
    ({"id": "candidate", "weights": DEFAULT_RANKING_POLICY.configuration()["weights"]},
     "id, version and weights only"),
    (_receipt(version=2), "version 2 differs"),
    (_receipt(version=True), "version True differs"),
    (_receipt(weights={"title": 5.0}), "every weight field"),
    (_receipt(weights={**DEFAULT_RANKING_POLICY.weights, "typo": 1.0}), "every weight field"),
    (_receipt(weights={**DEFAULT_RANKING_POLICY.weights, "body": -1.0}), "weight for body"),
    (_receipt(weights={**DEFAULT_RANKING_POLICY.weights, "body": True}), "weight for body"),
    (_receipt(id="bad id"), "identifier"),
    (_receipt(config_sha256="0" * 64), "digest does not match"),
    (_receipt(weights={**DEFAULT_RANKING_POLICY.weights, "applicability": 4.0}),
     "digest does not match"),
])
def test_frozen_configuration_rejects_drift_and_malformed_input(frozen, message):
    with pytest.raises(ValueError, match=message):
        RankingPolicy.from_configuration(frozen)


def test_ranking_space_accepts_on_grid_weights_and_fixes_the_rest():
    space = RankingSpace({"applicability": (0, 6, 0.5), "body": (0.0, 2, 1)})
    assert space.check(RankingPolicy("a", {"applicability": 3.5, "body": 2})).policy_id == "a"
    assert space.check(DEFAULT_RANKING_POLICY) is DEFAULT_RANKING_POLICY
    assert space.document() == {
        "version": 1,
        "fixed": {"title": 5.0, "summary": 4.0, "tags": 4.0, "findings": 4.0},
        "bounds": {"applicability": [0.0, 6.0, 0.5], "body": [0.0, 2.0, 1.0]},
    }
    same = RankingSpace({"body": [0, 2, 1], "applicability": (0.0, 6.0, 0.5)})
    assert same.digest() == space.digest()
    assert RankingSpace({"body": (0, 3, 1)}).digest() != space.digest()


@pytest.mark.parametrize("weights, message", [
    ({"applicability": 6.5}, "must lie on"),
    ({"applicability": -0.5}, "weight for applicability"),
    ({"applicability": 3.25}, "must lie on"),
    ({"title": 6}, "title is fixed"),
])
def test_ranking_space_rejects_out_of_range_off_grid_and_fixed_edits(weights, message):
    space = RankingSpace({"applicability": (0, 6, 0.5)})
    with pytest.raises(ValueError, match=message):
        space.check(RankingPolicy("candidate", weights))


@pytest.mark.parametrize("bounds, message", [
    ({}, "at least one"),
    ({"typo": (0, 1, 1)}, "Unknown ranking weight field"),
    ({"body": (0, 1)}, "finite minimum"),
    ({"body": (0, float("inf"), 1)}, "finite minimum"),
    ({"body": (0, 1, True)}, "finite minimum"),
    ({"body": (2, 1, 1)}, "minimum <= maximum"),
    ({"body": (-1, 1, 1)}, "minimum <= maximum"),
    ({"body": (0, 1, 0)}, "step > 0"),
])
def test_ranking_space_rejects_malformed_bounds(bounds, message):
    with pytest.raises(ValueError, match=message):
        RankingSpace(bounds)


@pytest.mark.parametrize("bound, value, accepted", [
    ((0, 1, 0.1), 0.3, True), ((0, 1, 0.1), 0.7, True), ((0, 1, 0.1), 1.0, True),
    ((0, 1, 0.1), 0.35, False), ((0.1, 0.7, 0.2), 0.7, True), ((0.1, 0.7, 0.2), 0.6, False),
    ((0, 1, 0.1), 1.0000000001, False),
])
def test_ranking_space_step_membership_uses_decimal_values(bound, value, accepted):
    space, policy = RankingSpace({"body": bound}), RankingPolicy("candidate", {"body": value})
    if accepted:
        assert space.check(policy) is policy
    else:
        with pytest.raises(ValueError, match="must lie on"):
            space.check(policy)
