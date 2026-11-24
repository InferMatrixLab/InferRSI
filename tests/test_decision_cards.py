"""Pinned L0 → L1 → source reads across the three searchable atom kinds."""

import json
import sys
from importlib.resources import files
from pathlib import Path

import pytest

from inferrsi.apps.cli import main
from inferrsi.knowledge.decision_cards import DecisionSource
from inferrsi.knowledge.knowledge_find import find, load_corpus
from inferrsi.knowledge.knowledge_operations import Bundle, KnowledgeReader
from inferrsi.knowledge.knowledge_store import KnowledgeStore

ROOT = Path(files("inferrsi.knowledge").joinpath("data", "skill_library"))


def cli(capsys, args):
    assert main(args) == 0
    return json.loads(capsys.readouterr().out)


def encoded(card):
    return json.dumps(card, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def compact_read(capsys, link, full):
    """Reopen both projections and the pinned source through their actual CLI routes."""
    result = cli(capsys, [*link["read_args"], "--compact"])
    card = result["card"]
    assert card["view"] == "compact" and result["card_bytes"] == len(encoded(card))
    for key in ("ref", "revision", "atom", "decision", "status", "missing_fields"):
        assert card[key] == full["card"][key]
    assert cli(capsys, result["full_read_args"]) == full
    source_args = result.get("source_read_args", result["next_read_args"])
    assert cli(capsys, source_args)["revision"] == card["revision"]
    return result


@pytest.mark.parametrize("sidecar", [False, True])
def test_stale_checkout_skill_cannot_link_new_declaration(tmp_path, sidecar):
    owner = tmp_path / "pilot"
    owner.mkdir()
    core = owner / "SKILL.md"
    header = "---\nname: pilot\ndescription: "

    def write(term):
        metadata = json.dumps({"applicability": {"scope": term}})
        if sidecar:
            core.write_text(header + "Pilot.\n---\nProcedure.\n", encoding="utf-8")
            (owner / "metadata.json").write_text(metadata, encoding="utf-8")
        else:
            core.write_text(header + f"{term}.\nmetadata:\n  inferrsi: |\n    {metadata}\n"
                            "---\nProcedure.\n", encoding="utf-8")

    write("oldquartz")
    corpus = load_corpus(tmp_path, kinds=("skill",))
    assert find("oldquartz", corpus, decision_cards=True)["items"][0]["decision_card"]["revision"]
    write("newamber")
    stale = find("oldquartz", corpus, decision_cards=True)
    assert stale["items"][0].pop("decision_card") == {
        "status": "unavailable", "reason": "Source changed after ranking; repeat Find",
    }
    assert stale == find("oldquartz", corpus)
    fresh = load_corpus(tmp_path, kinds=("skill",))
    assert not find("oldquartz", fresh, decision_cards=True)["items"]
    assert find("newamber", fresh, decision_cards=True)["items"][0]["decision_card"]["revision"]


@pytest.mark.parametrize(("query", "before", "after", "keep_pin"), [
    ("nvidia quartz", "cuda", "rocm", False),
    ("amd quartz", "cuda", "rocm", False),
    ("cpu quartz", "cuda", "rocm", True),
    ("cuda rocm quartz", "cuda", "rocm", True),
    ("图模式 quartz", "cuda", "rocm", True),  # alias expansion adds cuda
    ("cuda quartz", "rocm", "common", False),
    ("cuda quartz", "cuda", "common", True),
    ("cuda quartz", "common", None, True),  # flat roots have no backend
    ("cuda quartz", "cuda", "cuda", True),  # only the peer registration changes
    ("quartz", "cuda", "absent", False),
])
def test_checkout_skill_pin_tracks_backend_weight(tmp_path, query, before, after, keep_pin):
    index = tmp_path / "skill-index.json"
    for name in ("pilot", "peer"):
        directory = tmp_path / name
        directory.mkdir()
        term = "quartz" if name == "pilot" else "unrelated"
        (directory / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {term}.\n---\n{term}.\n", encoding="utf-8",
        )

    def register(pilot, peer):
        if pilot is None:
            index.unlink()
            return
        skills = {"peer": {"path": "peer", "backend": peer}}
        if pilot != "absent":
            skills["pilot"] = {"path": "pilot", "backend": pilot}
        index.write_text(json.dumps({"schema_version": 1, "skills": skills}), encoding="utf-8")

    register(before, "common")
    corpus = load_corpus(tmp_path, kinds=("skill",))
    original, = find(query, corpus, decision_cards=True)["items"]
    pin = original["decision_card"]
    assert pin["revision"]
    register(after, "ascend")
    stale = find(query, corpus, decision_cards=True)
    link = stale["items"][0].pop("decision_card")
    assert stale == find(query, corpus)
    fresh = find(query, load_corpus(tmp_path, kinds=("skill",)), decision_cards=True)["items"]
    if keep_pin:
        assert link == pin == fresh[0]["decision_card"]
        assert stale["items"][0]["score"] == fresh[0]["score"]
    else:
        assert link["status"] == "unavailable" and "read_args" not in link
        if after == "absent":
            assert not fresh
        else:
            assert "repeat Find" in link["reason"]
            assert stale["items"][0]["score"] != fresh[0]["score"]
            assert fresh[0]["decision_card"] == pin


@pytest.mark.parametrize("failure", ["registration", "preview"])
def test_find_reports_safe_decision_source_failure(tmp_path, monkeypatch, failure):
    from inferrsi.knowledge import knowledge_find, skill_catalog

    owner = tmp_path / "pilot"
    owner.mkdir()
    (owner / "SKILL.md").write_text("---\nname: pilot\ndescription: Pilot.\n---\nProcedure.\n")
    corpus = load_corpus(tmp_path, kinds=("skill",))
    query = "cuda pilot"
    baseline = find(query, corpus)
    preview = knowledge_find._read_preview(corpus.documents[0], {})

    def unavailable(*args):
        raise OSError(13, "access denied", "/synthetic-checkout/private/skill-index.json")

    with monkeypatch.context() as patch:
        if failure == "registration":
            # The candidate already has its normal read link when the backend recheck fails.
            patch.setattr(knowledge_find, "_read_preview", lambda *args: preview)
            patch.setattr(skill_catalog, "skill_registrations", unavailable)
        else:
            patch.setattr(knowledge_find, "_read_preview", unavailable)
        plain = find(query, corpus)
        result = find(query, corpus, decision_cards=True)
        hit, = result["items"]
        assert hit.pop("decision_card") == {"status": "unavailable",
                                            "reason": "Source unavailable; repeat Find"}
        assert encoded(result) == encoded(plain)
        if failure == "registration":
            assert encoded(plain) == encoded(baseline)

    hit, = find(query, corpus, decision_cards=True)["items"]
    link = hit["decision_card"]
    read = KnowledgeReader(skill_root=tmp_path).read_decision_card(
        link["ref"], revision=link["revision"]
    )
    assert read["card"]["revision"] == link["revision"]


def test_stale_package_record_cannot_link_updated_owner(tmp_path, monkeypatch):
    from inferrsi.knowledge import catalog

    identity = "xdit.cuda.diffusion.parallelism_freshness_and_topology"
    name = identity + ".json"
    path = tmp_path / "knowledge" / "data" / "skill_library" / "records" / name
    path.parent.mkdir(parents=True)
    record = json.loads((ROOT / "records" / name).read_text(encoding="utf-8"))
    record["summary"] = "oldquartz"
    path.write_text(json.dumps(record), encoding="utf-8")
    monkeypatch.setattr(catalog, "files", lambda _: tmp_path)
    corpus = load_corpus(kinds=("record",))
    assert find("oldquartz", corpus, decision_cards=True)["items"][0]["decision_card"]["revision"]
    record["summary"] = "newamber"
    path.write_text(json.dumps(record), encoding="utf-8")
    stale = find("oldquartz", corpus, decision_cards=True)
    assert stale["items"][0].pop("decision_card") == {
        "status": "unavailable", "reason": "Source changed after ranking; repeat Find",
    }
    assert stale == find("oldquartz", corpus)


@pytest.mark.parametrize("legacy", [False, True])
def test_checkout_skill_pinned_cli_and_byte_budget(tmp_path, capsys, legacy):
    owner = tmp_path / "pilot"
    owner.mkdir()
    declaration = {
        "status": "candidate", "empirical_validation": "not_run",
        "applicability": {"prerequisites": ["fixed seed"], "refusal_point": "quality unknown",
                          "failure_modes": ["trace loss", "missing samples"]},
        "limitations": [{"hardware": "pilot only"}],
        "recommendations": ["比较质量" * 90], "validation_plan": ["check error"],
    }
    header = "---\nname: pilot\ndescription: Inspect pilot quality.\n"
    metadata = json.dumps(declaration, ensure_ascii=False)
    if legacy:
        (owner / "metadata.json").write_text(metadata, encoding="utf-8")
    else:
        header += f"metadata:\n  inferrsi: |\n    {metadata}\n"
    (owner / "SKILL.md").write_text(header + "---\nProcedure.\n", encoding="utf-8")
    (owner / "sample.txt").write_bytes(b"frozen attachment")
    args = ["find", "pilot", "--skill-root", str(tmp_path), "--kinds", "skill",
            "--no-external", "--json"]
    original = cli(capsys, args)
    result = cli(capsys, [*args, "--decision-cards"])
    hit, = result["items"]
    link = hit.pop("decision_card")
    assert result == original
    assert link["ref"] == "checkout:pilot"
    assert link["open_argv"][-len(link["read_args"]):] == link["read_args"]
    material = cli(capsys, hit["read_args"])
    assert material["content"].splitlines()[-1] == "Procedure."
    assert material["revision"] == link["revision"]
    assert hit["next_read_content_bytes"] == len(material["content"].encode("utf-8"))

    read = cli(capsys, link["read_args"])
    card = read["card"]
    assert card["layer"] == "L1" and card["atom"]["kind"] == "skill"
    assert card["revision"] == link["revision"] == read["revision"]
    assert card["declared"] == declaration
    assert card["decision"]["recommendation"] == declaration["recommendations"]
    assert card["decision"]["refusal_or_limits"] == {
        "refusal_point": "quality unknown", "failure_modes": ["trace loss", "missing samples"],
        "limitations": [{"hardware": "pilot only"}],
    }
    assert read["status"] == "complete" and not card["missing_fields"]
    compact = compact_read(capsys, link, read)
    assert compact["card"]["validation_evidence"] == {"empirical_validation": "not_run"}
    assert compact["card"]["declared"] == {"status": "candidate"}
    assert "recommendations" in compact["card"]["omitted_declared_fields"]
    limit = compact["card_bytes"]
    args = [*link["read_args"], "--compact", "--max-bytes"]
    assert cli(capsys, [*args, str(limit)]) == compact
    under = cli(capsys, [*args, str(limit - 1)])
    assert under["status"] == "over_budget" and under["card_bytes"] == limit and "card" not in under
    assert under["full_read_args"] == compact["full_read_args"] and under["missing_fields"] == []
    size = len(encoded(card))
    assert read["card_bytes"] == link["card_bytes"] == size
    assert cli(capsys, [*link["read_args"], "--max-bytes", str(size)])["card"] == card
    small = cli(capsys, [*link["read_args"], "--max-bytes", str(size - 1)])
    assert small["status"] == "over_budget" and small["card_bytes"] == size
    assert "card" not in small
    assert str(tmp_path) in read["next_read_args"]
    assert cli(capsys, read["next_read_args"])["revision"] == link["revision"]
    if legacy:
        assert json.loads(cli(capsys, read["source_read_args"])["content"]) == declaration
    target = tmp_path / "copy.txt"
    cli(capsys, ["resource", link["ref"], "pilot/sample.txt", "--revision", link["revision"],
                 "--skill-root", str(tmp_path), "--output", str(target)])
    assert target.read_bytes() == b"frozen attachment"


def test_real_case_finding_links_follow_visible_order_and_reopen_original(capsys):
    args = ["find", "Sarathi chunked prefill", "--kinds", "case", "--limit", "1",
            "--no-external", "--json"]
    default = cli(capsys, args)
    result = cli(capsys, [*args, "--decision-cards"])
    hit, = result["items"]
    assert hit["id"] == "case.sarathi-chunk-budget"
    for row, position in zip(hit["findings"], (0, 1, 3), strict=True):
        link = row.pop("decision_card")
        assert "--installed-library" in link["read_args"]
        read = cli(capsys, link["read_args"])
        card = read["card"]
        pointer = f"case.json#/findings/{position}"
        assert card["atom"]["selector"] == card["atom"]["pointer"] == pointer
        assert card["decision"]["recommendation"]["direction"] == row["direction"]
        assert link["card_bytes"] == len(encoded(card))
        assert card["declared"]["state"] == "candidate"
        assert card["declared"]["empirical_validation"] == "not_run"
        source = cli(capsys, read["source_read_args"])
        assert source["revision"] == link["revision"]
        assert cli(capsys, read["next_read_args"])["revision"] == link["revision"]
        assert card["declared"]["finding"] == json.loads(source["content"])["findings"][position]
        compact = compact_read(capsys, link, read)["card"]
        assert compact["finding_context"]["scope"] == card["declared"]["finding"]["scope"]
        assert compact["declared"]["origin"] == card["declared"]["origin"]
    assert result == default


def test_author_id_reordering_and_missing_checkout_revision(tmp_path, capsys):
    owner = tmp_path / "pilot"
    cases = owner / "cases"
    cases.mkdir(parents=True)
    (owner / "SKILL.md").write_text("---\nname: pilot\ndescription: Pilot.\n---\nBody.")
    (cases / "notes.md").write_text("Pilot history.")
    record = {
        "id": "case.pilot", "kind": "case", "content": "notes.md", "origin": ["unknown"],
        "state": "candidate", "sources": [{"type": "unknown"}], "attribution": [],
        "applicability": [], "limitations": [],
        "findings": [
            {"direction": "Initial", "reason": "size", "outcome": "caveat"},
            {"id": "trace-loss", "direction": "Trace loss",
             "reason": "absent", "outcome": "rejected"},
        ],
    }
    path = cases / "pilot.json"
    path.write_text(json.dumps(record))
    corpus = load_corpus(tmp_path, kinds=("case",))
    hit, = find("trace loss", corpus, decision_cards=True)["items"]
    link = hit["findings"][0]["decision_card"]
    assert link["read_args"][-1] == "id:trace-loss"
    old = cli(capsys, link["read_args"])
    compact = compact_read(capsys, link, old)
    assert compact["card"]["validation_evidence"] is None
    assert compact["full_read"]["finding"] == "id:trace-loss"
    by_position = [*link["read_args"][:-1], "case.json#/findings/1", "--compact"]
    assert cli(capsys, by_position) == compact
    assert compact["card"]["decision"]["recommendation"]["outcome"] == "rejected"
    assert old["card"]["atom"]["pointer"] == "case.json#/findings/1"
    assert old["status"] == "partial"
    assert {"validation", "prerequisites", "refusal_or_limits"} <= set(
        old["card"]["missing_fields"])
    oversized = cli(capsys, [*link["read_args"], "--max-bytes", "0"])
    assert oversized["status"] == "over_budget" and "card" not in oversized
    assert oversized["missing_fields"] == old["card"]["missing_fields"]
    (cases / "notes.md").write_text("Different search terms.")
    stale_body = find("trace loss", corpus, decision_cards=True)["items"][0]
    assert stale_body["decision_card"]["status"] == "unavailable"
    assert all("decision_card" not in row for row in stale_body["findings"])
    (cases / "notes.md").write_text("Pilot history.")
    original = find("trace loss", corpus)
    record["findings"][1]["id"] = "different-id"
    path.write_text(json.dumps(record))
    stale = find("trace loss", corpus, decision_cards=True)
    assert stale["items"][0].pop("decision_card")["status"] == "unavailable"
    assert stale == original == find("trace loss", corpus)
    record["findings"][1]["id"] = "trace-loss"
    record["findings"].reverse()
    path.write_text(json.dumps(record))
    stale = find("trace loss", corpus, decision_cards=True)["items"][0]
    assert stale["decision_card"]["status"] == "unavailable"
    assert all("decision_card" not in row for row in stale["findings"])
    failed = cli(capsys, link["read_args"])
    assert failed["status"] == "unavailable_revision" and "card" not in failed
    assert cli(capsys, [*link["read_args"], "--compact"]) == failed
    fresh = find("trace loss", load_corpus(tmp_path, kinds=("case",)), decision_cards=True)
    new = cli(capsys, fresh["items"][0]["findings"][0]["decision_card"]["read_args"])
    assert new["card"]["atom"]["selector"] == "id:trace-loss"
    assert new["card"]["atom"]["pointer"] == "case.json#/findings/0"
    assert new["revision"] != old["revision"]


def test_package_record_original_evidence_and_legacy_read(capsys):
    identity = "xdit.cuda.diffusion.parallelism_freshness_and_topology"
    raw = json.loads((ROOT / "records" / f"{identity}.json").read_text(encoding="utf-8"))
    hit, = cli(capsys, ["find", identity, "--kinds", "record", "--limit", "1",
                        "--no-external", "--decision-cards", "--json"])["items"]
    link = hit["decision_card"]
    assert link["ref"] == f"package:{identity}"
    read = cli(capsys, link["read_args"])
    card = read["card"]
    assert card["atom"] == {"kind": "record", "resource": "record.json"}
    for key in ("verification", "sources", "status", "claims", "limitations", "validation_plan"):
        assert card["declared"][key] == raw[key]
    assert card["declared"]["verification"]["locally_verified"] is False
    compact = compact_read(capsys, link, read)
    assert compact["card"]["validation_evidence"] == {"verification": raw["verification"]}
    assert set(("sources", "claims")) <= set(compact["card"]["omitted_declared_fields"])
    assert compact["card"]["declared"]["downstream_impact"] == raw["downstream_impact"]
    assert KnowledgeReader().read_decision_card(**compact["full_read"])["card"] == card
    assert card["decision"]["prerequisites"] == raw["applicability"]["conditions"]
    assert json.loads(cli(capsys, read["next_read_args"])["content"]) == raw
    assert cli(capsys, ["read", identity])["ref"] == link["ref"]


def test_installed_skill_package_fallback_without_yaml(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "yaml", None)
    hit, = cli(capsys, ["find", "ascend-device-health", "--kinds", "skill", "--limit", "1",
                        "--no-external", "--decision-cards", "--json"])["items"]
    link = hit["decision_card"]
    assert link["ref"].startswith("package:") and "--installed-library" not in link["read_args"]
    read = cli(capsys, link["read_args"])
    card = read["card"]
    assert card["atom"]["kind"] == "skill" and card["atom"]["resource"].endswith("/SKILL.md")
    assert len(encoded(card)) == link["card_bytes"]
    assert cli(capsys, read["next_read_args"])["revision"] == card["revision"]
    assert compact_read(capsys, link, read)["card"]["missing_fields"] == card["missing_fields"]


@pytest.mark.parametrize("entrypoint", ["note.md", "record.json"])
def test_store_record_reopens_retained_metadata_and_body(tmp_path, capsys, entrypoint):
    store = KnowledgeStore(tmp_path, skill_root=None)
    metadata = {
        "id": "pilot", "kind": "knowledge", "entrypoint": entrypoint, "state": "candidate",
        "sources": [{"type": "unknown"}], "attribution": [], "applicability": {}, "limitations": [],
    }
    old = store.create(Bundle(metadata, {entrypoint: b"first note"}, {}))
    store.update(Bundle(metadata, {entrypoint: b"revision two"}, {}),
                 expected=old, reason="extend", evidence=[])
    args = ["read", "store:pilot", "--store", str(tmp_path), "--layer", "L1", "--revision"]
    read = cli(capsys, [*args, old])
    assert read["status"] == "partial" and read["source_resource"] is None
    assert cli(capsys, read["source_read_args"])["revision"] == old
    assert cli(capsys, read["next_read_args"])["content"] == "first note"
    compact = cli(capsys, [*args, old, "--compact"])
    assert cli(capsys, compact["full_read_args"]) == read
    assert cli(capsys, [*args, "sha256:" + "0" * 64])["status"] == "unavailable_revision"
    with pytest.raises(ValueError, match="exact --revision"):
        KnowledgeReader(store=store).read_decision_card("store:pilot", revision="")


def test_compact_projection_uses_only_supplied_bundle(monkeypatch):
    metadata = {"id": "pilot", "kind": "knowledge", "entrypoint": "note.md",
                "state": "candidate", "sources": [{"type": "unknown"}],
                "applicability": {}, "limitations": [], "attribution": []}
    bundle = Bundle(metadata, {"note.md": b"body"}, {})
    view = bundle.view()

    def no_files(*args, **kwargs):
        pytest.fail("The in-memory decision projection opened a file")

    monkeypatch.setattr("io.open", no_files)
    monkeypatch.setattr("builtins.open", no_files)
    source = DecisionSource.from_bundle("store:pilot", bundle, view)
    compact = source.project(compact=True)
    assert compact["status"] == "partial" and "validation" in compact["card"]["missing_fields"]
    assert compact["card"]["validation_evidence"] is None
    assert compact["full_read"] == {"reference": "store:pilot", "revision": view["revision"]}


def test_compact_requires_explicit_l1(capsys):
    with pytest.raises(SystemExit) as failure:
        main(["read", "pilot", "--compact"])
    assert failure.value.code == 2 and "require --layer L1" in capsys.readouterr().err
