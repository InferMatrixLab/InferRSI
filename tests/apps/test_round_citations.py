"""Round reasons prove use only through a delivered passage and authored choice."""

import json
import shlex
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from inferrsi.apps.cli import main
from inferrsi.apps.views.dashboard import dashboard_snapshot
from inferrsi.apps.workflows.campaign import create_campaign
from tests.apps.test_codex_knowledge_search import QUERY, REF, _cli, _import, _operation
from tests.apps.test_optimization_session import session as session
from tests.apps.test_optimization_session import task as task
from tests.apps.test_optimization_story import log_document
from tests.apps.test_project_optimization import project as project
from tests.apps.test_project_optimization import start
from tests.fixtures.knowledge_retrieval import install_legacy_capture

QUOTE = "NPU OOM."
REASON = f"Score each row immediately to avoid retaining all masks [use {REF} | {QUOTE}]."


def _historical_knowledge(root, command, query, *, limit=1, joint=False):
    """Render the old one-step tool return from its persisted capture format."""
    argv = [sys.executable, "-m", "inferrsi", *command, "knowledge", "--session", str(root),
            "--query", query, "--context-bytes", "8192", "--limit", str(limit)]
    number = len(list((root / "knowledge").glob("legacy-*.json"))) + 1
    sample = {QUERY: "managed-query", "zzunmatchedcaptureqv": "managed-empty"}[query]
    path, digest = install_legacy_capture(root, sample, f"legacy-{number}")
    ref = {"path": path.relative_to(root).as_posix(), "sha256": digest, "kind": "delivered_context"}
    output = {"reference": ref, "context": json.loads(path.read_bytes())}
    if joint:
        output["external"] = {"state": "not_enabled", "channel": "cannbot-knowledge",
                              "count": 0, "items": []}
    return argv, json.dumps(output, ensure_ascii=False, indent=2) + "\n"


def _async_round(cwd, command, output, *, pid="17", code=0):
    from tests.apps.test_codex_search_delivery import _call, _command, _exec_result

    call = _call(cwd, command, "round", emit="JSON.stringify(r)")
    started = _exec_result("round", "")
    block = started["payload"]["output"][1]
    data = json.loads(block["text"])
    del data["exit_code"]
    block["text"] = json.dumps({**data, "session_id": 17})
    finished = _command(cwd, command, output, "round", exit_code=code)
    finished["payload"]["item"].update(process_id=pid, status="failed" if code else "completed",
                                       source="unified_exec_startup")
    return [call, started, finished]


@pytest.mark.parametrize(("body", "include_ids"), [
    ("unopened", False), ("full", False), ("full", True), ("clipped", True),
])
def test_scoped_find_read_and_adoption_are_independent(
    project, tmp_path, capsys, body, include_ids,
):
    repo, _, _, root = project
    start(project, capsys)
    argv, found = _cli(tmp_path, "find", QUERY, "--kinds", "case", "--limit", "1",
                       "--session", str(root))
    search = json.loads(found)
    hit, = search["items"]
    assert hit["material_ref"] == REF
    ids = [Path(search["reference"]["path"]).stem]
    rows = _operation(tmp_path, argv, found, "find")
    cite = []
    if body != "unopened":
        argv, opened = _cli(tmp_path, *hit["read_args"])
        reference = json.loads(opened)["reference"]["path"]
        ids.append(Path(reference).stem)
        rows.extend(_operation(tmp_path, argv, opened, "read",
                               received=True if body == "full" else "Warning: truncated output\n"))
        cite = ["--knowledge-ref", f"{reference}#{REF}"]
    argv, outcome = _cli(tmp_path, "session", "round", "--session", str(root), "--candidate",
                         str(repo), "--hypothesis", REASON, *cite)
    rows.extend(_operation(tmp_path, argv, outcome, "round"))
    _, archive = _import(tmp_path, rows, context_ids=ids if include_ids else ())
    observed = archive["observed"]
    assert (observed["searches"], observed["hits"], observed["used"]) == (1, 1, int(body == "full"))
    find_event, = [event for event in archive["events"] if event["action"] == "search"]
    policy = {k: search["ranking_policy"][k] for k in ("id", "version", "config_sha256")}
    assert find_event["request"]["ranking_policy"] == policy
    assert find_event["request"]["kinds"] == "case"
    material = archive["materials"][REF]
    assert archive["coverage"] == ("partial" if body == "clipped" else "complete")
    if body == "full":
        read_event, = [event for event in archive["events"] if event["action"] == "read"]
        assert read_event["request"]["ranking_policy"] == policy
        assert read_event["request"]["search_ref"] == search["reference"]["path"]
        assert material["delivery_state"] == "visible"
        assert QUOTE in material["evidence"][0]["passage_text"]
    else:
        assert material["use"] == "unknown"


@pytest.mark.parametrize("include_ids", [False, True])
def test_cited_claims_share_a_json_line_with_source_urls(project, tmp_path, capsys, include_ids):
    repo, _, _, root = project
    start(project, capsys)
    ref = "package:triton.common.kernel.bandwidth_fusion_resource_limits"
    argv, found = _cli(tmp_path, "find", "bandwidth fusion resource limits softmax",
                       "--repo-type", "triton", "--session", str(root))
    result = json.loads(found)
    hit = next(item for item in result["items"] if item["material_ref"] == ref)
    rows = _operation(tmp_path, argv, found, "find")
    read_argv, opened = _cli(tmp_path, *hit["read_args"])
    read = json.loads(opened)
    body = read["content"]
    assert "\n" not in body and "https://" in body
    claims = json.loads(body)["claims"]
    full = claims[0]["description"]
    quotes = [full[:67], full]
    hypotheses = [f"Apply the cited guidance [use {ref} | {quote}]." for quote in quotes]
    rows.extend(_operation(tmp_path, read_argv, opened, "read"))
    args, outcome = _cli(tmp_path, "session", "round", "--session", str(root),
                         "--candidate", str(repo), "--hypothesis", "\n".join(hypotheses),
                         "--knowledge-ref", read["reference"]["path"])
    rows.extend(_operation(tmp_path, args, outcome, "round"))
    ids = [Path(row["reference"]["path"]).stem for row in (result, read)] if include_ids else []
    _, archive = _import(tmp_path, rows, context_ids=ids)
    assert archive["observed"]["used"] == 1 and archive["declarations"] == []
    evidence = archive["materials"][ref]["evidence"]
    assert len(evidence) == 2
    for item in evidence:
        assert item["passage_text"] in quotes and item["passage_truncated"]
        assert item["passage_path"] == "record.json" and item["passage_line"] == 1
        assert "https://" not in item["passage_text"]


def test_citation_cannot_extract_an_identifier_from_a_redacted_url_or_secret():
    from inferrsi.apps.views.capture_delivery import citation_excerpts

    text = "Use a stable reduction. See https://example.invalid/private-file and api_key=hidden."
    assert citation_excerpts(text, ["stable reduction", "private-file", "hidden"]) == [
        "stable reduction",
    ]
    from inferrsi.harness.records.evidence import sanitized_text

    text = json.dumps({"description": "Keep this excerpt.", "api_key": "fixture-opaque",
                       "credentials": {"value": "fixture-nested"}, "token_budget": 1234})
    assert citation_excerpts(text, ["Keep this excerpt.", "fixture-opaque", "fixture-nested"]) == [
        "Keep this excerpt.",
    ]
    public = json.loads(sanitized_text(text, "", limit=None))
    assert public == {"description": "Keep this excerpt.", "api_key": "[redacted]",
                      "credentials": "[redacted]", "token_budget": 1234}


def test_a_source_url_leaves_the_adjacent_json_summary_citable():
    from inferrsi.apps.views.capture_delivery import citation_excerpts
    from inferrsi.knowledge.knowledge_operations import KnowledgeReader

    bundle = KnowledgeReader().read("package:vllm.common.llm.bounded_serving_measurement")
    text = bundle.content["record.json"].decode("utf-8")
    summary = json.loads(text)["summary"]
    assert citation_excerpts(text, [summary]) == [summary]
    text = ('{"source":"https://example.invalid/private-file",'
            '"description":"Use a stable reduction."}')
    assert citation_excerpts(text, ["private-file", "Use a stable reduction."]) == [
        "Use a stable reduction.",
    ]


def test_round_receipt_confirms_the_original_submission_position(project, tmp_path, capsys):
    from inferrsi.apps.views.search_attribution import import_search
    from tests.apps.test_codex_knowledge_search import LIBRARY
    from tests.apps.test_codex_search_delivery import _meta, _rollout
    from tests.apps.test_search_capture_delivery import _review

    repo, _, _, root = project
    start(project, capsys)
    _, found = _cli(tmp_path, "find", QUERY, "--kinds", "case", "--limit", "1",
                    "--session", str(root))
    read_argv, opened = _cli(tmp_path, *json.loads(found)["items"][0]["read_args"])
    read = _operation(tmp_path, read_argv, opened, "read")
    source = json.loads(opened)["reference"]["path"]
    argv, outcome = _cli(tmp_path, "session", "round", "--session", str(root),
                         "--candidate", str(repo), "--hypothesis", REASON,
                         "--knowledge-ref", f"{source}#{REF}")
    status_argv, receipt = _cli(tmp_path, "session", "status", "--session", str(root),
                                "--round-receipt", "1")
    status = _operation(tmp_path, status_argv, receipt, "status")
    clipped = outcome[:65] + "\n... command output truncated for persistence ...\n" + outcome[-65:]

    def submit(command, pid="17"):
        return _async_round(tmp_path, command, clipped, pid=pid)

    trace = tmp_path / "round.jsonl"
    review = _review(tmp_path / "review.json")

    def archive(rows):
        _rollout(trace, _meta(tmp_path), *rows)
        result = import_search(root, number=1, trace=trace, lines=(2, len(rows) + 1),
                               knowledge_root=LIBRARY, archive_review=review, complete=True)
        record = json.loads(result.read_bytes())
        # Each variant represents an independent trace for this test campaign.
        result.unlink()
        (root / "search/round-1.json").unlink()
        return record

    command = shlex.join(argv)
    submitted = submit(command)
    confirmed = archive([*read, *submitted, *status])
    assert confirmed["observed"]["used"] == 1
    evidence, = confirmed["materials"][REF]["evidence"]
    assert evidence["decision_line"] == 5 and evidence["event_id"] == "file-3"
    assert evidence["decision_quote"] == REASON and QUOTE in evidence["passage_text"]

    # The host may emit a cleanup's plain output and the round's launch object
    # in one code-mode call. The exact native process ID must still bind it.
    from tests.apps.test_codex_search_delivery import _command

    batched = deepcopy(submitted)
    options = json.dumps({"cmd": command, "workdir": str(tmp_path)})
    cleanup_options = json.dumps({"cmd": "true", "workdir": str(tmp_path)})
    batched[0]["payload"]["input"] = (
        f'text((await tools.exec_command({cleanup_options})).output);\n'
        f'text((await tools.exec_command({options})));'
    )
    batched[1]["payload"]["output"].insert(1, {"type": "input_text", "text": ""})
    cleanup = _command(tmp_path, "true", "", "cleanup")
    batch_rows = [batched[0], cleanup, *batched[1:]]
    confirmed = archive([*read, *batch_rows, *status])
    evidence, = confirmed["materials"][REF]["evidence"]
    assert confirmed["observed"]["used"] == 1 and evidence["decision_line"] == 5
    wrong_process = deepcopy(batch_rows)
    wrong_process[-1]["payload"]["item"]["process_id"] = "18"
    duplicate_launch = deepcopy(batch_rows)
    blocks = duplicate_launch[2]["payload"]["output"]
    blocks.append(dict(blocks[-1]))
    dynamic_command = deepcopy(batch_rows)
    dynamic_command[0]["payload"]["input"] = batched[0]["payload"]["input"].replace(
        json.dumps(command), "command"
    )
    for invalid in (wrong_process, duplicate_launch, dynamic_command):
        assert archive([*read, *invalid, *status])["observed"]["used"] == 0

    full = json.loads(outcome)
    summary = {"completed_rounds": 1, "session": full["session"]}
    for shown, expected in ((summary, 1), ({**summary, "session": "another"}, 0),
                            ({**summary, "invented": None}, 0)):
        returned = _operation(tmp_path, argv, outcome, "round", received=json.dumps(shown))
        assert archive([*read, *returned])["observed"]["used"] == expected

    changed = json.loads(receipt)
    changed["latest_observation"]["observation_sha256"] = "0" * 64
    altered = _operation(tmp_path, status_argv, json.dumps(changed), "wrong-digest")
    early = [*submitted[:2], *status, submitted[2]]
    wrong_ref = submit(shlex.join([*argv[:-1], source + "#wrong"]))
    wrong_round = _operation(tmp_path, [*status_argv[:-1], "2"], receipt, "wrong-round")
    duplicate = deepcopy(submitted)
    duplicate[0]["payload"]["call_id"] = duplicate[1]["payload"]["call_id"] = "second"
    duplicate[2]["payload"]["item"]["id"] = "second"
    for rows in (
        [*read, *submitted], [*read, *status], [*submitted, *read, *status],
        [*read, *early], [*read, *submitted, *altered],
        [*read, *submitted, *status[:-1]],
        [*read, *submitted, *_operation(tmp_path, status_argv, receipt, "short-status",
                                        received="Warning: truncated output\n")],
        [*read, *submitted, *wrong_round],
        [*read, *submit(command, pid="18"), *status],
        [*read, submitted[0], submitted[2], *status],
        [*read, *wrong_ref, *status], [*read, *submit(command + "; printf extra"), *status],
        [*read, *submitted, *duplicate, *status],
    ):
        assert archive(rows)["observed"]["used"] == 0

    # Once two verified rounds share all these authored fields, a later
    # receipt for round 1 cannot disambiguate this clipped submission.
    _cli(tmp_path, *argv[argv.index("session"):])
    assert archive([*read, *submitted, *status])["observed"]["used"] == 0


def test_blocked_round_receipt_verifies_the_failed_candidate_reason(project, tmp_path, capsys):
    from inferrsi.apps.views.round_citations import retained_round_citations
    from tests.apps.test_codex_search_delivery import _meta, _rollout

    repo, protocol, _, root = project
    (protocol / "quality.py").write_text("raise SystemExit(2)\n", encoding="utf-8")
    start(project, capsys)
    _, found = _cli(tmp_path, "find", QUERY, "--kinds", "case", "--limit", "1",
                    "--session", str(root))
    read_argv, opened = _cli(tmp_path, *json.loads(found)["items"][0]["read_args"])
    read = _operation(tmp_path, read_argv, opened, "read")
    source = json.loads(opened)["reference"]["path"]
    args = ["session", "round", "--session", str(root), "--candidate", str(repo),
            "--hypothesis", REASON, "--knowledge-ref", source]
    assert main(args) == 2
    result = capsys.readouterr().out
    outcome = json.loads(result)
    assert outcome["state"] == "blocked" and outcome["best"]["kind"] == "baseline"
    observed = outcome["latest_observation"]
    assert observed["assessment"]["status"] == "infrastructure_failure"
    observation = root / observed["path"] / "observation.json"
    frozen = observation.read_bytes()

    cmd = shlex.join(["env", "-u", "DEVICE", "OMP_NUM_THREADS=1", sys.executable,
                      "-m", "inferrsi", *args])
    status_args, receipt = _cli(tmp_path, "session", "status", "--session", str(root),
                                "--round-receipt", "1")
    status = _operation(tmp_path, status_args, receipt, "status")
    submitted = _async_round(tmp_path, cmd, result, code=2)
    _, archive = _import(tmp_path, [*read, *submitted, *status], context_ids=[Path(source).stem])
    assert archive["observed"]["used"] == 1
    evidence, = archive["materials"][REF]["evidence"]
    assert evidence["decision_line"] == 5 and evidence["decision_quote"] == REASON
    assert QUOTE in evidence["passage_text"] and observation.read_bytes() == frozen

    campaign = json.loads((root / "campaign.json").read_bytes())
    trace = tmp_path / "submission.jsonl"
    altered = deepcopy(outcome)
    altered["latest_observation"]["observation_sha256"] = "0" * 64
    wrong_candidate = deepcopy(outcome)
    wrong_candidate["latest_observation"]["candidate_sha256"] = "0" * 64
    for rows in (
        submitted, status,
        [*_async_round(tmp_path, cmd, "Invalid argument\n", code=2), *status],
        [*_async_round(tmp_path, cmd, json.dumps(altered), code=2), *status],
        [*_async_round(tmp_path, cmd, json.dumps(wrong_candidate), code=2), *status],
        [*_async_round(tmp_path, cmd, result, code=1), *status],
        [*_async_round(tmp_path, cmd, result, pid="18", code=2), *status],
    ):
        _rollout(trace, _meta(tmp_path), *rows)
        _, position = retained_round_citations(root, campaign, 1, trace, (2, len(rows) + 1))
        assert position is None


@pytest.mark.parametrize("include_id", [False, True])
def test_selecting_a_scoped_find_receipt_keeps_visible_external_hits(
    project, tmp_path, capsys, monkeypatch, include_id,
):
    from inferrsi.apps.workflows import session_knowledge

    root = project[-1]
    start(project, capsys, extra=("--cannbot-platform", "a3"))
    remote = {"state": "ok", "revision": "a" * 40, "count": 1,
              "items": [{"locator": "ops/card", "card_sha256": "b" * 64, "score": 1.0}]}
    monkeypatch.setattr(session_knowledge, "round_provider",
                        lambda plan: SimpleNamespace(search=lambda *a, **kw: remote))
    args = ["find", "zzexternalarchiveonlyqv", "--session", str(root)]
    assert main(args) == 0
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result["items"] == [] and result["external"]["count"] == 1
    ids = [Path(result["reference"]["path"]).stem] if include_id else []
    rows = _operation(tmp_path, [sys.executable, "-m", "inferrsi", *args], output, "find")
    for record in _import(tmp_path, rows, context_ids=ids):
        assert record["coverage"] == "complete"
        assert record["observed"] == {"searches": 1, "hits": 1, "unique_hits": 1, "used": 0}
        assert set(record["materials"]) == {"cannbot-knowledge:ops/card"}


@pytest.mark.parametrize("case", [
    "read", "managed_context", "late_body", "clipped", "wrong_quote",
    "long_line", "grouped_context", "joint_context", "joint_context_clipped",
])
def test_managed_round_resolves_citations_from_original_tool_outputs(
    project, tmp_path, capsys, case,
):
    repo, _, _, root = project
    joint = case.startswith("joint_context")
    start(project, capsys, extra=("--cannbot-platform", "a3") if joint else ())
    context_ids = []
    ref, quote, reason = REF, QUOTE, REASON
    if joint or case in ("managed_context", "grouped_context"):
        read_argv, read_output = _historical_knowledge(root, ["campaign"], QUERY, joint=joint)
        answer = json.loads(read_output)
        context_ids = [answer["context"]["context_id"]]
        if joint:
            assert answer["external"]["state"] == "not_enabled"
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
    received = True
    if case == "clipped":
        received = "Warning: truncated output\n"
    elif case == "joint_context_clipped":
        received = read_output.split('\n  "external":', 1)[0] + '\n  "external": {\n'
    read = _operation(tmp_path, read_argv, read_output, "read", received=received)
    if case == "grouped_context":
        _, second = _historical_knowledge(root, ["campaign"], "zzunmatchedcaptureqv")
        context_ids.append(json.loads(second)["context"]["context_id"])
        read[-1]["payload"]["output"] += "\n" + second

    if case == "wrong_quote":
        reason = reason.replace(quote, "Unrecorded phrase.")
    args = ["session", "round", "--directory", str(root), "--candidate", str(repo),
            "--hypothesis", reason]
    assert main(args) == 0
    receipt = capsys.readouterr().out
    # The host can summarize the round response. The read must remain exact.
    round_op = _operation(tmp_path, [sys.executable, "-m", "inferrsi", *args],
                          receipt, "round", received='{"completed_rounds": 1}\n')
    rows = ([round_op[0], *read, *round_op[1:]] if case == "late_body"
            else [*read, *round_op])
    _, archive = _import(tmp_path, rows, context_ids=context_ids)
    coverage = ("partial" if case in ("clipped", "grouped_context", "joint_context_clipped")
                else "complete")
    assert archive["coverage"] == coverage
    matched = case in ("read", "managed_context", "long_line", "joint_context")
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
    log_argv, receipt = _cli(tmp_path, "evidence", "log", "--directory", str(root),
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
    _cli(tmp_path, "evidence", "log", "--directory", str(root), "--file", str(source))
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
        command = ["session"]
    else:
        root = request.getfixturevalue("session")
        command = ["benchmarks", "session"]

    ids = []
    if case == "no_query":
        argv, output = _cli(tmp_path, *command, "status", "--session", str(root))
    else:
        argv, output = _historical_knowledge(root, command, QUERY)
        if case != "omitted":
            ids.append(json.loads(output)["context"]["context_id"])
    rows = _operation(tmp_path, argv, output, "first", received=(
        "Warning: truncated output\n" + output[:250] if case == "unverified" else True
    ))
    if case == "second_omitted":
        argv, output = _historical_knowledge(root, command, "zzunmatchedcaptureqv")
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
