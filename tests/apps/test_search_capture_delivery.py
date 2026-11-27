import json
import shutil
from pathlib import Path

import pytest

from inferrsi.apps.views.capture_delivery import (
    capture_event,
    capture_return_texts,
    visible_capture_resources,
)
from inferrsi.apps.views.search_attribution import import_search
from inferrsi.apps.workflows.campaign import capture_context, create_campaign, save_retrieval
from inferrsi.knowledge.catalog import search_knowledge
from inferrsi.knowledge.context_projection import assemble_context_text
from inferrsi.knowledge.knowledge_operations import KnowledgeReader
from tests.fixtures.knowledge_retrieval import install_legacy_capture


def _review(path, **fields):
    path.write_text(json.dumps({
        "task": "Check knowledge delivery.",
        "corpus": {"repository": "example/knowledge", "revision": "a" * 40, "root": "."},
        "decisions": [],
        **fields,
    }), encoding="utf-8")
    return path


def test_delivery_requires_a_versioned_resource_block_in_a_model_tool_return(tmp_path):
    context = {
        "ref": "package:case", "revision": "r1", "omissions": [],
        "resources": [
            {"path": "case.md", "content": "Check residency before initializing."},
            {"path": "other.md", "content": "Second resource."},
        ],
    }
    doc = {"contexts": [context]}
    block = assemble_context_text([{**context, "resources": context["resources"][:1]}])
    trace = tmp_path / "trace.jsonl"

    def output(text):
        return {"type": "response_item", "payload": {"type": "custom_tool_call_output",
                "output": [{"type": "input_text", "text": text}]}}

    trace.write_text("\n".join(json.dumps(row) for row in [
        {"type": "session_meta"}, output("knowledge/r1.json"),
        output(block.replace("@ r1", "@ r2")), output(block.rstrip("\n")),
        {"type": "response_item", "payload": {"type": "message", "role": "assistant"}},
    ]))
    for number in (2, 3, 4):
        texts = capture_return_texts(trace, (2, 5), {"r1": number}, ["r1"])
        expected = [{"ref": "package:case", "path": "case.md"}] if number == 4 else []
        assert visible_capture_resources(doc, texts["r1"]) == expected
    with pytest.raises(ValueError, match="model-facing"):
        capture_return_texts(trace, (2, 5), {"r1": 5}, ["r1"])
    with pytest.raises(ValueError, match="outside the round"):
        capture_return_texts(trace, (2, 3), {"r1": 4}, ["r1"])


def test_round_counts_search_but_retains_exact_reads_and_inventory(tmp_path):
    root = tmp_path / "campaign"
    create_campaign(root, "capture-counts")
    reader = KnowledgeReader()
    record = "package:inferrsi.common.skills.cgroup_resource_controls"
    revision = reader.read(record).revision
    capture_context(root, context_id="pin", reader=reader, ids=[record],
                    revisions={record: revision})
    save_retrieval(root, context_id="catalog", result=search_knowledge(limit=1, explain=True))
    install_legacy_capture(root, "manual-query", "query")

    archive = import_search(
        root, number=1, context_ids=["pin", "catalog", "query"], complete=True,
        archive_review=_review(tmp_path / "review.json"),
    )
    for path in (root / "search/round-1.json", archive):
        saved = json.loads(path.read_bytes())
        assert saved["counts"] == {"searches": 1, "hits": 1, "unique_hits": 1, "used": 0}
        pinned, inventory, discovery = saved["events"]
        assert [event["action"] for event in (pinned, inventory, discovery)] == [
            "read", "inventory", "search",
        ]
        assert pinned["materials"][0]["revision"] == revision
        assert inventory["materials"][0]["revision"].startswith("catalog-sha256:")
        assert discovery["tool"] == "find"


@pytest.mark.parametrize("observation", [
    None,
    {
        "schema_version": 1,
        "request": {"query": "cgroupv2"},
        "selection": {"state": "not_requested", "ranking_applied": False},
    },
])
def test_legacy_capture_remains_search_when_ranking_is_unknown_or_unrequested(observation):
    doc = {"items": [], "contexts": [], "request": {}, "retrieval": observation}
    assert capture_event("legacy", (doc, "knowledge/legacy.json", "a" * 64))["action"] == "search"


def test_archive_accepts_complete_managed_json_at_the_matching_capture(tmp_path):
    root = tmp_path / "campaign"
    create_campaign(root, "managed-return")
    path, digest = install_legacy_capture(root, "case-return", "r1")
    capture = json.loads(path.read_bytes())
    context, = capture["contexts"]
    resource = next(item for item in context["resources"] if item["path"].endswith(".md"))
    reference = {"path": "knowledge/r1.json", "sha256": digest, "kind": "delivered_context"}
    response = {"reference": reference, "context": capture}
    trace = tmp_path / "trace.jsonl"
    quote = "Check the observed residency before choosing a mitigation."

    def write_trace(output):
        rows = [
            {"type": "session_meta", "payload": {"id": "managed-session"}},
            {"type": "response_item", "payload": {"type": "custom_tool_call_output",
              "output": [{"type": "input_text", "text": "Output:\n" + output}]}},
            {"type": "response_item", "payload": {"type": "message", "role": "assistant",
              "phase": "final_answer", "content": [{"type": "output_text", "text": quote}]}},
        ]
        trace.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    review = _review(
        tmp_path / "review.json", capture_returns={"r1": 2},
        decisions=[{"use": "used", "ref": context["ref"], "event_line": 2,
                    "passage_path": resource["path"], "passage_line": 1,
                    "decision_line": 3, "decision_quote": quote}],
    )
    inputs = {
        "number": 1, "context_ids": ["r1"], "trace": trace, "lines": (2, 3),
        "knowledge_root": tmp_path.resolve(), "archive_review": review,
    }
    exact = json.dumps(response, ensure_ascii=False, indent=2)
    for invalid in (
        json.dumps(reference),
        exact.replace(digest, "0" * 64, 1),
        json.dumps({**response, "context": {**capture, "assembled_text": ""}},
                   ensure_ascii=False, indent=2),
        exact[:-1],
    ):
        write_trace(invalid)
        with pytest.raises(ValueError, match="matching visible captured resource"):
            import_search(root, **inputs)
        assert not (root / "search/archive/round-1.json").exists()

    write_trace(exact)
    saved = json.loads(import_search(root, **inputs).read_bytes())
    event, = saved["events"]
    assert event["delivery"]["state"] == "visible"
    assert event["delivery"]["return_line"] == 2
    evidence, = saved["materials"][context["ref"]]["evidence"]
    assert evidence["basis"] == "archive_reviewed"
    assert evidence["passage_path"] == resource["path"]
    assert evidence["passage_text"] == resource["content"].splitlines()[0]
    write_trace(exact.replace("\n", "\r\n"))
    assert json.loads(import_search(root, **inputs).read_bytes()) == saved


def test_manual_find_reads_body_and_each_requested_attachment_without_a_budget(tmp_path, capsys):
    from inferrsi import __version__
    from inferrsi.apps.cli import main
    from tests.apps.test_campaign_task_selection import BASELINE_CUE

    root = tmp_path / "campaign"
    create_campaign(root, "diffusion", backend="cuda")
    ref = "package:inferrsi.common.skills.inference_benchmark_design"
    bundle = KnowledgeReader().read(ref)
    links = ["references/benchmark-commands.md", "references/autotunebench-trial-validity.md"]
    attachments = [next(path for path in bundle.content if path.endswith("/" + link))
                   for link in links]
    assert main(["find", BASELINE_CUE, "--session", str(root),
                 "--limit", "2"]) == 0
    found = json.loads(capsys.readouterr().out)
    search = json.loads((root / found["reference"]["path"]).read_bytes())
    assert search["captured_by"] == f"inferrsi find {__version__}"
    assert search["request"]["backend"] == "cuda"
    assert search["request"]["sources"] == ["package", "checkout"]
    assert "context_bytes" not in search["request"] and not search["contexts"]
    first, _ = found["items"]
    assert first["material_ref"] == ref and "content" not in first
    assert main(first["read_args"]) == 0
    read = json.loads(capsys.readouterr().out)
    assert len(read["content"].encode("utf-8")) == first["next_read_content_bytes"]
    saved = json.loads((root / read["reference"]["path"]).read_bytes())
    assert saved["captured_by"] == f"inferrsi read {__version__}"
    resource, = saved["contexts"][0]["resources"]
    assert resource["content"] == read["content"]
    body = read["content"]
    page = read
    while "next_read_args" in page:
        assert main(page["next_read_args"]) == 0
        page = json.loads(capsys.readouterr().out)
        body += page["content"]
    from inferrsi.knowledge._skill_selection import skill_procedure

    expected, _ = skill_procedure(first["body_resource"], bundle.content[first["body_resource"]])
    assert len(expected) == 13_166 and body.encode() == expected
    for link, path in zip(links, attachments, strict=True):
        assert f"]({link})" in body
        assert main([*first["read_args"], "--resource", link]) == 0
        result = json.loads(capsys.readouterr().out)
        received = bytearray()
        while True:
            receipt = json.loads((root / result["reference"]["path"]).read_bytes())
            assert result["content_resource"] == receipt["request"]["resource"] == path
            assert result["revision"] == first["revision"]
            assert receipt["request"]["search_ref"] == found["reference"]["path"]
            assert receipt["context_budget"] is None and not receipt["context_omissions"]
            assert receipt["context_bytes_used"] == len(result["content"].encode())
            delivered, = receipt["contexts"][0]["resources"]
            assert (delivered["path"], delivered["role"]) == (path, "reference")
            received.extend(result["content"].encode())
            if "next_read_args" not in result:
                break
            assert main(result["next_read_args"]) == 0
            result = json.loads(capsys.readouterr().out)
        assert received == bundle.content[path]

    archive = import_search(root, number=1, context_ids=[search["context_id"], saved["context_id"]],
                            archive_review=_review(tmp_path / "review.json"))
    find_event, read_event = json.loads(archive.read_bytes())["events"]
    identity = {k: search["request"]["ranking_policy"][k]
                for k in ("id", "version", "config_sha256")}
    assert find_event["request"]["kinds"] == "case,skill,record"
    assert find_event["request"]["ranking_policy"] == identity
    assert read_event["request"]["ranking_policy"] == identity
    assert read_event["request"]["search_ref"] == found["reference"]["path"]
    assert read_event["request"]["resource"] == resource["path"]


def test_manual_find_reopens_the_returned_checkout_without_archiving_local_paths(tmp_path, capsys):
    from inferrsi.apps.cli import main
    from tests.knowledge.test_knowledge_find import _plant_case

    root, library = tmp_path / "campaign", tmp_path / "separate library"
    _plant_case(library, "casebook")
    create_campaign(root, "manual")
    assert main(["find", "mask caching ran out of device memory", "--kinds", "case",
                 "--skill-root", str(library), "--session", str(root),
                 "--limit", "1"]) == 0
    found = json.loads(capsys.readouterr().out)
    hit, = found["items"]
    assert hit["read_args"][hit["read_args"].index("--skill-root") + 1] == str(library)
    assert str(library) not in (root / found["reference"]["path"]).read_text(encoding="utf-8")
    assert found["sources"] == ["checkout"]
    assert main(hit["read_args"]) == 0
    read = json.loads(capsys.readouterr().out)
    assert read["revision"] == hit["revision"] and "910B1" in read["content"]
    case = library / "casebook/cases/qwen-ascend-rejected-directions.md"
    case.write_text(case.read_text(encoding="utf-8") + "\nUpdated.\n", encoding="utf-8")
    with pytest.raises(SystemExit) as changed:
        main(hit["read_args"])
    assert changed.value.code == 2


@pytest.mark.parametrize("scoped", [False, True])
def test_body_link_read_archives_the_resolved_attachment(tmp_path, scoped):
    from tests.apps.test_campaign_task_selection import BASELINE_CUE
    from tests.apps.test_codex_knowledge_search import _cli, _import, _operation

    root = tmp_path / "campaign"
    create_campaign(root, "diffusion", backend="cuda")
    scope = ["--session", str(root)] if scoped else []
    argv, output = _cli(tmp_path, "find", BASELINE_CUE, "--limit", "1", "--backend", "cuda",
                        "--no-external", "--json", *scope)
    hit, = json.loads(output)["items"]
    _, procedure = _cli(tmp_path, *hit["read_args"])
    link = "references/benchmark-commands.md"
    assert f"]({link})" in json.loads(procedure)["content"]
    read_argv, opened = _cli(tmp_path, *hit["read_args"], "--resource", link)
    view = json.loads(opened)
    assert view["revision"] == json.loads(procedure)["revision"]
    path = view["body_resource"].removesuffix("/SKILL.md") + "/" + link
    assert view["content_resource"] == path

    rows = [*_operation(tmp_path, argv, output, "find"),
            *_operation(tmp_path, read_argv, opened, "attachment")]
    for report in _import(tmp_path, rows, campaign=root):
        assert report["coverage"] == "complete" and report["counts"]["used"] == 0
        read = report["events"][-1]
        assert read["delivery"]["visible_resources"] == [
            {"ref": view["ref"], "path": path, "content_range": view["content_range"]},
        ]


@pytest.mark.parametrize(("case", "unresolved"), [
    ("matched", []), ("other_campaign", [3, 6]), ("clipped_read", [6]), ("changed_read", [6]),
])
def test_selected_find_and_read_match_their_native_stdout_once(tmp_path, case, unresolved):
    from tests.apps.test_codex_knowledge_search import _cli, _import, _operation

    root = tmp_path / "campaign"
    create_campaign(root, "native-returns")
    find_argv, found = _cli(tmp_path, "find", "cgroupv2", "--session", str(root),
                            "--no-external", "--limit", "1", "--json")
    hit, = json.loads(found)["items"]
    read_argv, opened = _cli(tmp_path, *hit["read_args"])
    rows, ids = [], []
    for tool, argv, output in (("find", find_argv, found), ("read", read_argv, opened)):
        call, event, returned = _operation(tmp_path, argv, output, tool)
        cmd = call["payload"]["arguments"]["cmd"].replace("\\", "\\\\").replace("'", "\\'")
        call["payload"] = {
            "type": "custom_tool_call", "name": "exec", "call_id": tool,
            "input": f"const r=await tools.exec_command({{cmd:'{cmd}'}});text(r.output);",
        }
        visible = output
        if tool == "read" and case == "clipped_read":
            visible = "Warning: truncated output\n" + output[:120]
        elif tool == "read" and case == "changed_read":
            visible = output.replace('"content": "', '"content": "altered ', 1)
        returned["payload"] = {"type": "custom_tool_call_output", "call_id": tool, "output": [
            {"type": "input_text", "text": "Script completed\nWall time 0.4 seconds\nOutput:\n"},
            {"type": "input_text", "text": visible},
        ]}
        rows.extend((call, event, returned))
        ids.append(Path(json.loads(output)["reference"]["path"]).stem)
    if case == "other_campaign":
        # The exact captured bytes alone cannot bind a command issued in a different directory.
        root = shutil.copytree(root, tmp_path / "different-campaign")

    local, archive = _import(tmp_path, rows, context_ids=ids, campaign=root)
    for report in (local, archive):
        assert [event["context_id"] for event in report["events"]] == ids
        assert [event["action"] for event in report["events"]] == ["search", "read"]
        assert report["observed"] == {"searches": 1, "hits": 1, "unique_hits": 1, "used": 0}
        assert report["coverage"] == ("partial" if unresolved else "complete")
        assert report["unresolved_command_lines"] == unresolved
    assert [(d["trace_line"], d["action"], d["reason"]) for d in archive["unresolved_details"]] == [
        (line, "search" if line == 3 else "read", "capture_unverified") for line in unresolved
    ]
    if case == "matched":
        search, read = archive["events"]
        assert search["delivery"]["visible_refs"] == [hit["material_ref"]]
        assert search["delivery"]["return_line"] == 4
        assert read["delivery"]["return_line"] == 7
        assert read["delivery"]["visible_resources"] == [
            {"ref": hit["material_ref"], "path": hit["body_resource"],
             "content_range": json.loads(opened)["content_range"]},
        ]
    elif case in ("clipped_read", "changed_read"):
        assert archive["events"][1]["delivery"]["state"] == "unknown"


def test_scoped_find_records_the_catalog_filters_and_effective_store_scope(tmp_path, capsys):
    from inferrsi.apps.cli import main
    from inferrsi.knowledge.knowledge_store import KnowledgeStore

    root, store = tmp_path / "manual", tmp_path / "store"
    store.mkdir()
    KnowledgeStore(store, skill_root=None)
    create_campaign(root, "filtered")
    args = ["find", "diffusion", "--session", str(root), "--store", str(store),
            "--kinds", "record", "--backend", "cuda", "--limit", "1"]
    assert main(args) == 0
    found = json.loads(capsys.readouterr().out)
    assert found["sources"] == ["package", "store"]
    filters = ["--repo-type", "vllm_omni", "--tier", "contribution", "--scenario", "diffusion.t2i"]
    with pytest.raises(SystemExit) as error:
        main([*args, *filters])
    assert error.value.code == 2 and "--store" in capsys.readouterr().err
    args = [word for word in args if word not in ("--store", str(store))]
    assert main([*args, *filters]) == 0
    catalog = json.loads(capsys.readouterr().out)
    request = json.loads((root / catalog["reference"]["path"]).read_bytes())["request"]
    assert request["sources"] == catalog["sources"] == ["package"]
    assert (request["repo"], request["tier"], request["scenario"], request["kinds"],
            request["backend"]) == ("vllm_omni", "contribution", "diffusion.t2i", "record", "cuda")
