"""Check the Apps side of D023-3 against public Knowledge reads."""

import json
import shutil
from hashlib import sha256
from pathlib import Path, PurePosixPath

import pytest

from inferrsi.apps.handoff.context_provider import ContextProvider
from inferrsi.apps.workflows.knowledge import knowledge_reader
from inferrsi.knowledge.knowledge_find import find, installed_skill_root, load_corpus
from inferrsi.knowledge.knowledge_operations import Bundle, KnowledgeReader
from inferrsi.knowledge.knowledge_store import KnowledgeStore

_CGROUP = "package:inferrsi.common.skills.cgroup_resource_controls"
_H3 = "package:inferrsi.common.skills.audit_h3_runtime_residency"


def _request(**overrides):
    return {
        "query": None, "ids": [_CGROUP], "pins": [], "selection_limits": {},
        "max_bytes": 65536, "round_id": "scope/round:1", **overrides,
    }


def test_delivery_uses_exact_fixed_resource_bytes_in_knowledge_order():
    reader = knowledge_reader()
    # local-dream includes a Python helper that must remain a reported omission.
    refs = (_H3, _CGROUP, "package:inferrsi.common.skills.local_dream")
    revisions = {ref: reader.read(ref).revision for ref in refs}
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
        pieces = []
        for resource in resources:
            raw = reader.resource(context["ref"], resource["path"], revision=context["revision"])
            if resource["locator"] == "skill-procedure":
                assert sha256(raw).hexdigest() == resource["source_sha256"]
                raw = b"".join(raw[start:end] for start, end in resource["source_byte_ranges"])
            assert sha256(raw).hexdigest() == resource["sha256"]
            pieces.append(raw)
        body = b"".join(pieces)
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


def test_find_selects_the_pin_before_exact_assembly(monkeypatch):
    collect = KnowledgeReader.collect

    def assemble(self, query="", **options):
        assert not query and options["ids"] == [_CGROUP]
        assert options["revisions"] == {_CGROUP: self.read(_CGROUP).revision}
        assert options["relevance"] == "cgroupv2"
        return collect(self, query, **options)

    monkeypatch.setattr(KnowledgeReader, "collect", assemble)
    bounds = {"relevance": "cgroupv2", "limit": 1}
    draft = ContextProvider(knowledge_reader()).collect(
        _request(ids=[], selection_limits=bounds),
    )
    assert [item["pin"]["reference"] for item in draft.items] == [_CGROUP]
    assert draft.selection["ranking_applied"] is True
    assert draft.selection["state"] == "applied"
    assert draft.selection["method"] == "find-lexical-v1"
    assert draft.selection["tie_break"] == "state_then_id_then_ref"


def test_find_uses_the_question_to_select_optional_files_for_the_sealed_pin():
    provider = ContextProvider(knowledge_reader())
    query = "video diffusion temporal tiling"
    request = _request(query=query, ids=[], selection_limits={"kind": "skill", "backend": "cuda",
                                                             "limit": 1})
    draft = provider.collect(request)
    ref = "package:inferrsi.common.skills.video_diffusion_optimization"
    revision = provider.reader.read(ref).revision
    item, = draft.items
    assert item["pin"] == {"reference": ref, "revision": revision}
    assert item["delivered_roles"] == ["core"]
    exact, = provider.reader.collect(ids=[ref], revisions={ref: revision}, relevance=query,
                                     context_bytes=request["max_bytes"])["contexts"]
    body, = exact["resources"]
    assert draft.content == body["content"].encode("utf-8")
    assert draft.sha256 == body["sha256"]
    assert any(row["code"] == "not_relevant" and "campaign.template.json" in row["message"]
               for row in draft.omissions)

    miss = provider.collect({**request, "query": "!!!"})
    assert miss.content == b"" and miss.items == [] and miss.selection["no_match"]


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


def test_query_reserves_both_diffusion_bodies_before_any_attachments():
    from inferrsi.knowledge._skill_selection import skill_procedure
    from tests.apps.test_campaign_task_selection import BASELINE_CUE

    provider = ContextProvider(knowledge_reader())
    req = _request(query=BASELINE_CUE, ids=[], selection_limits={"backend": "cuda", "limit": 2})
    draft = provider.collect(req)
    refs = ["package:inferrsi.common.skills.inference_benchmark_design",
            "package:inferrsi.common.skills.video_diffusion_optimization"]
    assert [item["pin"]["reference"] for item in draft.items] == refs
    bodies = []
    for item in draft.items:
        pin = item["pin"]
        bundle = provider.reader.read(pin["reference"], revision=pin["revision"])
        body = bundle.metadata["skill_documents"]["original"]
        bodies.append(skill_procedure(body, bundle.content[body])[0])
    assert all(body in draft.content for body in bodies)
    assert len(draft.content) <= req["max_bytes"] and draft.omissions
    exact = provider.collect({**req, "max_bytes": sum(map(len, bodies))})
    assert exact.content == b"".join(bodies)
    assert all(item["delivered_roles"] == ["core"] for item in exact.items)
    assert any(item["code"] == "context_limit" for item in exact.omissions)


def test_find_respects_separate_selection_and_sealed_byte_limits(tmp_path):
    source = Path(__file__).resolve().parents[1] / "fixtures/indexer/ranking-corpus"
    library = shutil.copytree(source, tmp_path / "library")
    record = library / "demo/cases/alpha.json"
    data = json.loads(record.read_text())
    data["limitations"] = ["x" * 10000]
    record.write_text(json.dumps(data))
    provider = ContextProvider(knowledge_reader(skill_root=library))
    request = _request(query="qxrankprobe", ids=[],
                       selection_limits={"kind": "case", "limit": 1, "max_bytes": 2048})
    draft = provider.collect(request)
    item, = draft.items
    assert item["pin"]["reference"] == "checkout:case.alternate"
    assert draft.content and draft.selection["matched_count"] == 2
    assert any(row["code"] == "output_limit" and "case.qxrankprobe" in row["message"]
               for row in draft.omissions)
    empty = provider.collect({**request, "max_bytes": 0})
    assert empty.content == b"" and empty.selection == draft.selection
    assert any(row["code"] == "context_limit" for row in empty.omissions)


def test_ranked_case_title_counts_toward_selection_bytes_for_the_handoff():
    reader = knowledge_reader(skill_root=installed_skill_root())
    provider = ContextProvider(reader)
    limits = {"kind": "case", "limit": 1, "max_bytes": 6000}
    request = _request(query="drama3 rejected directions", ids=[], selection_limits=limits)
    ranked = provider.collect(request)
    first = "checkout:case.drama3-rejected-directions"
    second = "checkout:case.qwen-b300-rejected-directions"
    assert [row["pin"] for row in ranked.items] == [
        {"reference": second, "revision": reader.read(second).revision}
    ]
    assert any(row["code"] == "output_limit" and first in row["message"]
               for row in ranked.omissions)

    # The caller who chooses the first Case directly is charged for its exact
    # view, which fits without the title supplied by ranked discovery.
    revision = reader.read(first).revision
    exact = provider.collect(_request(ids=[first], pins=[{"name": first, "revision": revision}],
                                      selection_limits=limits))
    assert [row["pin"] for row in exact.items] == [{"reference": first, "revision": revision}]


def test_first_unreadable_hit_does_not_consume_a_sealed_selection_slot(tmp_path):
    source = Path(__file__).resolve().parents[1] / "fixtures/indexer/ranking-corpus"
    library = shutil.copytree(source, tmp_path / "library")
    record = library / "demo/cases/alpha.json"
    data = json.loads(record.read_text())
    data["required_resources"] = ["missing.csv"]
    record.write_text(json.dumps(data))

    result = find("qxrankprobe", load_corpus(library, kinds=("case",)), limit=1)
    first, = result["items"]
    assert first["id"] == "case.qxrankprobe" and "missing.csv" in first["unreadable"]
    provider = ContextProvider(knowledge_reader(skill_root=library))
    draft = provider.collect(_request(query="qxrankprobe", ids=[],
                                      selection_limits={"kind": "case", "limit": 1}))
    delivered, = draft.items
    assert delivered["pin"]["reference"] == "checkout:case.alternate"
    assert draft.selection["matched_count"] == 2 and draft.selection["returned_count"] == 1
    assert any(row["code"] == "invalid" and "case.qxrankprobe" in row["message"]
               for row in draft.omissions)


def test_text_lookup_uses_the_requested_store_revision(tmp_path):
    store = KnowledgeStore(tmp_path, skill_root=None)
    metadata = {"id": "local-context", "kind": "knowledge", "state": "candidate",
                "entrypoint": "note.md", "sources": [{"type": "unknown"}], "applicability": {},
                "limitations": [], "attribution": []}
    old = store.create(Bundle(metadata, {"note.md": b"firstrevisionmarker"}, {}))
    store.update(Bundle(metadata, {"note.md": b"latestrevisionmarker"}, {}), expected=old,
                 reason="new observation", evidence=[])
    provider = ContextProvider(knowledge_reader(store_root=tmp_path))
    request = _request(query="firstrevisionmarker", ids=[], selection_limits={"kind": "knowledge"})
    assert provider.collect(request).selection["no_match"]
    draft = provider.collect({**request, "pins": [{"name": "local-context", "revision": old}]})
    assert draft.selection["returned_count"] == 1 and not draft.selection["no_match"]
    assert draft.content == b"firstrevisionmarker"
    assert draft.items[0]["pin"] == {"reference": "store:local-context", "revision": old}
    assert not draft.omissions
    missing = provider.collect({
        **request, "query": "cgroupv2", "selection_limits": {"limit": 1},
        "pins": [{"name": "local-context", "revision": "sha256:" + "0" * 64}],
    })
    assert [item["pin"]["reference"] for item in missing.items] == [_CGROUP]
    assert any(row["code"] == "unavailable_revision" and "store:local-context" in row["message"]
               for row in missing.omissions)


@pytest.mark.parametrize("overrides", [
    {"max_bytes": False}, {"max_bytes": 2**53}, {"round_id": "../escape"},
    {"query": "cgroupv2"},
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
