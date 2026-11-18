"""Import real CLI results from a bounded synthetic Codex rollout."""

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "src/inferrsi/knowledge/data/skill_library"
QUERY = "cache per-step masks ran out of device memory"
REF = "checkout:case.qwen-ascend-rejected-directions"
PASSAGE = "# Qwen Ascend: reported rejected directions"
DECISION = "I will check peak device memory before retaining per-step masks."


def _cli(cwd, *args):
    argv = [sys.executable, "-X", "utf8", "-m", "inferrsi", *args]
    return argv, _run(cwd, argv)


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


def _import(tmp_path, rows, *, decisions=()):
    trace, campaign = tmp_path / "rollout.jsonl", tmp_path / "campaign"
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
                     "--archive-review", str(review))
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


def test_unarchived_compatibility_query_prevents_false_complete_coverage(tmp_path):
    argv, output = _cli(tmp_path, "collect", "--relevance", QUERY, "--limit", "1", "--json")
    assert json.loads(output)["items"]
    for record in _import(tmp_path, _operation(tmp_path, argv, output, "collect")):
        assert record["coverage"] == "partial" and record["counts"] is None
        assert record["observed"]["searches"] == 1
        assert record["unresolved_command_lines"] == [3]
