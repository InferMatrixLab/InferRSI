"""Round reasons prove use only through a delivered passage and authored choice."""

import json
import sys

import pytest
from test_codex_knowledge_search import QUERY, REF, _cli, _import, _operation
from test_optimization_session import session as session
from test_optimization_session import task as task
from test_optimization_story import log_document
from test_project_optimization import project as project
from test_project_optimization import start

from inferrsi.apps.campaign import create_campaign
from inferrsi.apps.cli import main
from inferrsi.apps.views.dashboard import dashboard_snapshot

QUOTE = "NPU OOM."
REASON = f"Score each row immediately to avoid retaining all masks [use {REF} | {QUOTE}]."


@pytest.mark.parametrize("case", [
    "read", "managed_context", "late_body", "clipped", "wrong_quote",
    "long_line", "grouped_context",
])
def test_managed_round_resolves_citations_from_original_tool_outputs(
    project, tmp_path, capsys, case,
):
    repo, _, _, root = project
    start(project, capsys)
    context_ids = []
    ref, quote, reason = REF, QUOTE, REASON
    if case in ("managed_context", "grouped_context"):
        read_args = ["campaign", "knowledge", "--directory", str(root), "--query", QUERY,
                     "--context-bytes", "8192", "--limit", "1"]
        read_argv, read_output = _cli(tmp_path, *read_args)
        context_ids = [json.loads(read_output)["context"]["context_id"]]
    elif case == "long_line":
        ref = "package:inferrsi.ascend.skills.ascend_aclgraph_capture_replay"
        quote = (
            "For performance claims, require host/device timing "
            "rather than a launch-overhead guess."
        )
        reason = f"Use host/device timing for the next measurement [use {ref} | {quote}]."
        path = "data/skill_library/systems/platforms/ascend/ascend-aclgraph-capture-replay/SKILL.md"
        read_argv, read_output = _cli(tmp_path, "read", ref, "--resource", path,
                                     "--omit-resources")
    else:
        read_argv, read_output = _cli(tmp_path, "read", REF, "--material", "--omit-resources",
                                     "--installed-library")
    read = _operation(tmp_path, read_argv, read_output, "read",
                      received="Warning: truncated output\n" if case == "clipped" else True)
    if case == "grouped_context":
        _, second = _cli(tmp_path, "campaign", "knowledge", "--directory", str(root),
                         "--query", "zzunmatchedcaptureqv", "--context-bytes", "8192")
        context_ids.append(json.loads(second)["context"]["context_id"])
        read[-1]["payload"]["output"] += "\n" + second

    if case == "wrong_quote":
        reason = reason.replace(quote, "Unrecorded phrase.")
    args = ["campaign", "round", "--directory", str(root), "--candidate", str(repo),
            "--hypothesis", reason]
    assert main(args) == 0
    receipt = capsys.readouterr().out
    # The host can summarize the round response. The read must remain exact.
    round_op = _operation(tmp_path, [sys.executable, "-m", "inferrsi", *args],
                          receipt, "round", received='{"completed_rounds": 1}\n')
    rows = ([round_op[0], *read, *round_op[1:]] if case == "late_body"
            else [*read, *round_op])
    _, archive = _import(tmp_path, rows, context_ids=context_ids)
    coverage = "partial" if case in ("clipped", "grouped_context") else "complete"
    assert archive["coverage"] == coverage
    matched = case in ("read", "managed_context", "long_line")
    assert archive["observed"]["used"] == int(matched)
    assert archive["observed"]["searches"] == len(context_ids)
    [projected] = [record for record in dashboard_snapshot(root)["data"]["knowledge_trace"][
        "searches"] if record["schema_version"] == 2]
    if matched:
        [evidence] = archive["materials"][ref]["evidence"]
        assert evidence["decision_quote"] == reason
        assert quote in evidence["passage_text"]
        if case == "long_line":
            assert evidence["passage_truncated"]
        [material] = [row for row in projected["materials"] if row["ref"] == ref]
        assert material["evidence"][0]["state"] == "archive_reviewed"
    else:
        assert archive["materials"][REF]["use"] == "unknown"
        assert projected["declarations"][0]["state"] == "caller_declaration"
        assert projected["declarations"][0]["reason"] == "read_excerpt_unverified"


@pytest.mark.parametrize("order", ["after_read", "before_read", "repeated", "after_log"])
def test_manual_reason_requires_authored_message_and_keeps_original_log_version(tmp_path, order):
    root = tmp_path / "campaign"
    create_campaign(root, "camp")
    argv, body = _cli(tmp_path, "read", REF, "--material", "--omit-resources",
                      "--installed-library")
    read = _operation(tmp_path, argv, body, "read")
    reason_message = {"type": "response_item", "payload": {
        "type": "message", "role": "assistant", "phase": "commentary",
        "content": [{"type": "output_text", "text": REASON}],
    }}
    log = log_document("0" * 64)
    log["iterations"][0]["rationale"] = REASON
    source = tmp_path / "log.json"
    source.write_text(json.dumps(log), encoding="utf-8")
    log_argv, receipt = _cli(tmp_path, "campaign", "log", "--directory", str(root),
                            "--file", str(source))
    log_op = _operation(tmp_path, log_argv, receipt, "log")
    rows = {
        "after_read": [*read, reason_message, *log_op],
        "before_read": [reason_message, *read, *log_op],
        "repeated": [reason_message, *read, reason_message, *log_op],
        "after_log": [reason_message, *read, *log_op, reason_message],
    }[order]
    _, before = _import(tmp_path, rows)
    adopted = order in ("after_read", "repeated")
    assert before["counts"]["used"] == int(adopted)
    if adopted:
        evidence, = before["materials"][REF]["evidence"]
        assert evidence["decision_line"] == len(read) + 2 + int(order == "repeated")
    log["iterations"][1]["rationale"] = "Later round records a different decision."
    source.write_text(json.dumps(log), encoding="utf-8")
    _cli(tmp_path, "campaign", "log", "--directory", str(root), "--file", str(source))
    _, after = _import(tmp_path, rows)
    assert after == before


@pytest.mark.parametrize(("flow", "case"), [
    ("campaign", "no_query"),
    ("campaign", "omitted"),
    ("benchmarks", "omitted"),
    ("campaign", "unverified"),
    ("campaign", "uncited"),
    ("benchmarks", "uncited"),
    ("campaign", "second_omitted"),
])
def test_managed_search_coverage_and_delivery_without_a_citation(
    tmp_path, request, capsys, flow, case,
):
    if flow == "campaign":
        setup = request.getfixturevalue("project")
        start(setup, capsys)
        root = setup[-1]
        command = ["campaign"]
    else:
        root = request.getfixturevalue("session")
        command = ["benchmarks", "session"]

    ids = []
    if case == "no_query":
        argv, output = _cli(tmp_path, *command, "status", "--session", str(root))
    else:
        argv, output = _cli(tmp_path, *command, "knowledge", "--session", str(root),
                            "--query", QUERY, "--context-bytes", "8192", "--limit", "1")
        if case != "omitted":
            ids.append(json.loads(output)["context"]["context_id"])
    rows = _operation(tmp_path, argv, output, "first", received=(
        "Warning: truncated output\n" + output[:250] if case == "unverified" else True
    ))
    if case == "second_omitted":
        argv, output = _cli(tmp_path, *command, "knowledge", "--session", str(root),
                            "--query", "zzunmatchedcaptureqv", "--context-bytes", "8192")
        rows.extend(_operation(tmp_path, argv, output, "second"))
    verified = case in ("uncited", "second_omitted")
    complete = case in ("no_query", "uncited")
    for record in _import(tmp_path, rows, context_ids=ids, campaign=root):
        assert record["coverage"] == ("complete" if complete else "partial")
        assert record["counts"] == (record["observed"] if complete else None)
        assert record["observed"]["searches"] == len(ids)
        assert record["observed"]["used"] == 0
        assert record["unresolved_command_lines"] == (
            [] if complete else [6] if case == "second_omitted" else [3]
        )
        if ids:
            material = record["materials"][REF]
            assert material.get("delivery_state", "unknown") == (
                "visible" if verified else "unknown"
            )
            assert material["use"] == "unknown"
