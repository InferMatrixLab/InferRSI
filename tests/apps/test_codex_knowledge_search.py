"""Import real CLI results from a bounded synthetic Codex rollout."""

import gzip
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

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


def _import(tmp_path, rows, *, decisions=(), context_ids=(), campaign=None):
    trace = tmp_path / "rollout.jsonl"
    campaign = campaign or tmp_path / "campaign"
    meta = {"type": "session_meta", "payload": {"id": "synthetic-cli", "cwd": str(tmp_path)}}
    trace.write_text("".join(json.dumps(row) + "\n" for row in [meta, *rows]), encoding="utf-8")
    review = tmp_path / "review.json"
    review.write_text(json.dumps({
        "task": "Review a retained CLI search", "decisions": list(decisions),
        "corpus": {"repository": "InferMatrixLab/InferRSI", "revision": "a" * 40,
                   "root": "src/inferrsi/knowledge/data/skill_library"},
    }), encoding="utf-8")
    if not campaign.exists():
        _cli(tmp_path, "campaign", "init", "--directory", str(campaign), "--id", "example")
    _, output = _cli(tmp_path, "campaign", "import-search", "--directory", str(campaign),
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


@pytest.mark.parametrize("case", [
    "omitted", "matched", "wrong_id", "clipped", "inventory", "exact",
])
def test_manual_capture_search_coverage_requires_the_matching_receipt(tmp_path, case):
    campaign = tmp_path / "campaign"
    _cli(tmp_path, "campaign", "init", "--directory", str(campaign), "--id", "capture-test")
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
