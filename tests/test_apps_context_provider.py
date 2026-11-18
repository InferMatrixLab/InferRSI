"""Check the Apps side of D023-3 against public Knowledge reads."""

from hashlib import sha256
from pathlib import PurePosixPath

import pytest

from inferrsi.apps.context_provider import ContextProvider
from inferrsi.apps.knowledge import knowledge_reader

_CGROUP = "package:inferrsi.common.skills.cgroup_resource_controls"
_H3 = "package:inferrsi.common.skills.audit_h3_runtime_residency"


def _request(**overrides):
    return {
        "query": None, "ids": [_CGROUP], "pins": [], "selection_limits": {},
        "max_bytes": 65536, "round_id": "scope/round:1", **overrides,
    }


def test_delivery_uses_exact_fixed_resource_bytes_in_knowledge_order():
    reader = knowledge_reader()
    revisions = {ref: reader.read(ref).revision for ref in (_H3, _CGROUP)}
    pins = [{"name": ref, "revision": revision} for ref, revision in revisions.items()]
    request = _request(ids=list(revisions), pins=pins, max_bytes=262144)
    provider = ContextProvider(reader)
    draft = provider.collect(request)
    contexts = reader.collect(
        ids=list(revisions), revisions=revisions, context_bytes=request["max_bytes"],
    )["contexts"]
    assert [item["pin"] for item in draft.items] == [
        {"reference": ref, "revision": revision} for ref, revision in revisions.items()
    ]
    expected = []
    for context, item in zip(contexts, draft.items, strict=True):
        resources = context["resources"]
        body = b"".join(
            reader.resource(context["ref"], r["path"], revision=context["revision"])
            for r in resources
        )
        expected.append(body)
        assert item["delivered_roles"] == list(dict.fromkeys(r["role"] for r in resources))
        assert item["delivered_bytes"] == len(body)
    assert draft.content == b"".join(expected)
    assert draft.sha256 == sha256(draft.content).hexdigest()
    assert draft.selection["state"] == "explicit_ids"
    assert draft.limitations
    assert any(item["code"] == "not_context_resource" for item in draft.omissions)
    assert len(PurePosixPath(draft.intended_location).parts) == 3
    assert draft == provider.collect(request)
    other = provider.collect({**request, "round_id": "other"})
    assert draft.intended_location != other.intended_location
    assert not hasattr(draft, "artifact")


@pytest.mark.parametrize("budget", [0, 1])
def test_empty_delivery_preserves_budget_omission(budget):
    draft = ContextProvider(knowledge_reader()).collect(_request(max_bytes=budget))
    assert draft.content == b""
    assert draft.sha256 == sha256(b"").hexdigest()
    assert draft.items == []
    assert draft.selection["no_match"] is False
    assert draft.omissions == [{
        "code": "context_limit", "stage": "context_delivery",
        "message": f"{_CGROUP}: context_limit", "retryable": False,
    }]


def test_unavailable_pin_never_falls_back_to_current_revision():
    draft = ContextProvider(knowledge_reader()).collect(
        _request(pins=[{"name": _CGROUP, "revision": "sha256:" + "0" * 64}]),
    )
    assert draft.content == b""
    assert draft.items == []
    assert draft.selection["no_match"] is True
    assert [entry["code"] for entry in draft.omissions] == ["unavailable_revision"]


def test_discovery_delegates_selection_to_knowledge():
    bounds = {"relevance": "cgroupv2", "limit": 1}
    draft = ContextProvider(knowledge_reader()).collect(
        _request(ids=[], selection_limits=bounds),
    )
    assert [item["pin"]["reference"] for item in draft.items] == [_CGROUP]
    assert draft.selection["ranking_applied"] is True
    assert draft.selection["state"] == "applied"
    assert draft.selection["method"] == "find-lexical-v1"
    assert draft.selection["tie_break"] == "state_then_id_then_ref"


def test_discovered_installed_case_can_be_replayed_at_its_exact_revision():
    provider = ContextProvider(knowledge_reader())
    discovered = provider.collect(_request(
        query="cache per-step masks ran out of device memory", ids=[],
        selection_limits={"limit": 1}, max_bytes=8192,
    ))
    item, = discovered.items
    pin = item["pin"]
    assert pin["reference"] == "checkout:case.qwen-ascend-rejected-directions"
    replay = provider.collect(_request(
        ids=[pin["reference"]], pins=[{"name": pin["reference"], "revision": pin["revision"]}],
        max_bytes=8192,
    ))
    assert replay.content and replay.content == discovered.content
    assert replay.items == discovered.items
    assert replay.selection["state"] == "explicit_ids"


@pytest.mark.parametrize("overrides", [
    {"max_bytes": False}, {"max_bytes": 2**53}, {"round_id": "../escape"},
    {"selection_limits": {"context_bytes": 1}},
    {"selection_limits": {"limit": True}},
    {"pins": [{"name": _CGROUP, "revision": "r1"}, {"name": _CGROUP, "revision": "r2"}]},
])
def test_invalid_request_is_rejected_before_collect(overrides, monkeypatch):
    reader = knowledge_reader()
    monkeypatch.setattr(reader, "collect", lambda *a, **kw: pytest.fail("unexpected collect"))
    with pytest.raises(ValueError):
        ContextProvider(reader).collect(_request(**overrides))


def test_inconsistent_knowledge_resource_bytes_are_rejected(monkeypatch):
    reader = knowledge_reader()
    result = reader.collect(ids=[_CGROUP], context_bytes=65536)
    result["contexts"][0]["resources"][0]["content"] = "changed"
    monkeypatch.setattr(reader, "collect", lambda *a, **kw: result)
    with pytest.raises(ValueError, match="digest mismatch"):
        ContextProvider(reader).collect(_request())
