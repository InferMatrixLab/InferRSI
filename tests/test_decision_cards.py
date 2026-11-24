"""Pinned L0 → L1 → source reads across the three searchable atom kinds."""

import json
import sys
from importlib.resources import files
from pathlib import Path

import pytest

from inferrsi.apps.cli import main
from inferrsi.knowledge.knowledge_find import find, load_corpus
from inferrsi.knowledge.knowledge_operations import Bundle, KnowledgeReader
from inferrsi.knowledge.knowledge_store import KnowledgeStore

ROOT = Path(files("inferrsi.knowledge").joinpath("data", "skill_library"))


def cli(capsys, args):
    assert main(args) == 0
    return json.loads(capsys.readouterr().out)


def encoded(card):
    return json.dumps(card, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


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
    assert cli(capsys, hit["read_args"])["content"].splitlines()[-1] == "Procedure."

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
    assert old["card"]["atom"]["pointer"] == "case.json#/findings/1"
    assert old["status"] == "partial"
    assert {"validation", "prerequisites", "refusal_or_limits"} <= set(
        old["card"]["missing_fields"])
    oversized = cli(capsys, [*link["read_args"], "--max-bytes", "0"])
    assert oversized["status"] == "over_budget" and "card" not in oversized
    assert oversized["missing_fields"] == old["card"]["missing_fields"]
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
    assert cli(capsys, [*args, "sha256:" + "0" * 64])["status"] == "unavailable_revision"
    with pytest.raises(ValueError, match="exact --revision"):
        KnowledgeReader(store=store).read_decision_card("store:pilot", revision="")
