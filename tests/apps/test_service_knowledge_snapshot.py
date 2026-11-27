"""A fingerprint-free search retains the actual bytes its reads can deliver."""

import json
from pathlib import Path

import pytest

from inferrsi.apps.cli import main
from inferrsi.harness import optimization
from inferrsi.harness.records import service_io
from inferrsi.knowledge import knowledge_find, knowledge_operations
from inferrsi.knowledge.catalog import lookup_record
from tests.apps.test_campaign_task_selection import BASELINE_CUE
from tests.fixtures.service_reuse import call, diagnose, rejected
from tests.fixtures.service_reuse import campaign as campaign
from tests.fixtures.service_reuse import no_fingerprints as no_fingerprints

IDENTITY = "inferrsi.common.skills.inference_benchmark_design"
LINK = "references/benchmark-commands.md"


@pytest.fixture
def installed_source(tmp_path, monkeypatch):
    """Edit a real owner tree without changing this test checkout's package."""
    record = lookup_record(IDENTITY, file_fingerprints=False)
    body = knowledge_operations.service_body(record)[1]
    attachment = knowledge_operations.service_body(record, LINK)[1]
    package = tmp_path / "installed-package"
    root = package / "knowledge"
    for path, content in knowledge_operations.service_resources(record).items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    monkeypatch.setattr(knowledge_operations, "files", lambda name: package)
    return {"root": root, "record": record, "body": body, "attachment": attachment,
            "primary": root / record["skill_documents"]["original"]}


def find(campaign):
    call(campaign, "start")
    diagnose(campaign)
    assert main(["find", BASELINE_CUE, "--backend", "cuda", "--session",
                 str(campaign["root"]), "--limit", "1"]) == 0
    found = json.loads(campaign["capsys"].readouterr().out)
    assert found["items"][0]["material_ref"] == "package:" + IDENTITY
    service_io.no_fingerprints(found)
    return found


def read(campaign, argv):
    assert main(argv) == 0
    opened = json.loads(campaign["capsys"].readouterr().out)
    retained = service_io.read(campaign["root"] / opened["reference"]["path"])
    context, = retained["contexts"]
    resource, = context["resources"]
    assert resource["content"] == opened["content"]
    assert context["content_bytes"] == len(opened["content"].encode())
    assert retained["request"]["search_ref"] in argv
    service_io.no_fingerprints(opened)
    return opened


def finish(campaign, first):
    parts = [first["content"]]
    opened = first
    while "next_read_args" in opened:
        previous = opened["content_range"]["end"]
        opened = read(campaign, opened["next_read_args"])
        assert opened["content_range"]["start"] == previous
        parts.append(opened["content"])
    return "".join(parts).encode()


def test_service_reads_and_continuations_keep_the_find_source(campaign, installed_source):
    found = find(campaign)
    hit, = found["items"]
    primary = installed_source["primary"]
    primary.write_bytes(primary.read_bytes() + b"\nEdited after Find.\n")
    body = read(campaign, hit["read_args"])
    assert body["revision"] == hit["revision"]
    assert "next_read_args" in body
    assert finish(campaign, body) == installed_source["body"]

    attachment = read(campaign, [*hit["read_args"], "--resource", LINK,
                                  "--byte-range", "0", "128"])
    original = installed_source["attachment"]
    assert attachment["content"].encode() == original[:128]
    target = primary.parent / LINK
    target.write_bytes(b"Replaced after the first attachment page.\n")
    assert finish(campaign, attachment) == original
    assert attachment["revision"] == hit["revision"]

    declared = next(name for name in installed_source["record"]["skill_metadata"]["references"]
                    if name.startswith("../"))
    path, raw, _ = knowledge_operations.service_body(installed_source["record"], declared)
    (installed_source["root"] / path).write_bytes(b"Changed declared reference.\n")
    linked = read(campaign, [*hit["read_args"], "--resource", declared + "#section"])
    assert finish(campaign, linked) == raw
    _, state, _ = optimization.read_records(campaign["root"])
    assert any(item.get("search_ref") == found["reference"]["path"]
               for item in state["contexts"])


def test_service_search_does_not_publish_a_changed_ranked_body(campaign, installed_source,
                                                            monkeypatch):
    original_rank = knowledge_find.rank

    def change_after_ranking(*args, **kwargs):
        result = original_rank(*args, **kwargs)
        primary = installed_source["primary"]
        primary.write_bytes(primary.read_bytes() + b"\nChanged before retention.\n")
        return result

    monkeypatch.setattr(knowledge_find, "rank", change_after_ranking)
    call(campaign, "start")
    diagnose(campaign)
    assert rejected(["find", BASELINE_CUE, "--backend", "cuda", "--session",
                     str(campaign["root"]), "--limit", "1"]) == 2
    assert "Knowledge changed while finding material" in campaign["capsys"].readouterr().err
    assert json.loads((campaign["root"] / "state.json").read_bytes())["contexts"] == []
    assert not (campaign["root"] / "knowledge/sources").exists()


def test_service_retains_a_records_declared_edition(tmp_path):
    record = lookup_record("vllm.common.llm.bounded_serving_measurement", file_fingerprints=False)
    edition = record["skill_documents"]["en"]
    expected = knowledge_operations.service_body(record, edition)
    source = tmp_path / "retained"
    resources = knowledge_operations.service_resources(record)
    assert set(resources) == {"record.json", edition}
    for path, content in resources.items():
        target = source / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    assert knowledge_operations.service_body(record, edition, source_root=source) == expected
    assert json.loads(knowledge_operations.service_body(record, source_root=source)[1]) == record


def test_service_old_search_keeps_history_but_cannot_claim_current_bytes(campaign):
    found = find(campaign)
    hit, = found["items"]
    delivery = read(campaign, hit["read_args"])
    root = campaign["root"]
    reference = root / found["reference"]["path"]
    legacy = json.loads(reference.read_bytes())
    legacy.pop("source_snapshot")
    reference.write_text(json.dumps(legacy), encoding="utf-8")
    old_search = reference.read_bytes()
    old_delivery = (root / delivery["reference"]["path"]).read_bytes()
    before = (root / "state.json").read_bytes()
    assert rejected(hit["read_args"]) == 2
    assert "run Find again before reading" in campaign["capsys"].readouterr().err
    assert reference.read_bytes() == old_search
    assert (root / delivery["reference"]["path"]).read_bytes() == old_delivery
    assert (root / "state.json").read_bytes() == before
    _, state, _ = optimization.read_records(root)
    assert any(item["path"] == delivery["reference"]["path"] for item in state["contexts"])


def test_missing_retained_attachment_never_falls_back_to_current_package(campaign):
    found = find(campaign)
    hit, = found["items"]
    root = campaign["root"]
    search = json.loads((root / found["reference"]["path"]).read_bytes())
    retained = root / search["source_snapshot"] / IDENTITY
    primary = Path(hit["body_resource"])
    (retained / primary.parent / LINK).unlink()
    assert rejected([*hit["read_args"], "--resource", LINK]) == 2
    assert "Unknown resource" in campaign["capsys"].readouterr().err
    assert read(campaign, hit["read_args"])["content"]
