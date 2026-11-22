"""Recorded ranking and shared search evidence keep their identities and semantics."""

import copy
import json
import runpy
from pathlib import Path

import pytest

from inferrsi.apps.views.dashboard import dashboard_snapshot, render_dashboard
from inferrsi.apps.views.retrieval_projection import (
    project_knowledge,
    public_value,
    retrieval_view,
)
from inferrsi.apps.views.search_attribution import import_search
from inferrsi.knowledge.catalog import search_knowledge

FIXTURE = runpy.run_path(str(Path(__file__).parent / "fixtures/knowledge_retrieval.py"))


@pytest.fixture
def campaign(tmp_path):
    FIXTURE["build"](tmp_path)
    return tmp_path


@pytest.mark.parametrize("question", [{"query": "launch"}, {"relevance": "launch"}])
def test_execution_scores_and_exact_budget_preserve_payloads(tmp_path, question):
    with FIXTURE["reader"](tmp_path) as reader:
        result = reader.collect(**question, context_bytes=54)
        # Observations cannot eject a result from the budgeted item bytes.
        bounded = reader.collect(**question, context_bytes=54, max_bytes=result["material_bytes"])
        fewer = reader.collect(**question, limit=2)
    assert len(result["items"]) == 5 and len(result["contexts"]) == 2
    assert len(result["context_omissions"]) == 3 and result["context_bytes"] == 54
    observation = result["retrieval"]
    assert observation["calls"] == ["collect", "find"]
    assert observation["selection"]["method"] == "find-lexical-v1"
    assert observation["counts"]["matched"] == 5
    assert observation["assembly"] == "performed"
    assert [m["ref"] for m in observation["items"]] == [m["ref"] for m in result["items"]]
    for item in observation["items"]:
        assert item["score"] == sum(item["components"].values())
    assert len({m["score"] for m in observation["items"]}) == 1
    assert [m["ref"] for m in observation["items"]] == sorted(m["ref"] for m in result["items"])
    for field in ("items", "contexts", "context_omissions", "context_bytes", "material_bytes"):
        assert result[field] == bounded[field]
    assert fewer["retrieval"]["counts"]["excluded"]["item_limit"] == 3
    assert fewer["retrieval"]["assembly"] == "not_requested"


def test_catalog_observation_does_not_mutate_records_or_return_order(tmp_path, monkeypatch):
    with FIXTURE["reader"](tmp_path) as reader:
        records = list(reader.records().values())
        original = copy.deepcopy(records)
        monkeypatch.setattr("inferrsi.knowledge.catalog.knowledge_records", lambda: records)
        observations = {}
        for query in ("guidance missing", "missing", "guidance guidance", ""):
            result = search_knowledge(query, limit=2, explain=True)
            assert result["items"] == search_knowledge(query, limit=2)
            observations[query] = result["retrieval"]
        excluded = search_knowledge("guidance", repo="other", explain=True)

    assert records == original
    ranked = observations["guidance missing"]
    assert ranked["calls"] == ["knowledge search", "find"]
    assert ranked["selection"]["method"] == "find-lexical-v1"
    assert ranked["counts"]["matched"] == 5  # "guidance" is only in the Skill bodies.
    assert ranked["items"] == observations["guidance guidance"]["items"]
    for item in ranked["items"]:
        assert item["score"] == item["components"]["guidance"]
    assert observations["missing"]["items"] == []
    inventory = observations[""]
    assert inventory["calls"] == ["knowledge search"]
    assert inventory["selection"]["state"] == "not_requested"
    assert inventory["selection"]["method"] is None
    assert all("score" not in item for item in inventory["items"])
    assert excluded["retrieval"]["counts"]["excluded"]["repo"] == 5


def test_shell_search_keeps_its_recorded_query_scope_and_hits(campaign):
    path = campaign / "search/round-3.json"
    record = json.loads(path.read_text())
    hit = {"ref": "cases/launch.md"}
    record["events"] = [{"id": "search:1", "action": "search", "tool": "rg",
                         "query": "dense BF16", "scope": ["cases"], "materials": [hit]}]
    path.write_text(json.dumps(record))
    searches = dashboard_snapshot(campaign)["data"]["knowledge_trace"]["searches"]
    event, = next(s["events"] for s in searches if s["path"] == "search/round-3.json")
    assert (event["query"], event["scope"], event["materials"]) == ("dense BF16", ["cases"], [hit])


def test_actual_paths_ranking_states_and_multi_run_navigation(campaign):
    data = dashboard_snapshot(campaign)["data"]
    trace = data["knowledge_trace"]
    captures = {c["context_id"]: c for c in trace["retrievals"]}
    assert captures["catalog"]["trace"]["calls"] == ["knowledge search", "find"]
    assert captures["collect"]["trace"]["calls"] == ["collect", "find"]
    assert captures["capture"]["trace"]["calls"] == ["campaign capture-context", "collect", "find"]
    assert captures["explicit"]["trace"]["selection"]["state"] == "explicit_ids"
    assert captures["explicit"]["trace"]["calls"] == ["collect"]
    assert all("score" not in item for item in captures["explicit"]["trace"]["items"])
    assert captures["no-ranking"]["trace"]["selection"]["state"] == "not_requested"
    assert captures["legacy"]["trace"]["entrypoint"] == "unknown"
    assert captures["legacy"]["trace"]["items"] == []
    assert captures["legacy"]["trace"]["selection"]["method"] == "weighted-lexical-v1"
    assert captures["empty"]["trace"]["counts"]["matched"] == 0
    assert len(captures["capture"]["contexts"]) == 2
    assert len(captures["capture"]["context_omissions"]) == 3
    links = captures["capture"]["links"]
    assert {(link["candidate_id"], link["run_id"], link["round"]) for link in links} == {
        ("repeat", "first", 1), ("repeat", "retry", 1)}
    assert len(links) == 2 and len({link["experiment_id"] for link in links}) == 2
    assert all(link["round"] == 2 for link in captures["collect"]["links"])
    assert len(trace["searches"]) == 4  # v1/v2 are kept distinct, never summed.
    archive = next(s for s in trace["searches"] if s["schema_version"] == 2)
    assert not archive["issues"]
    events = {event["context_id"]: event for event in archive["events"]}
    assert events["catalog"]["tool"] == "knowledge search"
    assert events["catalog"]["delivery"]["state"] == "unknown"
    assert events["capture"]["tool"] == "find"
    assert events["capture"]["delivery"]["state"] == "visible"
    material = next(m for m in archive["materials"] if m["evidence"])
    evidence, = material["evidence"]
    assert evidence["state"] == "archive_reviewed"
    assert evidence["event_id"] == events["capture"]["id"]
    assert evidence["passage_path"] == captures["capture"]["contexts"][0]["resources"][0]["path"]
    assert evidence["passage_text"] == "Synthetic launch guidance."
    assert any(d["preparation_state"] == "omitted" for d in archive["declarations"])
    assert archive["counts"]["used"] == 1
    for number in (2, 3):
        saved = next(s for s in trace["searches"] if s["round"] == number)
        assert saved["counts"] is None
    assert {r["verdict"] for r in data["candidates"]} == {"FAIL", "INCONCLUSIVE"}
    assert any("omitted" in check["message"] for check in data["story"]["checks"])


def test_missing_legacy_fields_do_not_imply_ranking_or_assembly():
    assert retrieval_view({})["selection"]["state"] == "unknown"
    assert retrieval_view({"request": {"relevance_method": "task-lexical-v1"}})[
        "selection"]["state"] == "unknown"
    assert retrieval_view({"request": {"relevance": None}})["selection"]["state"] == (
        "not_requested")
    assert retrieval_view({})["assembly"] == "unknown"


@pytest.mark.parametrize(("change", "state"), [
    ({"schema_version": 17}, "unsupported_version"),
    ({"campaign_id": "other"}, "identity_mismatch"),
    ({"round": 99}, "identity_mismatch"),
    ({"counts": None}, "invalid_counts"),
    ({"corpus": {}}, "invalid_source"),
    ({"events": [{"materials": [], "delivery": None}]}, "invalid_events"),
    ({"materials": {"ref": {"use": "used", "evidence": None}}}, "invalid_materials"),
])
def test_invalid_archives_are_explicit_and_do_not_break_render(campaign, change, state):
    path = campaign / "search/archive/round-1.json"
    doc = json.loads(path.read_text())
    path.write_text(json.dumps({**doc, **change}))
    snapshot = dashboard_snapshot(campaign)
    archive = next(s for s in snapshot["data"]["knowledge_trace"]["searches"]
                   if s["schema_version"] == 2)
    assert archive["state"] == state and "counts" not in archive
    assert "__DASHBOARD_" not in render_dashboard(snapshot)


@pytest.mark.parametrize("kind", ["capture", "revision", "passage", "candidate"])
def test_shared_record_mismatch_is_flagged(campaign, kind):
    path = campaign / "search/archive/round-1.json"
    doc = json.loads(path.read_text())
    if kind == "capture":
        doc["events"][0]["sha256"] = "0" * 64
    elif kind == "revision":
        doc["events"][0]["materials"][0]["revision"] = "changed"
    elif kind == "passage":
        next(m for m in doc["materials"].values() if m.get("evidence"))["evidence"][0][
            "passage_text"] = "changed"
    else:
        doc["candidates"][0]["run_id"] = "wrong-run"
    path.write_text(json.dumps(doc))
    archive = next(s for s in dashboard_snapshot(campaign)["data"]["knowledge_trace"]["searches"]
                   if s["schema_version"] == 2)
    assert archive["issues"]
    if kind == "passage":
        evidence = next(m for m in archive["materials"] if m["evidence"])["evidence"][0]
        assert evidence["state"] == "passage_mismatch"


def test_shared_records_work_without_optimization_log_and_reimport_is_idempotent(campaign):
    data = dashboard_snapshot(campaign)["data"]
    data["story"] = {"state": "not_recorded"}
    view = project_knowledge(campaign, data)
    assert len(view["retrievals"]) == 7
    assert all(c["state"] == "verified" for c in view["retrievals"])
    path = campaign / "search/round-2.json"
    original = path.read_bytes()
    import_search(campaign, number=2,
                  context_ids=["collect", "explicit", "no-ranking", "empty", "legacy"])
    assert path.read_bytes() == original


def test_untrusted_verified_capture_is_redacted_before_embedding(campaign):
    data = dashboard_snapshot(campaign)["data"]
    capture = data["story"]["retrievals"][0]
    capture["request"]["query"] = "password=synthetic-secret /private/example/model"
    capture["assembled_text"] = "token=synthetic-secret /private/example/model"
    value = project_knowledge(campaign, data)
    payload = json.dumps(value)
    assert "synthetic-secret" not in payload and "/private/example" not in payload
    assert "redacted" in payload


@pytest.mark.parametrize(("private", "replacement"), [
    ("/tmp", "[redacted-path]"),
    ("/dev/shm", "[redacted-path]"),
    ("192.0.2.1", "[redacted-address]"),
    ("a@b.co", "[redacted-email]"),
])
def test_public_redaction_preserves_complete_text(private, replacement):
    text = f"Use {private}. " + "Preserve this recorded tail. " * 20
    # A path includes the trailing period; other redactors leave it intact.
    expected = text.replace(private + "." if private.startswith("/") else private,
                            replacement)
    assert public_value({"text": text}) == {"text": expected}


@pytest.mark.parametrize("declarations", [None, False, {}, [None], ["invalid"]])
def test_v1_ignores_unsupported_top_level_declarations(campaign, declarations):
    path = campaign / "search/round-2.json"
    doc = json.loads(path.read_text())
    path.write_text(json.dumps({**doc, "declarations": declarations}))
    snapshot = dashboard_snapshot(campaign)
    search = next(s for s in snapshot["data"]["knowledge_trace"]["searches"]
                  if s["path"] == "search/round-2.json")
    assert search["state"] == "recorded" and search["declarations"] == []
    assert search["counts"] == doc["counts"]
    for layout in ("default", "profile_first"):
        snapshot["data"]["review_layout"] = layout
        assert "__DASHBOARD_" not in render_dashboard(snapshot)


def _round_one(campaign, version):
    return next(s for s in dashboard_snapshot(campaign)["data"]["knowledge_trace"]["searches"]
                if s["round"] == 1 and s["schema_version"] == version)


@pytest.mark.parametrize("version", [1, 2])
def test_adoption_split_passes_through_and_old_records_stay_readable(campaign, version):
    path = campaign / ("search/round-1.json" if version == 1 else "search/archive/round-1.json")
    doc = json.loads(path.read_text())
    search = _round_one(campaign, version)
    assert search["state"] == "recorded" and search["adoption"] == doc["adoption"]
    assert search["adoption"]["search_hits"]["adopted"] == doc["observed"]["used"]
    path.write_text(json.dumps({k: v for k, v in doc.items() if k != "adoption"}))
    search = _round_one(campaign, version)
    assert search["state"] == "recorded" and search["adoption"] is None
    assert search["counts"] == doc["counts"]


@pytest.mark.parametrize("change", [
    {"search_hits": {"adopted": 6, "unique_hits": 5, "state": "complete"}},
    {"direct_reads": {"adopted": 0, "read_only": 0, "state": "complete"}},
    {"search_hits": {"adopted": 1, "unique_hits": 5, "state": "unknown"}},
    {"other_adopted": 1},
    {"attribution_unknown": 1},
    {"attribution_unknown": None},
    {"unverified_reads": {"adopted": 1, "refs": 0}},
    {"unverified_reads": {"adopted": 0, "refs": 0, "state": "not_applicable"}},
    {"unique_hit_revisions": 4},
    {"unique_hit_revisions": -1},
])
def test_adoption_outside_its_denominator_is_invalid(campaign, change):
    path = campaign / "search/archive/round-1.json"
    doc = json.loads(path.read_text())
    path.write_text(json.dumps({**doc, "adoption": {**doc["adoption"], **change}}))
    search = _round_one(campaign, 2)
    assert search["state"] == "invalid_counts" and "adoption" not in search


@pytest.mark.parametrize("state", ["unknown", "complete"])
def test_ambiguous_attribution_requires_unknown_rates(campaign, state):
    path = campaign / "search/archive/round-1.json"
    doc = json.loads(path.read_text())
    adoption = doc["adoption"]
    hits = adoption["search_hits"]
    adoption.update(attribution_unknown=1,
                    search_hits={**hits, "adopted": hits["adopted"] - 1, "state": state},
                    direct_reads={**adoption["direct_reads"], "state": state})
    path.write_text(json.dumps(doc))
    search = _round_one(campaign, 2)
    assert search["state"] == ("recorded" if state == "unknown" else "invalid_counts")


def test_missing_capture_and_duplicate_json_keys_are_explicit(campaign):
    (campaign / "knowledge/capture.json").unlink()
    (campaign / "search/round-3.json").write_text('{"round":3,"round":3}')
    snapshot = dashboard_snapshot(campaign)
    trace = snapshot["data"]["knowledge_trace"]
    assert trace["retrievals"][0]["state"] == "file_absent"
    assert next(s for s in trace["searches"] if s["round"] == 3)["state"] == "invalid_format"
    assert "__DASHBOARD_" not in render_dashboard(snapshot)


def test_conflicting_rounds_and_duplicate_runs_do_not_get_unique_navigation(campaign):
    data = dashboard_snapshot(campaign)["data"]
    data["story"]["iterations"][1]["context_ids"].append("capture")
    trace = project_knowledge(campaign, data)
    capture = next(c for c in trace["retrievals"] if c["context_id"] == "capture")
    assert capture["association_state"] == "round_conflict"
    assert all(link["state"] == "round_conflict" for link in capture["links"])
    data = dashboard_snapshot(campaign)["data"]
    data["candidates"].append(copy.deepcopy(data["candidates"][0]))
    capture = next(c for c in project_knowledge(campaign, data)["retrievals"]
                   if c["context_id"] == "capture")
    assert any(link["state"] == "ambiguous" for link in capture["links"])


def test_symlinked_search_record_and_malformed_observation_degrade(campaign):
    path = campaign / "search/round-3.json"
    path.unlink()
    path.symlink_to(campaign / "campaign.json")
    data = dashboard_snapshot(campaign)["data"]
    assert next(s for s in data["knowledge_trace"]["searches"] if s["round"] == 3)[
        "state"] == "unsafe_path"
    assert retrieval_view({"retrieval": {"schema_version": 1, "items": None}})[
        "state"] == "unsupported_version"


def test_declaration_source_hash_mismatch_is_not_hidden(campaign):
    path = campaign / "search/archive/round-1.json"
    doc = json.loads(path.read_text())
    doc["declarations"][0]["log_sha256"] = "0" * 64
    path.write_text(json.dumps(doc))
    archive = next(s for s in dashboard_snapshot(campaign)["data"]["knowledge_trace"]["searches"]
                   if s["schema_version"] == 2)
    assert archive["declarations"][0]["state"] == "source_mismatch"
    assert "source_mismatch" in archive["issues"]


@pytest.mark.parametrize(("field", "value"), [
    *[("source", source) for source in [None, False, 7, [], {}, "", "../source.json"]],
    *[("context_id", context_id) for context_id in [
        [], {}, None, False, 7, "", " capture", "../capture", "_capture",
        "x" * 129, "not-recorded", "catalog",
    ]],
])
def test_invalid_declaration_identity_preserves_dashboard(campaign, field, value):
    path = campaign / "search/archive/round-1.json"
    doc = json.loads(path.read_text())
    doc["declarations"][0][field] = value
    path.write_text(json.dumps(doc))

    snapshot = dashboard_snapshot(campaign)
    trace = snapshot["data"]["knowledge_trace"]
    archive = next(s for s in trace["searches"] if s["schema_version"] == 2)
    assert archive["state"] == "recorded"
    assert archive["declarations"][0]["state"] == "source_mismatch"
    assert "source_mismatch" in archive["issues"]
    assert archive["counts"] == doc["counts"]
    assert all(link["state"] == "linked" for link in archive["links"])
    assert len(trace["retrievals"]) == 7
    assert any(e["state"] == "archive_reviewed"
               for material in archive["materials"] for e in material["evidence"])
    for layout in ("default", "profile_first"):
        snapshot["data"]["review_layout"] = layout
        rendered = render_dashboard(snapshot)
        assert "source_mismatch" in rendered and "__DASHBOARD_" not in rendered
