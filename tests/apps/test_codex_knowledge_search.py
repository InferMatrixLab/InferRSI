"""Import real CLI results from a bounded synthetic Codex rollout."""

import gzip
import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from inferrsi.apps.workflows.knowledge import collect_archive, knowledge_reader
from tests.fixtures.knowledge_retrieval import install_legacy_capture, legacy_records

ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "src/inferrsi/knowledge/data/skill_library"
QUERY = "cache per-step masks ran out of device memory"
REF = "checkout:case.qwen-ascend-rejected-directions"
PASSAGE = "# Qwen Ascend: reported rejected directions"
DECISION = "I will check peak device memory before retaining per-step masks."


def _cli(cwd, *args):
    argv = [sys.executable, "-X", "utf8", "-m", "inferrsi", *args]
    return argv, _run(cwd, argv)


def _historical_capture(campaign, context_id, options):
    """Build the original manual argv and path-only response from the capture API."""
    from inferrsi.apps.cli.arguments import parser
    from inferrsi.apps.workflows.campaign import capture_context
    from inferrsi.knowledge.knowledge_operations import KnowledgeReader

    words = ["campaign", "capture-context", "--directory", str(campaign), "--limit", "1",
             "--id", context_id, *options]
    args = parser(historical=True).parse_args(words)
    if args.query or (args.relevance and not args.ids):
        sample = "manual-query" if args.query else "manual-relevance"
        path, digest = install_legacy_capture(campaign, sample, context_id)
    else:
        path, digest = capture_context(campaign, context_id=context_id, reader=KnowledgeReader(),
                                       relevance=args.relevance, ids=args.ids, limit=1)
    result = {"context": path.relative_to(campaign).as_posix(), "sha256": digest}
    return [sys.executable, "-m", "inferrsi", *words], json.dumps(result, indent=2) + "\n"


def _run(cwd, argv):
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(ROOT / "src"), *sys.path]))
    env.update(HOME=str(cwd / "home"), USERPROFILE=str(cwd / "home"))
    env.pop("INFERRSI_LAUNCHER", None)
    result = subprocess.run(argv, env=env, cwd=cwd, capture_output=True,
                            text=True, encoding="utf-8", check=True)
    assert result.stdout
    return result.stdout


def _operation(cwd, argv, stdout, identity, *, received=True, script=None):
    cmd = script or shlex.join(argv)
    item = {"type": "CommandExecution", "id": identity, "cwd": cwd.as_uri(),
            "command": ["/bin/sh", "-lc", cmd] if os.name == "posix" else argv,
            "exit_code": 0, "aggregated_output": stdout}
    rows = [
        {"type": "response_item", "payload": {
            "type": "function_call", "name": "exec_command", "call_id": identity,
            "arguments": {"cmd": cmd, "workdir": str(cwd)},
        }},
        {"type": "event_msg", "payload": {"type": "item_completed", "item": item}},
    ]
    if received is not None:
        output = stdout if received is True else received
        rows.append({"type": "response_item", "payload": {
            "type": "function_call_output", "call_id": identity, "output": f"Output:\n{output}",
        }})
    return rows


def _desktop_collect(cwd, argv, stdout, *, received=None):
    words = ["D:/scratch/venv/Scripts/python.exe", *argv[1:]]
    words[words.index("--skill-root") + 1] = "skill_library"
    script = " ".join(words)
    call, completed, returned = _operation(cwd, argv, stdout, "collect")
    call["payload"] = {
        "type": "custom_tool_call", "name": "exec", "call_id": "collect",
        "input": "const r = await tools.exec_command("
                 + json.dumps({"cmd": script, "workdir": str(cwd)}) + "); text(r);",
    }
    completed["payload"]["item"]["command"] = [
        r"C:\Program Files\PowerShell\7\pwsh.exe", "-Command", script,
    ]
    returned["payload"] = {"type": "custom_tool_call_output", "call_id": "collect", "output": [
        {"type": "input_text", "text": "Script completed\nWall time 0.4 seconds\nOutput:\n"},
        {"type": "input_text", "text": json.dumps({
            "chunk_id": "demo", "wall_time_seconds": 0.4, "exit_code": 0,
            "output": stdout if received is None else received,
        })},
    ]}
    return call, completed, returned


def _import(tmp_path, rows, *, decisions=(), context_ids=(), campaign=None, capture_returns=None):
    trace = tmp_path / "rollout.jsonl"
    campaign = campaign or tmp_path / "campaign"
    meta = {"type": "session_meta", "payload": {"id": "synthetic-cli", "cwd": str(tmp_path)}}
    trace.write_text("".join(json.dumps(row) + "\n" for row in [meta, *rows]), encoding="utf-8")
    review = tmp_path / "review.json"
    review.write_text(json.dumps({
        "task": "Review a retained CLI search", "decisions": list(decisions),
        "capture_returns": capture_returns or {},
        "corpus": {"repository": "InferMatrixLab/InferRSI", "revision": "a" * 40,
                   "root": "src/inferrsi/knowledge/data/skill_library"},
    }), encoding="utf-8")
    if not campaign.exists():
        _cli(tmp_path, "evidence", "init", "--directory", str(campaign), "--id", "example")
    _, output = _cli(tmp_path, "evidence", "import-search", "--directory", str(campaign),
                     "--round", "1", "--trace", str(trace), "--lines", "2", str(len(rows) + 1),
                     "--knowledge-root", str(LIBRARY), "--complete",
                     "--archive-review", str(review),
                     *(word for key in context_ids for word in ("--context-id", key)))
    return (json.loads((campaign / "search/round-1.json").read_text(encoding="utf-8")),
            json.loads((campaign / json.loads(output)["record"]).read_text(encoding="utf-8")))


@pytest.mark.parametrize("json_output", [False, True])
def test_direct_find_and_read_import(tmp_path, json_output):
    find_args = ("find", QUERY, "--kinds", "case", "--limit", "1", "--no-external")
    find_argv, found = _cli(tmp_path, *find_args, *(["--json"] if json_output else []))
    if not json_output and os.name == "posix":
        read_argv = shlex.split(next(line.split("open: ", 1)[1] for line in found.splitlines()
                                     if line.startswith("     open: ")))
    else:
        encoded = found if json_output else _cli(tmp_path, *find_args, "--json")[1]
        read_argv = json.loads(encoded)["items"][0]["open_argv"]
    read_script = None
    if not json_output and os.name == "posix":
        # Exercise the documented single command written across two lines.
        read_script = shlex.join(read_argv).replace(" --material", " \\\n  --material", 1)
    opened = _run(tmp_path, ["/bin/sh", "-c", read_script] if read_script else read_argv)
    view = json.loads(opened)
    assert view["content"].startswith(PASSAGE)
    rows = [*_operation(tmp_path, find_argv, found, "find"),
            *_operation(tmp_path, read_argv, opened, "read", script=read_script),
            {"type": "response_item", "payload": {
                "type": "message", "role": "assistant", "phase": "final_answer",
                "content": [{"type": "output_text", "text": DECISION}],
            }}]
    local, archive = _import(tmp_path, rows)
    for record in (local, archive):
        assert record["coverage"] == "complete"
        assert record["counts"] == {"searches": 1, "hits": 1, "unique_hits": 1, "used": 0}
        search, read = record["events"]
        assert (search["tool"], search["action"], search["query"]) == ("find", "search", QUERY)
        assert search["materials"][0]["ref"] == REF
        assert search["delivery"]["visible_refs"] == [REF]
        assert search["delivery"].get("passages", []) == []
        assert (read["tool"], read["action"]) == ("read", "read")
        assert read["materials"][0]["revision"] == view["revision"]
        assert read["delivery"]["visible_resources"] == [{"ref": REF, "path": view["entrypoint"]}]
        assert record["materials"][REF]["delivery_state"] == "visible"
        assert record["materials"][REF]["use"] == "unknown"
    assert PASSAGE not in json.dumps(local)
    assert archive["events"][1]["delivery"]["passages"][0]["text"] == PASSAGE

    review = {"ref": REF, "use": "used", "event_line": 6, "passage_line": 1,
              "passage_path": view["entrypoint"], "decision_line": 8, "decision_quote": DECISION}
    _, reviewed = _import(tmp_path, rows, decisions=[review])
    assert reviewed["counts"]["used"] == 1
    assert reviewed["materials"][REF]["evidence"][0]["passage_text"] == PASSAGE
    # Search and visible read now carry the same version, so the decision can be attributed.
    assert reviewed["materials"][REF]["evidence"][0]["event_id"] == read["id"]
    assert reviewed["events"][0]["materials"][0]["revision"] == view["revision"]
    assert reviewed["adoption"] == {
        "search_hits": {"adopted": 1, "unique_hits": 1, "state": "complete"},
        "direct_reads": {"adopted": 0, "read_only": 0, "state": "not_applicable"},
        "unverified_reads": {"adopted": 0, "refs": 0},
        "other_adopted": 0, "attribution_unknown": 0, "unique_hit_revisions": 1}


@pytest.mark.parametrize("issue", ["missing_result", "truncated_result", "replaced_result"])
def test_unverified_direct_returns_remain_partial(tmp_path, issue):
    find_argv, found = _cli(tmp_path, "find", QUERY, "--kinds", "case", "--limit", "1",
                            "--no-external", "--json")
    read_argv = json.loads(found)["items"][0]["open_argv"]
    opened = _run(tmp_path, read_argv)
    received = {"missing_result": None,
                "truncated_result": "Warning: truncated output\n" + opened[:500],
                "replaced_result": '{"content": "Different body"}\n'}[issue]
    rows = [*_operation(tmp_path, find_argv, found, "find"),
            *_operation(tmp_path, read_argv, opened, "read", received=received)]
    for record in _import(tmp_path, rows):
        assert record["coverage"] == "partial" and record["counts"] is None
        assert record["observed"] == {"searches": 1, "hits": 1, "unique_hits": 1, "used": 0}
        assert record["unresolved_command_lines"] == [6]
        assert record["events"][1]["delivery"]["state"] == "unknown"
        assert record["materials"][REF]["delivery_state"] == "ref_visible"
        assert PASSAGE not in json.dumps(record)


def test_no_match_and_unqualified_metadata_read_are_verified_without_content(tmp_path):
    find_argv, found = _cli(tmp_path, "find", "zzcanarymissingqv", "--json")
    assert json.loads(found)["no_match"]
    read_argv, opened = _cli(tmp_path, "read", REF.split(":", 1)[1], "--installed-library")
    view = json.loads(opened)
    assert view["content"] == view["entrypoint"]  # The metadata contains a path.
    for record in _import(tmp_path, [
        *_operation(tmp_path, find_argv, found, "find"),
        *_operation(tmp_path, read_argv, opened, "read"),
    ]):
        assert record["coverage"] == "complete"
        assert record["counts"] == {"searches": 1, "hits": 0, "unique_hits": 0, "used": 0}
        assert record["materials"][REF]["delivery_state"] == "ref_visible"
        assert not record["events"][1]["delivery"].get("visible_resources")


@pytest.mark.parametrize("mode", ["catalog-text", "catalog-json"])
def test_find_archive_uses_the_returned_owner_and_pin(tmp_path, mode):
    options = ["inference benchmark design", "--repo-type", "inferrsi", "--no-external"]
    argv, result = _cli(tmp_path, "find", *options, "--limit", "1",
                        *(["--json"] if mode.endswith("json") else []))
    if mode.endswith("text"):
        opening = next(line for line in result.splitlines() if line.strip().startswith("open"))
        args = shlex.split(opening.split(": ", 1)[1].removeprefix("& "))
        offset = args.index("read")
        read_args = args[offset:]
    else:
        read_args = json.loads(result)["items"][0]["read_args"]
    expected = {"ref": read_args[1], "revision": read_args[read_args.index("--revision") + 1]}
    assert expected["ref"].startswith("package:")
    _, archive = _import(tmp_path, _operation(tmp_path, argv, result, "find"))
    assert archive["coverage"] == "complete"
    material, = archive["events"][0]["materials"]
    assert {key: material[key] for key in expected} == expected


@pytest.mark.parametrize("version", ["research", "model-find"])
def test_archived_model_commands_keep_their_actual_hits_and_pins(tmp_path, version):
    # Saved real CLI returns. Their original argv and generating revisions travel with them.
    fixture = ROOT / "tests/fixtures/legacy/model_research_returns.json.gz"
    samples = json.loads(gzip.decompress(fixture.read_bytes()))[version]["samples"]
    rows = []
    for label, run in samples.items():
        rows.extend(_operation(tmp_path, run["argv"], run["stdout"], label))
    _, record = _import(tmp_path, rows)
    assert record["coverage"] == "complete"
    assert record["counts"] == {"searches": 2, "hits": 1, "unique_hits": 1, "used": 0}
    hit, empty = record["events"]
    assert hit["action"] == empty["action"] == "search"
    assert hit["query"] == "MiniMax-H3" and empty["query"] == "zzcanaryunknownqx"
    assert not empty["materials"] and not hit["delivery"].get("visible_resources")
    item, = hit["materials"]
    assert item["ref"] == "package:vllm_omni.ascend.diffusion.minimax_h3_reference_kv_reuse"
    if version == "model-find":
        returned, = json.loads(samples["hit"]["stdout"])["items"]
        assert item["revision"] == returned["revision"]
    else:
        assert "revision" not in item

    run = samples["hit"]
    clipped = "Warning: truncated output\n" + run["stdout"][:200]
    other = tmp_path / "clipped"
    other.mkdir()
    _, partial = _import(other, _operation(other, run["argv"], run["stdout"], "clip",
                                          received=clipped))
    assert partial["coverage"] == "partial" and partial["counts"] is None
    assert partial["unresolved_command_lines"] and partial["observed"]["used"] == 0


def test_unarchived_compatibility_query_prevents_false_complete_coverage(tmp_path):
    argv = [sys.executable, "-m", "inferrsi", "collect", "--relevance", QUERY, "--limit", "1",
            "--json"]
    output = json.dumps(legacy_records()["samples"]["unarchived"], indent=2)
    for record in _import(tmp_path, _operation(tmp_path, argv, output, "collect")):
        assert record["coverage"] == "partial" and record["counts"] is None
        assert record["observed"]["searches"] == 1
        assert record["unresolved_command_lines"] == [3]


def _archive_collect(tmp_path, *, inventory=False, empty=False):
    _cli(tmp_path, "evidence", "init", "--directory", "campaign", "--id", "example")
    options = ("--skill-root", str(LIBRARY))
    kwargs = {"context_bytes": 65536}
    options += ("--context-bytes", "65536")
    if inventory:
        options += ("--kind", "case", "--limit", "1")
        kwargs.update(kind="case", limit=1)
        if empty:
            options += ("--scenario", "rfc762.nothing-matches")
            kwargs["scenario"] = "rfc762.nothing-matches"
    else:
        options += ("--id", REF, "--limit", "5")
        _, plain = _cli(tmp_path, "collect", *options, "--json")
        item, = json.loads(plain)["items"]
        assert not (tmp_path / "campaign/knowledge/r1.json").exists()
        options += ("--revision", f"{REF}={item['revision']}")
        kwargs.update(ids=[REF], revisions={REF: item["revision"]}, limit=5)
    result = collect_archive(tmp_path / "campaign", context_id="r1",
                             reader=knowledge_reader(skill_root=LIBRARY), **kwargs)
    return ([sys.executable, "-X", "utf8", "-m", "inferrsi", "collect",
             *options, "--archive", "campaign", "--capture-id", "r1"],
            json.dumps(result, ensure_ascii=False, indent=2) + "\n")


def test_collect_receipt_attribution_and_same_round_reimport(tmp_path):
    argv, stdout = _archive_collect(tmp_path)
    campaign = tmp_path / "campaign"
    response = json.loads(stdout)
    reference, context = response["reference"], response["context"]
    capture_file = campaign / reference["path"]
    raw = capture_file.read_bytes()
    assert (reference["path"], reference["kind"]) == ("knowledge/r1.json", "delivered_context")
    assert reference["sha256"] == hashlib.sha256(raw).hexdigest()
    assert context == json.loads(raw)
    assert context["request"]["limit"] == 5 and context["request"]["context_bytes"] == 65536
    item, = context["items"]
    revision = item["revision"]
    assert item["ref"] == REF and context["request"]["revisions"] == {REF: revision}
    resource = next(r for c in context["contexts"] for r in c["resources"]
                    if r["content"].startswith(PASSAGE))
    assert resource["sha256"] == hashlib.sha256(resource["content"].encode()).hexdigest()
    assembled = context["assembled_text"].encode()
    assert context["assembled_sha256"] == hashlib.sha256(assembled).hexdigest()

    rows = [*_desktop_collect(tmp_path, argv, stdout), {
        "type": "response_item", "payload": {"type": "message", "role": "assistant",
            "phase": "final_answer", "content": [{"type": "output_text", "text": DECISION}]},
    }]
    for record in _import(tmp_path, rows, context_ids=["r1"]):
        assert record["coverage"] == "complete" and record["unresolved_command_lines"] == []
        assert record["counts"] == {"searches": 0, "hits": 0, "unique_hits": 0, "used": 0}
        event, = record["events"]
        assert (event["tool"], event["action"], event["source"], event["sha256"]) == (
            "collect", "read", reference["path"], reference["sha256"],
        )
        assert event["materials"][0]["revision"] == revision
        assert event["delivery"]["return_line"] == 4
        assert {"ref": REF, "path": resource["path"]} in event["delivery"]["visible_resources"]
        assert record["materials"][REF]["use"] == "unknown"
        assert record["adoption"]["direct_reads"] == {
            "read_only": 1, "adopted": 0, "state": "complete",
        }

    options = {"capture_returns": {"r1": 4}, "decisions": [{
        "ref": REF, "use": "used", "event_line": 4, "passage_line": 1,
        "passage_path": resource["path"], "decision_line": 5, "decision_quote": DECISION,
    }]}
    local, reviewed = _import(tmp_path, rows, context_ids=["r1"], **options)
    assert local["counts"]["used"] == 0
    assert reviewed["counts"] == {"searches": 0, "hits": 0, "unique_hits": 0, "used": 1}
    assert reviewed["adoption"]["direct_reads"] == {
        "read_only": 1, "adopted": 1, "state": "complete",
    }
    evidence, = reviewed["materials"][REF]["evidence"]
    assert evidence == {
        "use": "used", "basis": "archive_reviewed", "event_id": "capture:r1",
        "passage_line": 1, "passage_path": resource["path"], "passage_text": PASSAGE,
        "decision_line": 5, "decision_quote": DECISION,
    }
    ledger_files = (campaign / "search/round-1.json", campaign / "search/archive/round-1.json")
    snapshots = [path.read_bytes() for path in ledger_files]
    for ids in (["r1", "r1"], ["r1"]):
        assert _import(tmp_path, rows, context_ids=ids, **options) == (local, reviewed)
        assert [path.read_bytes() for path in ledger_files] == snapshots
    assert capture_file.read_bytes() == raw


def _replace_collect_sources(tmp_path, stdout, sources):
    response = json.loads(stdout)
    capture = response["context"]
    if sources is None:
        del capture["contexts"][0]["sources"]
    else:
        capture["items"][0]["sources"] = sources
        capture["contexts"][0]["sources"] = sources
    raw = json.dumps(capture, ensure_ascii=False, indent=2).encode("utf-8")
    reference = response["reference"]
    (tmp_path / "campaign" / reference["path"]).write_bytes(raw)
    reference["sha256"] = hashlib.sha256(raw).hexdigest()
    return json.dumps(response, ensure_ascii=False, indent=2) + "\n"


@pytest.mark.parametrize(
    "failure", [
        "clipped", "wrong_digest", "wrong_directory", "missing_command",
        "no_source", "empty_sources", "unidentifiable_source", "unversioned_document",
        "unversioned_paper", "null_document_version", "null_document_snapshot",
        "empty_document_snapshot", "invalid_document_snapshot",
    ],
)
def test_collect_receipt_requires_matched_command_and_complete_tool_return(tmp_path, failure):
    document = {"type": "document", "url": "https://example.com/document"}
    invalid_sources = {
        "no_source": None,
        "empty_sources": [],
        "unidentifiable_source": [{"type": "unknown", "note": "untraced"}],
        "unversioned_document": [document],
        "unversioned_paper": [{"type": "paper", "id": "10.0000/example"}],
        "null_document_version": [{**document, "version": None}],
        "null_document_snapshot": [{**document, "sha256": None}],
        "empty_document_snapshot": [{**document, "sha256": ""}],
        "invalid_document_snapshot": [{**document, "version": "  ", "sha256": "invalid"}],
    }
    argv, stdout = _archive_collect(tmp_path)
    received = None
    if failure == "clipped":
        received = "Warning: truncated output\n" + stdout[:120]
    elif failure == "wrong_digest":
        stdout = stdout.replace(json.loads(stdout)["reference"]["sha256"], "0" * 64, 1)
    elif failure == "wrong_directory":
        argv[argv.index("--archive") + 1] = "other"
    elif failure in invalid_sources:
        stdout = _replace_collect_sources(tmp_path, stdout, invalid_sources[failure])
    rows = _desktop_collect(tmp_path, argv, stdout, received=received)
    if failure == "missing_command":
        rows = rows[-1:]
    for record in _import(tmp_path, rows, context_ids=["r1"]):
        assert record["coverage"] == "partial" and record["counts"] is None
        assert record["unresolved_command_lines"] == ([] if failure == "missing_command" else [3])
        assert record["observed"]["used"] == 0
        assert record["materials"][REF]["use"] == "unknown"
        delivery = record["events"][0]["delivery"]
        assert delivery["state"] == "unknown" and delivery["visible_resources"] == []
    with pytest.raises(subprocess.CalledProcessError, match="returned non-zero") as error:
        _import(tmp_path, rows, context_ids=["r1"], capture_returns={"r1": len(rows) + 1})
    assert "Collect archive review must cite the matched tool return" in error.value.stderr


@pytest.mark.parametrize("source", [
    {"type": "paper", "id": "10.0000/example", "version": None},
    {"type": "document", "url": "https://example.com/document", "version": "edition 2"},
    {"type": "document", "url": "https://example.com/document", "sha256": "ac" * 32},
])
def test_collect_receipt_retains_identifiable_source(tmp_path, source):
    argv, stdout = _archive_collect(tmp_path)
    rows = _desktop_collect(tmp_path, argv, _replace_collect_sources(tmp_path, stdout, [source]))
    for record in _import(tmp_path, rows, context_ids=["r1"]):
        assert record["coverage"] == "complete" and record["counts"] is not None
        assert record["events"][0]["delivery"]["state"] == "visible"


@pytest.mark.parametrize("empty", [False, True])
def test_collect_inventory_receipt_is_not_a_search(tmp_path, empty):
    argv, stdout = _archive_collect(tmp_path, inventory=True, empty=empty)
    if empty:
        capture = json.loads(stdout)["context"]
        assert capture["items"] == capture["contexts"] == []
    rows = _operation(tmp_path, argv, stdout, "collect")
    for record in _import(tmp_path, rows, context_ids=["r1"]):
        assert record["coverage"] == "complete"
        assert record["events"][0]["action"] == "inventory"
        assert record["counts"] == {"searches": 0, "hits": 0, "unique_hits": 0, "used": 0}


@pytest.mark.parametrize("case", [
    "omitted", "matched", "wrong_id", "clipped", "inventory", "exact",
])
def test_manual_capture_search_coverage_requires_the_matching_receipt(tmp_path, case):
    campaign = tmp_path / "campaign"
    _cli(tmp_path, "evidence", "init", "--directory", str(campaign), "--id", "capture-test")
    if case == "inventory":
        options = ()
    elif case == "exact":
        options = (
            "--id-ref", "package:inferrsi.common.skills.cgroup_resource_controls",
            "--relevance", "cgroupv2",
        )
    else:
        options = ("--relevance", QUERY) if case == "omitted" else (QUERY,)
    argv, output = _historical_capture(campaign, "capture", options)
    context_ids = []
    if case in ("matched", "clipped"):
        context_ids = ["capture"]
    elif case == "wrong_id":
        _historical_capture(campaign, "other", options)
        context_ids = ["other"]
    rows = _operation(tmp_path, argv, output, "manual", received=(
        "Warning: truncated output\n" + output[:45] if case == "clipped" else True
    ))
    complete = case in ("matched", "inventory", "exact")
    for record in _import(tmp_path, rows, context_ids=context_ids):
        assert record["coverage"] == ("complete" if complete else "partial")
        assert record["counts"] == (record["observed"] if complete else None)
        assert record["unresolved_command_lines"] == ([] if complete else [3])
        assert record["observed"]["searches"] == len(context_ids)
        assert record["observed"]["used"] == 0
        if case == "matched":
            event, = record["events"]
            assert event["context_id"] == "capture" and record["observed"]["hits"] == 1
            assert all(
                item.get("delivery_state", "unknown") == item["use"] == "unknown"
                for item in record["materials"].values()
            )
