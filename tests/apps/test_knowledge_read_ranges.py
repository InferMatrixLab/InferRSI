"""Paged CLI reads retain the UTF-8 bytes actually returned at one fixed revision."""

import hashlib
import json
import random
import sys
from pathlib import Path

import pytest

from inferrsi.apps.cli import main
from inferrsi.harness.records.knowledge_capture import MAX_CONTEXT_CAPTURE_BYTES, verify_capture
from inferrsi.knowledge._skill_selection import INLINE_PAGE_BYTES
from inferrsi.knowledge.knowledge_operations import Bundle, KnowledgeReader
from inferrsi.knowledge.knowledge_store import KnowledgeStore
from tests.apps.test_codex_knowledge_search import _import, _operation


def call(capsys, *argv):
    assert main(list(argv)) == 0
    text = capsys.readouterr().out
    return json.loads(text), text


def store_edition(tmp_path, body):
    (tmp_path / "store").mkdir()
    store = KnowledgeStore(tmp_path / "store", skill_root=None)
    record = {"id": "paging-demo", "kind": "knowledge", "state": "candidate",
              "title": "pagingdemo", "entrypoint": "note.md", "sources": [{"type": "unknown"}],
              "applicability": {}, "limitations": [], "attribution": []}
    bundle = Bundle(record, {"note.md": b"pagingdemo introduction\n", "pages.md": body}, {})
    return store, store.create(bundle), bundle


def test_large_attachment_continues_at_the_original_pin_and_records_each_page(tmp_path, capsys):
    body = ("资料😀\tmeasurement\n" * 108_000).encode()
    assert 2 * len(body) > MAX_CONTEXT_CAPTURE_BYTES
    store, revision, original = store_edition(tmp_path, body)
    root = tmp_path / "campaign"
    call(capsys, "evidence", "init", "--id", "paging", "--directory", str(root))
    result, _ = call(capsys, "find", "pagingdemo", "--store", str(store.workspace),
                     "--session", str(root), "--limit", "1")
    search_ref = result["reference"]["path"]
    item, = result["items"]
    assert item["material_ref"] == "store:paging-demo" and item["revision"] == revision
    argv = [*item["read_args"], "--resource", "pages.md"]
    result, _ = call(capsys, *argv)
    standalone, _ = call(capsys, "read", item["material_ref"], "--revision", revision,
                         "--store", str(store.workspace), "--resource", "pages.md",
                         "--omit-resources")
    assert standalone["content"] == result["content"]
    assert standalone["next_byte_range"] == result["next_byte_range"]
    replacement = Bundle(original.metadata, {"note.md": b"updated", "pages.md": b"new"}, {})
    store.update(replacement, expected=revision, reason="new edition", evidence=[])
    received = bytearray()
    while True:
        span, data = result["content_range"], result["content"].encode()
        assert span == {"start": len(received), "end": len(received) + len(data),
                        "total_bytes": len(body), "first_line": received.count(b"\n") + 1}
        assert data == body[span["start"]:span["end"]]
        assert result["revision"] == revision
        assert result["search_ref"] == search_ref
        saved = (root / result["reference"]["path"]).read_bytes()
        assert len(saved) <= MAX_CONTEXT_CAPTURE_BYTES
        document, state = verify_capture(saved)
        assert state == "verified" and document["context_bytes_used"] == len(data)
        resource, = document["contexts"][0]["resources"]
        assert resource["content_range"] == span and resource["content"] == result["content"]
        assert resource["sha256"] == hashlib.sha256(data).hexdigest()
        assert resource["source_sha256"] == hashlib.sha256(body).hexdigest()
        received.extend(data)
        if "next_byte_range" not in result:
            break
        result, _ = call(capsys, *result["next_read_args"])
    assert bytes(received) == body


@pytest.mark.parametrize("body", [
    bytes(random.Random(686).choices(b"abcdefghijklmnopqrstuvwxyz0123456789+/", k=153_600)),
    ("资料😀\t\r\n\u0001\\\"" * 2_000).encode(),
], ids=["entropy", "utf8-escaped"])
def test_default_pages_and_explicit_large_ranges_return_bounded_executable_continuations(
    tmp_path, capsys, body,
):
    store, revision, _ = store_edition(tmp_path, body)
    argv = ["read", "store:paging-demo", "--store", str(store.workspace),
            "--revision", revision, "--resource", "pages.md"]
    page, _ = call(capsys, *argv)
    assert "resources" not in page and "required_resources" not in page
    explicit, _ = call(capsys, *argv, "--byte-range", "0", str(len(body)))
    assert explicit["content"] == page["content"]
    received = bytearray()
    while True:
        raw = page["content"].encode()
        assert len(json.dumps(page["content"], ensure_ascii=False).encode()) <= INLINE_PAGE_BYTES
        assert page["content_range"]["start"] == len(received)
        assert page["content_range"]["end"] == len(received) + len(raw)
        received.extend(raw)
        if "next_read_args" not in page:
            break
        continuation = page["next_read_args"]
        assert continuation[:4] == ["read", "store:paging-demo", "--revision", revision]
        for flag, value in (("--store", str(store.workspace)), ("--resource", "pages.md")):
            assert continuation[continuation.index(flag) + 1] == value
        assert "--omit-resources" in continuation
        assert continuation[-3:] == ["--byte-range", *map(str, page["next_byte_range"])]
        page, _ = call(capsys, *continuation)
    assert received == body


def test_scoped_empty_checkout_link_is_audit_only(tmp_path, capsys):
    from tests.knowledge.test_knowledge_find import _plant_case

    library, campaign = tmp_path / "library", tmp_path / "campaign"
    _plant_case(library, "casebook")
    owner = library / "casebook"
    body = owner / "SKILL.md"
    with body.open("a", encoding="utf-8") as stream:
        stream.write("\n[Empty reference](references/empty.md).\n")
    (owner / "references").mkdir()
    (owner / "references/empty.md").touch()
    call(capsys, "evidence", "init", "--id", "empty", "--directory", str(campaign))
    found, _ = call(
        capsys, "find", "casebook optimization benchmark", "--session", str(campaign),
        "--skill-root", str(library), "--kinds", "skill", "--limit", "5",
    )
    hit = next(item for item in found["items"] if item["id"] == "casebook")
    argv = [*hit["read_args"], "--resource", "references/empty.md"]
    view, output = call(capsys, *argv)
    reference = view["reference"]
    assert view["content"] == "" and reference["kind"] == "empty_context"
    receipt, status = verify_capture((campaign / reference["path"]).read_bytes())
    assert status == "verified" and receipt["context_bytes_used"] == 0
    from inferrsi.harness.manager import _state

    with pytest.raises(ValueError, match="delivered context"):
        _state._validate_knowledge_refs(campaign, [reference], [reference["path"]])
    rows = _operation(tmp_path, [sys.executable, "-m", "inferrsi", *argv], output, "read")
    _, archive = _import(tmp_path, rows, campaign=campaign, context_ids=[receipt["context_id"]])
    assert archive["coverage"] == "complete" and archive["observed"]["used"] == 0
    event, = archive["events"]
    assert event["delivery"]["visible_resources"] == []


def test_content_read_does_not_expand_the_package_inventory(tmp_path, capsys):
    ref = "package:inferrsi.common.skills.inference_benchmark_design"
    revision = KnowledgeReader().read(ref).revision
    inventory, _ = call(capsys, "read", ref, "--revision", revision)
    assert len(inventory["resources"]) > 100
    assert "content" not in inventory
    page, _ = call(capsys, "read", ref, "--revision", revision,
                   "--resource", "references/benchmark-commands.md")
    assert page["content"] and page["next_read_args"]
    assert "resources" not in page and "required_resources" not in page


@pytest.mark.parametrize("scoped", [False, True])
def test_archive_only_attributes_the_selected_bytes_and_their_source_line(tmp_path, capsys, scoped):
    body = "一\nsecond line\nlast".encode()
    store, revision, _ = store_edition(tmp_path, body)
    root = tmp_path / "campaign"
    call(capsys, "evidence", "init", "--id", "range", "--directory", str(root))
    argv = ["read", "store:paging-demo", "--store", str(store.workspace), "--revision", revision]
    if scoped:
        found, _ = call(capsys, "find", "pagingdemo", "--session", str(root),
                        "--store", str(store.workspace), "--limit", "1")
        argv = found["items"][0]["read_args"]
    argv = [*argv, "--resource", "pages.md", "--byte-range", "4", "11"]
    result, output = call(capsys, *argv)
    assert result["content"] == "second line" and result["next_byte_range"] == [15, 11]
    rows = _operation(tmp_path, [sys.executable, "-m", "inferrsi", *argv], output, "read")
    _, archive = _import(tmp_path, rows, campaign=root)
    event, = archive["events"]
    assert event["materials"][0]["content_range"] == result["content_range"]
    resource, = event["delivery"]["visible_resources"]
    assert resource["content_range"] == result["content_range"]
    passage, = event["delivery"]["passages"]
    assert (passage["line"], passage["text"]) == (2, "second line")
    if scoped:
        _, via_capture = _import(tmp_path, rows, campaign=root,
                                 context_ids=[Path(result["reference"]["path"]).stem])
        event, = via_capture["events"]
        assert event["materials"][0]["content_range"] == result["content_range"]
        assert event["delivery"]["visible_resources"] == [resource]


def test_utf8_bounds_and_projected_skill_ranges(tmp_path, capsys):
    ref = "package:inferrsi.common.skills.inference_benchmark_design"
    bundle = KnowledgeReader().read(ref)
    path = bundle.metadata["skill_documents"]["original"]
    root = tmp_path / "campaign"
    call(capsys, "evidence", "init", "--id", "cuda", "--directory", str(root), "--backend", "cuda")
    result, _ = call(capsys, "find", "inference benchmark design", "--repo-type", "inferrsi",
                     "--session", str(root), "--limit", "1")
    argv = result["items"][0]["read_args"]
    full, _ = call(capsys, *argv)
    split = full["content_view"]["source_byte_ranges"][0][1]
    row, _ = call(capsys, *argv, "--byte-range", str(split - 1), "4")
    proof = row["content_view"]
    assert row["content"].encode() == full["content"].encode()[split - 1:split + 3]
    assert len(proof["source_byte_ranges"]) == 2
    source_parts = [bundle.content[path][lo:hi] for lo, hi in proof["source_byte_ranges"]]
    assert b"".join(source_parts) == row["content"].encode()
    assert proof["sha256"] == hashlib.sha256(row["content"].encode()).hexdigest()
    for requested in (["-1", "10"], ["0", "0"], [str(len(bundle.content[path])), "10"]):
        with pytest.raises(SystemExit):
            main(["read", ref, "--resource", path, "--revision", bundle.revision,
                  "--byte-range", *requested])
    with pytest.raises(SystemExit):
        main(["read", ref, "--resource", path, "--byte-range", "0", "5"])

    store, revision, _ = store_edition(tmp_path, "x😀 measurement".encode())
    argv = ["read", "store:paging-demo", "--store", str(store.workspace), "--revision", revision,
            "--resource", "pages.md", "--byte-range"]
    first, _ = call(capsys, *argv, "0", "1")
    assert first["content"] == "x" and first["next_byte_range"] == [1, 4]
    for start, size in (("1", "1"), ("2", "6")):
        with pytest.raises(SystemExit):
            main([*argv, start, size])
