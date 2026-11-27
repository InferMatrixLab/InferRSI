"""Model-visible file delivery must be traceable to exact tool output."""

import json
import shlex
from pathlib import Path, PureWindowsPath

import pytest

from inferrsi.apps.views.codex_search import read_window


def _meta(cwd):
    return {"type": "session_meta",
            "payload": {"id": "synthetic-session", "cwd": str(cwd)}}


def _call(cwd, command, call_id, *, emit="r.output"):
    source = (
        "const r = await tools.exec_command({\n"
        f"  cmd: {json.dumps(command)},\n"
        f"  workdir: {json.dumps(str(cwd))}\n"
        f"}});\ntext({emit});"
    )
    return {"type": "response_item",
            "payload": {"type": "custom_tool_call", "name": "exec",
                        "call_id": call_id, "input": source}}


def _command(cwd, command, output, event_id, exit_code=0):
    return {
        "type": "event_msg",
        "payload": {
            "type": "item_completed",
            "item": {
                "type": "CommandExecution", "id": event_id,
                "cwd": cwd.as_uri(), "command": ["/bin/zsh", "-lc", command],
                "exit_code": exit_code, "aggregated_output": output,
            },
        },
    }


def _result(call_id, output):
    return {
        "type": "response_item",
        "payload": {
            "type": "custom_tool_call_output", "call_id": call_id,
            "output": [{"type": "input_text",
                        "text": f"Script completed\nWall time in 0.1 seconds\nOutput:\n{output}"}],
        },
    }


def _exec_result(call_id, output, *, exit_code=0):
    result = {"chunk_id": "abcd12", "wall_time_seconds": 0.1, "exit_code": exit_code,
              "original_token_count": 100, "output": output}
    return {"type": "response_item", "payload": {
        "type": "custom_tool_call_output", "call_id": call_id, "output": [
            {"type": "input_text", "text": "Script completed\nWall time 0.3 seconds\nOutput:\n"},
            {"type": "input_text", "text": json.dumps(result, ensure_ascii=False)},
        ],
    }}


def _message(text):
    return {"type": "response_item",
            "payload": {"type": "message", "role": "assistant",
                        "phase": "final_answer",
                        "content": [{"type": "output_text", "text": text}]}}


def _rollout(path, *rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


@pytest.mark.parametrize(("cmd_key", "workdir_key"), [
    ("cmd", '"workdir"'), ('"cmd"', "'workdir'"), ("'cmd'", "workdir"),
])
def test_quoted_js_properties_keep_the_actual_command_workdir(tmp_path, cmd_key, workdir_key):
    corpus = tmp_path / "knowledge"
    corpus.mkdir()
    call = _call(corpus, "cat note.md", "read")
    source = call["payload"]["input"].replace("cmd:", cmd_key + ":")
    call["payload"]["input"] = source.replace("workdir:", workdir_key + ":")
    trace = tmp_path / "trace.jsonl"
    _rollout(trace, _meta(tmp_path), call, _command(corpus, "cat note.md", "body\n", "event"),
             _result("read", "body\n"))
    _, events, _, uncertain, details = read_window(trace, (2, 4), corpus, archive=True)
    assert events[0]["delivery"]["state"] == "visible"
    assert not uncertain and not details


@pytest.mark.parametrize("issue", ["dynamic", "duplicate", "wrong"])
def test_a_quoted_workdir_must_be_one_matching_literal(tmp_path, issue):
    call = _call(tmp_path, "cat note.md", "read")
    source = call["payload"]["input"].replace("workdir:", '"workdir":')
    literal = json.dumps(str(tmp_path))
    if issue == "dynamic":
        source = source.replace('"workdir": ' + literal, '"workdir": location')
    elif issue == "duplicate":
        source = source.replace('"workdir": ' + literal,
                                '"workdir": ' + literal + ', "workdir": ' + literal)
    else:
        source = source.replace('"workdir": ' + literal,
                                '"workdir": ' + json.dumps(str(tmp_path / "elsewhere")))
    call["payload"]["input"] = source
    trace = tmp_path / "trace.jsonl"
    _rollout(trace, _meta(tmp_path), call, _command(tmp_path, "cat note.md", "body\n", "event"),
             _result("read", "body\n"))
    _, events, _, uncertain, _ = read_window(trace, (2, 4), tmp_path, archive=True)
    assert events[0]["delivery"]["state"] == "unknown" and uncertain == [3]


@pytest.mark.parametrize(("literal", "visible"), [
    ("""'cat "example.md"'""", True), ('`cat "example.md"`', True),
    ('`cat "${file}"`', False), ("""'cat ' + '"example.md"'""", False),
])
def test_single_quoted_and_static_template_command_receives_stdout(tmp_path, literal, visible):
    trace = tmp_path / "trace.jsonl"
    command = 'cat "example.md"'
    call = _call(tmp_path, command, "read")
    call["payload"]["input"] = call["payload"]["input"].replace(json.dumps(command), literal)
    _rollout(trace, _meta(tmp_path), call, _command(tmp_path, command, "observed\n", "event"),
             _result("read", "observed\n"))
    _, events, _, uncertain, _ = read_window(trace, (2, 4), tmp_path, archive=True)
    assert (events[0]["delivery"]["state"] == "visible") is visible
    assert uncertain == ([] if visible else [3])


@pytest.mark.parametrize("issue", [
    None, "truncated", "exit_code", "running", "multi_result", "multi_call", "summary",
])
def test_single_serialized_exec_result_for_material_read(tmp_path, issue):
    trace = tmp_path / "rollout.jsonl"
    ref, revision = "package:example", "sha256:" + "a" * 64
    cmd = f"inferrsi read {ref} --revision {revision} --material --omit-resources"
    body = 'Check the "baseline" first.\n保留精度对照。\n'
    output = json.dumps({"ref": ref, "id": "example", "revision": revision,
                         "entrypoint": "SKILL.md", "content": body}, ensure_ascii=False) + "\n"
    call = _call(tmp_path, cmd, "read", emit="JSON.stringify(r)")
    result = _exec_result("read", output)
    blocks = result["payload"]["output"]
    if issue == "truncated":
        result = _exec_result("read", "Warning: truncated output\n" + output[:80])
    elif issue == "exit_code":
        result = _exec_result("read", output, exit_code=1)
    elif issue == "running":
        running = json.loads(blocks[1]["text"])
        del running["exit_code"]
        blocks[1]["text"] = json.dumps({**running, "session_id": 123})
    elif issue == "multi_result":
        blocks.append(dict(blocks[1]))
    elif issue == "multi_call":
        source = call["payload"]["input"]
        call["payload"]["input"] = source.replace(
            "text(JSON.stringify(r))", "await tools.exec_command(next); text(JSON.stringify(r))"
        )
    elif issue == "summary":
        blocks[1]["text"] = json.dumps({"output": output, "exit_code": 0})
    _rollout(
        trace, _meta(tmp_path), call, _command(tmp_path, cmd, output, "read-event"), result,
    )
    _, events, _, uncertain, details = read_window(trace, (2, 4), tmp_path, archive=True)
    delivery = events[0]["delivery"]
    if issue is None:
        assert delivery["state"] == "visible" and delivery["return_line"] == 4
        assert delivery["visible_resources"] == [{"ref": ref, "path": "SKILL.md"}]
        assert [p["text"] for p in delivery["passages"]] == body.splitlines()
        assert not uncertain and not details
    else:
        assert delivery["state"] == "unknown" and not delivery["passages"]
        assert not delivery.get("visible_resources") and uncertain == [3]


@pytest.mark.parametrize("explicit_returns", [False, True])
def test_selected_captures_use_verified_serialized_cli_returns(tmp_path, explicit_returns):
    from inferrsi.apps.views.search_attribution import import_search
    from inferrsi.apps.workflows.campaign import create_campaign
    from tests.apps.test_codex_knowledge_search import LIBRARY, QUERY, _cli
    from tests.apps.test_search_capture_delivery import _review

    root, trace = tmp_path / "campaign", tmp_path / "trace.jsonl"
    create_campaign(root, "example")
    argv, found = _cli(tmp_path, "find", QUERY, "--session", str(root),
                       "--limit", "1", "--no-external")
    result = json.loads(found)
    find_id = Path(result["reference"]["path"]).stem
    read_argv, opened = _cli(tmp_path, *result["items"][0]["read_args"])
    view = json.loads(opened)
    read_id = Path(view["reference"]["path"]).stem
    compound = shlex.join(argv) + "; printf done"
    read = shlex.join(read_argv)
    _rollout(
        trace, _meta(tmp_path),
        _call(tmp_path, compound, "find", emit="JSON.stringify(r)"),
        _command(tmp_path, compound, found + "done", "compound"),
        _exec_result("find", found + "done"),
        _call(tmp_path, read, "read", emit="JSON.stringify(r)"),
        _command(tmp_path, read, opened, "read-event"), _exec_result("read", opened),
    )
    review = _review(tmp_path / "review.json",
                     capture_returns={find_id: 4, read_id: 7} if explicit_returns else {})
    archive = import_search(root, number=1, trace=trace, lines=(2, 7), knowledge_root=LIBRARY,
                            context_ids=[find_id, read_id], archive_review=review, complete=True)
    for path in (root / "search/round-1.json", archive):
        record = json.loads(path.read_bytes())
        assert record["coverage"] == "partial" and record["unresolved_command_lines"] == [3]
        assert record["observed"]["used"] == 0
        search, read = record["events"]
        assert search["context_id"] == find_id and search["delivery"]["return_line"] == 4
        assert read["context_id"] == read_id and read["delivery"]["return_line"] == 7
        assert read["delivery"]["visible_resources"] == [
            {"ref": view["ref"], "path": view["content_resource"]},
        ]


def test_archive_keeps_multiple_exact_matches_and_legacy_materials(tmp_path):
    corpus = tmp_path / "knowledge"
    corpus.mkdir()
    trace = tmp_path / "rollout.jsonl"
    command = "rg -n needle ."
    output = "a.md:2:first needle\na.md:8:second needle\nb.md:4:third needle\n"
    _rollout(
        trace, _meta(corpus), _call(corpus, command, "call-search"),
        _command(corpus, command, output, "exec-private-id"),
        _result("call-search", output), _message("Use the second match in a.md."),
    )

    window, events, decisions, uncertain, details = read_window(
        trace, (2, 5), corpus, archive=True,
    )
    event = events[0]
    assert window["archive"] is True
    assert event["id"] == event["event_id"] == "file-3"
    assert event["materials"] == [
        {"ref": "a.md", "match_line": 2}, {"ref": "b.md", "match_line": 4},
    ]
    assert event["delivery"]["state"] == "visible"
    assert event["delivery"]["return_line"] == 4
    assert event["delivery"]["runtime_truncated"] is False
    assert [(item["ref"], item["line"], item["text"])
            for item in event["delivery"]["passages"]] == [
                ("a.md", 2, "first needle"),
                ("a.md", 8, "second needle"),
                ("b.md", 4, "third needle"),
            ]
    assert decisions == {5: "Use the second match in a.md."}
    assert event["delivery"]["return_line"] < next(iter(decisions))
    assert uncertain == [] and details == []

    _, legacy_events, legacy_decisions, legacy_uncertain, legacy_details = read_window(
        trace, (2, 5), corpus,
    )
    assert legacy_events[0]["materials"] == event["materials"]
    assert "delivery" not in legacy_events[0] and legacy_events[0]["event_id"] == "exec-private-id"
    assert legacy_decisions == decisions
    assert legacy_uncertain == [] and legacy_details == []


@pytest.mark.parametrize(("command", "output", "ref"), [
    ("rg -n needle .", "./42:1:needle\n", "42"),
    ("rg -n needle", "42:1:needle\n", "42"),
    ("rg -n needle cases/", "cases/42:1:needle\n", "cases/42"),
    ("rg -n needle 42 other.md", "42:1:needle\n", "42"),
])
def test_rg_known_directory_or_multiple_operands_have_filename_prefixes(
    tmp_path, command, output, ref,
):
    corpus, trace = tmp_path / "knowledge", tmp_path / "rollout.jsonl"
    _rollout(trace, _meta(corpus), _call(corpus, command, "call-search"),
             _command(corpus, command, output, "search"), _result("call-search", output))
    _, events, _, uncertain, _ = read_window(trace, (2, 4), corpus, archive=True)
    assert not uncertain
    assert events[0]["delivery"]["passages"] == [{"ref": ref, "line": 1, "text": "needle"}]


@pytest.mark.parametrize("separator", ["/", "\\"])
@pytest.mark.parametrize("mode", ["numbered_text", "numbered_context", "text"])
def test_rg_drive_qualified_output(monkeypatch, separator, mode):
    from inferrsi.apps.views import codex_search

    # Exercise Windows path semantics on every host, without requiring a Windows drive.
    monkeypatch.setattr(codex_search, "Path", PureWindowsPath)
    corpus = PureWindowsPath("F:/corpus")
    name = separator.join(["F:", "corpus", "case.md"])
    output = f"{name}:2:needle\n" if mode != "text" else f"{name}:needle\n"
    if mode == "numbered_context":
        output = f"{name}-1-before\n" + output
    rows, complete = codex_search._rg_observations(output, corpus, corpus, [name], mode, True)
    assert complete
    assert rows == [{"ref": "case.md", "line": None if mode == "text" else 2,
                     "text": "needle", "output_line": 1 if mode == "numbered_context" else 0}]


@pytest.mark.parametrize(("root", "output", "expected"), [
    ("C:/tmp/corpus", "F:/manual:needle\n",
     [{"ref": "F", "line": None, "text": "/manual:needle", "output_line": 0}]),
    ("F:/corpus", "F:/manual:needle\n",
     [{"ref": "F", "line": None, "text": "/manual:needle", "output_line": 0}]),
    ("F:/corpus", "F:/corpus/F/manual:needle\n", []),
])
def test_windows_unnumbered_drive_or_single_letter_filename(monkeypatch, root, output, expected):
    from inferrsi.apps.views import codex_search

    monkeypatch.setattr(codex_search, "Path", PureWindowsPath)
    corpus = PureWindowsPath(root)
    rows, complete = codex_search._rg_observations(output, corpus, corpus, ["F"], "text", True)
    assert rows == expected
    assert complete is bool(expected)


def test_sed_late_selected_line_survives_bounded_default_excerpt(tmp_path):
    corpus = tmp_path / "knowledge"
    corpus.mkdir()
    trace = tmp_path / "rollout.jsonl"
    command = "sed -n '1,15p' case.md"
    output = "".join(f"content line {line}\n" for line in range(1, 16))
    _rollout(trace, _meta(corpus), _call(corpus, command, "call-read"),
             _command(corpus, command, output, "exec-read"),
             _result("call-read", output))

    _, events, _, uncertain, details = read_window(
        trace, (2, 4), corpus, archive=True,
        selections={3: [("case.md", 15)]},
    )
    delivery = events[0]["delivery"]
    assert delivery["state"] == "visible" and delivery["return_line"] == 4
    assert len(delivery["passages"]) == 13
    assert {key: delivery["passages"][-1][key] for key in ("ref", "line", "text")} == {
        "ref": "case.md", "line": 15, "text": "content line 15",
    }
    assert not any(key in delivery["passages"][-1]
                   for key in ("redacted", "root_normalized", "truncated"))
    assert delivery["archive_omitted"] is True
    assert delivery["omitted_passages"] == 2
    assert uncertain == [] and details == []


def test_read_tools_infer_only_reliable_line_numbers(tmp_path):
    corpus = tmp_path / "knowledge"
    corpus.mkdir()
    trace = tmp_path / "rollout.jsonl"
    cases = [
        ("cat case.md", "first\nsecond\n", [1, 2]),
        ("nl -ba case.md", "     1\tfirst\n     2\tsecond\n", [1, 2]),
    ]
    rows = [_meta(corpus)]
    for index, (command, output, _) in enumerate(cases):
        call_id = f"call-{index}"
        rows.extend([
            _call(corpus, command, call_id),
            _command(corpus, command, output, f"exec-{index}"),
            _result(call_id, output),
        ])
    _rollout(trace, *rows)

    _, events, _, uncertain, _ = read_window(trace, (2, len(rows)), corpus, archive=True)
    assert [event["delivery"]["state"] for event in events] == ["visible", "visible"]
    assert [[passage["line"] for passage in event["delivery"]["passages"]]
            for event in events] == [[1, 2], [1, 2]]
    assert uncertain == []


def test_join_must_be_inside_window_and_not_rebuilt_from_adjacent_command(tmp_path):
    corpus = tmp_path / "knowledge"
    corpus.mkdir()
    trace = tmp_path / "rollout.jsonl"
    command = "rg -n needle ."
    output = "a.md:2:needle\n"
    _rollout(trace, _meta(corpus), _call(corpus, command, "call-search"),
             _command(corpus, command, output, "exec-search"),
             _result("call-search", output))

    _, events, _, uncertain, details = read_window(trace, (3, 4), corpus, archive=True)
    delivery = events[0]["delivery"]
    assert delivery["state"] == "unknown"
    assert "return_line" not in delivery
    assert delivery["passages"] == [] and uncertain == [3]
    assert details[0]["id"] == "file-3"
    assert "exec-search" not in json.dumps(details)


def test_closed_window_ignores_later_duplicate_and_partial_trace_rows(tmp_path):
    corpus = tmp_path / "knowledge"
    corpus.mkdir()
    trace = tmp_path / "rollout.jsonl"
    command = "rg -n needle ."
    output = "a.md:2:needle\n"
    _rollout(
        trace, _meta(corpus), _call(corpus, command, "call-first"),
        _command(corpus, command, output, "exec-first"),
        _result("call-first", output),
        _call(corpus, command, "call-later"),
        _command(corpus, command, output, "exec-later"),
    )
    with trace.open("a", encoding="utf-8") as stream:
        stream.write('{"type":"response_item","payload":')

    _, events, _, uncertain, details = read_window(trace, (2, 4), corpus, archive=True)
    assert events[0]["delivery"]["state"] == "visible"
    assert events[0]["delivery"]["return_line"] == 4
    assert uncertain == [] and details == []


@pytest.mark.parametrize("structured", [False, True])
def test_truncated_result_keeps_only_exact_visible_lines_and_refs(tmp_path, structured):
    corpus = tmp_path / "knowledge"
    corpus.mkdir()
    trace = tmp_path / "rollout.jsonl"
    command = "rg -n needle ."
    aggregate = "a.md:1:first\nb.md:2:middle\nc.md:3:last\n"
    visible = (
        "Warning: truncated output (original token count exceeded)\n"
        "a.md:1:first\n[omitted]\nc.md:3:last\n"
    )
    _rollout(trace, _meta(corpus),
             _call(corpus, command, "call-search", emit="r" if structured else "r.output"),
             _command(corpus, command, aggregate, "exec-search"),
             (_exec_result if structured else _result)("call-search", visible))

    _, events, _, uncertain, details = read_window(trace, (2, 4), corpus, archive=True)
    event = events[0]
    delivery = event["delivery"]
    assert delivery["state"] == "visible" and delivery["return_line"] == 4
    assert delivery["runtime_truncated"] is True
    assert delivery["visible_refs"] == ["a.md", "c.md"]
    assert [(passage["ref"], passage["line"]) for passage in delivery["passages"]] == [
        ("a.md", 1), ("c.md", 3),
    ]
    assert [material["ref"] for material in event["materials"]] == ["a.md", "b.md", "c.md"]
    assert uncertain == [3]
    assert details[0]["reason"] == "command_output_incomplete"


def test_transformed_and_multi_file_outputs_cannot_backfill_passages(tmp_path):
    corpus = tmp_path / "knowledge"
    corpus.mkdir()
    trace = tmp_path / "rollout.jsonl"
    transformed_command = "rg -n needle ."
    transformed_aggregate = "a.md:2:private content\n"
    transformed_response = "a.md:2:[redacted]\n"
    multi_command = "cat a.md b.md"
    multi_output = "first file text\nsecond file text\n"
    _rollout(
        trace, _meta(corpus),
        _call(corpus, transformed_command, "call-transformed"),
        _command(corpus, transformed_command, transformed_aggregate, "exec-transformed"),
        _result("call-transformed", transformed_response),
        _call(corpus, multi_command, "call-multi"),
        _command(corpus, multi_command, multi_output, "exec-multi"),
        _result("call-multi", multi_output),
    )

    _, events, _, uncertain, details = read_window(trace, (2, 7), corpus, archive=True)
    assert [event["delivery"]["state"] for event in events] == ["unknown", "unknown"]
    assert all(event["delivery"]["passages"] == [] for event in events)
    assert all("return_line" not in event["delivery"] for event in events)
    assert uncertain == [3, 6]
    assert [detail["reason"] for detail in details] == [
        "output_bytes_do_not_match", "read_sources_not_separable",
    ]
    assert "private content" not in json.dumps(details)


def test_zero_hit_rg_is_visible_when_empty_outer_result_is_correlated(tmp_path):
    corpus = tmp_path / "knowledge"
    corpus.mkdir()
    trace = tmp_path / "rollout.jsonl"
    command = "rg -n absent ."
    _rollout(trace, _meta(corpus), _call(corpus, command, "call-empty"),
             _command(corpus, command, "", "exec-empty", exit_code=1),
             _result("call-empty", ""))

    _, events, _, uncertain, details = read_window(trace, (2, 4), corpus, archive=True)
    delivery = events[0]["delivery"]
    assert events[0]["materials"] == []
    assert delivery["state"] == "visible" and delivery["return_line"] == 4
    assert delivery["runtime_truncated"] is False
    assert delivery["passages"] == [] and delivery["visible_refs"] == []
    assert uncertain == [] and details == []


def test_filename_only_search_uses_visible_refs_without_invented_passages(tmp_path):
    corpus = tmp_path / "knowledge"
    corpus.mkdir()
    trace = tmp_path / "rollout.jsonl"
    command = "rg -l needle ."
    output = "a.md\n"
    _rollout(trace, _meta(corpus), _call(corpus, command, "call-files"),
             _command(corpus, command, output, "exec-files"),
             _result("call-files", output))

    _, events, _, uncertain, details = read_window(trace, (2, 4), corpus, archive=True)
    delivery = events[0]["delivery"]
    assert delivery["state"] == "visible"
    assert delivery["visible_refs"] == ["a.md"]
    assert delivery["passages"] == []
    assert uncertain == [] and details == []


def test_read_truncation_marker_blocks_inferred_late_line_numbers(tmp_path):
    corpus = tmp_path / "knowledge"
    corpus.mkdir()
    trace = tmp_path / "rollout.jsonl"
    command = "cat case.md"
    output = "first line\ntokens truncated …\nlate text\n"
    _rollout(trace, _meta(corpus), _call(corpus, command, "call-read"),
             _command(corpus, command, output, "exec-read"),
             _result("call-read", output))

    _, events, _, uncertain, details = read_window(trace, (2, 4), corpus, archive=True)
    delivery = events[0]["delivery"]
    assert delivery["state"] == "visible" and delivery["runtime_truncated"] is True
    assert [(item["line"], item["text"]) for item in delivery["passages"]] == [
        (1, "first line"),
    ]
    assert uncertain == [3]
    assert details[0]["reason"] == "command_output_incomplete"


def test_passage_text_normalizes_corpus_root_and_redacts_secret_values(tmp_path):
    corpus = tmp_path / "knowledge"
    corpus.mkdir()
    trace = tmp_path / "rollout.jsonl"
    command = f"rg -n needle {corpus}"
    output = f"{corpus}/a.md:4:source={corpus}/private.md token=synthetic-secret\n"
    _rollout(trace, _meta(corpus), _call(corpus, command, "call-search"),
             _command(corpus, command, output, "exec-search"),
             _result("call-search", output))

    _, events, _, _, _ = read_window(trace, (2, 4), corpus, archive=True)
    passage = events[0]["delivery"]["passages"][0]
    assert passage["ref"] == "a.md" and passage["line"] == 4
    assert passage["root_normalized"] is True and passage["redacted"] is True
    assert str(corpus) not in passage["text"]
    assert "synthetic-secret" not in passage["text"]


def test_pipeline_unresolved_detail_keeps_only_safe_operation_skeleton(tmp_path):
    corpus = tmp_path / "knowledge"
    corpus.mkdir()
    trace = tmp_path / "rollout.jsonl"
    command = "rg -n needle a.md | head -1"
    output = "a.md:2:needle\n"
    _rollout(trace, _meta(corpus), _command(corpus, command, output, "exec-pipe"))

    _, events, _, uncertain, details = read_window(trace, (2, 2), corpus, archive=True)
    assert events == [] and uncertain == [2]
    assert details[0]["id"] == "file-2"
    assert details[0]["operation"] == {
        "tools": ["rg"], "action": "unknown", "compound": True,
    }
    assert "a.md" not in json.dumps(details)
    assert "needle" not in json.dumps(details)


def test_scoped_file_list_filter_keeps_only_a_few_normalized_path_samples(tmp_path):
    corpus = tmp_path / "knowledge"
    scope = corpus / "skill_library"
    scope.mkdir(parents=True)
    trace = tmp_path / "rollout.jsonl"
    for ignore_case, flag in ((False, ""), (True, "-i ")):
        command = f"rg --files {scope} | rg {flag}needle"
        call_id = f"call-list-{ignore_case}"
        output = "".join(f"{scope}/case-{index}.md\n" for index in range(1, 6))
        _rollout(
            trace, _meta(corpus), _call(corpus, command, call_id),
            _command(corpus, command, output, f"exec-list-{ignore_case}"),
            _result(call_id, output),
        )

        _, events, _, uncertain, details = read_window(
            trace, (2, 4), corpus, archive=True,
        )
        detail = details[0]
        assert events == [] and uncertain == [3]
        assert detail["id"] == "file-3" and detail["return_line"] == 4
        assert detail["operation"] == {
            "tools": ["rg", "rg"], "action": "file_list_filter",
            "scope": ["skill_library"], "compound": True,
        }
        assert detail["runtime_truncated"] is False
        assert detail["archive_omitted"] is True
        assert len(detail["excerpt"]) == 4
        assert detail["excerpt"][0]["ref"] == "skill_library/case-1.md"
        assert detail["excerpt"][0]["line"] is None
        assert detail["excerpt"][0]["text"] == (
            "<KNOWLEDGE_ROOT>/skill_library/case-1.md"
        )
        assert str(corpus) not in json.dumps(detail)
        assert "exec-list" not in json.dumps(detail)
        assert "materials" not in detail


def test_duplicate_identical_command_events_make_join_ambiguous(tmp_path):
    corpus = tmp_path / "knowledge"
    corpus.mkdir()
    trace = tmp_path / "rollout.jsonl"
    command = "rg -n needle ."
    output = "a.md:2:needle\n"
    _rollout(trace, _meta(corpus), _call(corpus, command, "call-search"),
             _command(corpus, command, output, "exec-one"),
             _command(corpus, command, output, "exec-two"),
             _result("call-search", output))

    _, events, _, uncertain, details = read_window(trace, (2, 5), corpus, archive=True)
    assert [event["delivery"]["state"] for event in events] == ["unknown", "unknown"]
    assert all(event["delivery"]["passages"] == [] for event in events)
    assert uncertain == [3, 4]
    assert all(detail["reason"] == "command_not_unique" for detail in details)
    assert "exec-one" not in json.dumps(events) and "exec-two" not in json.dumps(events)

def test_truncated_repeated_paragraph_has_no_unambiguous_source_line(tmp_path):
    corpus = tmp_path / "knowledge"
    trace = tmp_path / "rollout.jsonl"
    command = "cat case.md"
    body = "first\nrepeat\nagain\nrepeat\nagain\nlast\n"
    shown = "Warning: truncated output\nrepeat\nagain\nlast\n"
    _rollout(trace, _meta(corpus), _call(corpus, command, "read"),
             _command(corpus, command, body, "read-file"), _result("read", shown))

    _, events, _, _, _ = read_window(trace, (2, 4), corpus, archive=True)
    assert [(p["line"], p["text"]) for p in events[0]["delivery"]["passages"]] == [(6, "last")]
