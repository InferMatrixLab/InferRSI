from pathlib import Path

import pytest

from inferrsi.apps.views.codex_search import _command, _recorded_argv

PLAIN = ["bash", "-lc", "rg -n needle docs"]


@pytest.mark.parametrize("wrapped", [
    ["bash", "-o", "pipefail", "-lc", "rg -n needle docs"],
    ["/usr/bin/env", "bash", "-lc", "rg -n needle docs"],
    ["env", "LC_ALL=C", "bash", "-e", "-lc", "rg -n needle docs"],
    # Recorded on Windows, read on any OS.
    ["C:\\Program Files\\Git\\bin\\bash.exe", "-lc", "rg -n needle docs"],
    ["C:\\Program Files\\Git\\usr\\bin\\env.exe", "bash", "-lc", "rg -n needle docs"],
    # A trailing newline ends the only line; it is not a second command.
    ["bash", "-lc", "rg -n needle docs\n"],
])
def test_wrapped_shell_forms_decode_like_the_plain_form(wrapped):
    assert _recorded_argv({"command": PLAIN}) == (["rg", "-n", "needle", "docs"], False)
    assert _recorded_argv({"command": wrapped}) == _recorded_argv({"command": PLAIN})


@pytest.mark.parametrize("command", [
    ["pwsh", "-Command", "rg -n needle docs"],
    ["bash", "search.sh"],
    ["env", "-i", "bash", "-lc", "rg -n needle docs"],
    # After --, -c is a script file name, not inline code.
    ["bash", "--", "-c", "rg -n needle docs"],
    # Recorded on Windows, read on any OS.
    ["C:\\Program Files\\PowerShell\\7\\pwsh.exe", "-Command", "rg -n needle docs"],
    ["C:\\Tools\\env.exe", "C:\\Program Files\\PowerShell\\7\\pwsh.exe", "-Command",
     "rg -n needle docs"],
    # A shell inside the unwrapped script is as opaque as the same shell run directly.
    ["bash", "-lc", "bash search.sh"],
    ["bash", "-lc", "bash -- -c 'rg -n needle docs'"],
    ["bash", "-lc", "pwsh -Command 'rg -n needle docs'"],
    # A later line of a multi-line script is a command position too.
    ["bash", "-lc", "cd docs\nbash search.sh"],
    ["bash", "-lc", "cd docs\n\n  pwsh -Command 'rg -n needle .'"],
    ["bash", "-lc", "cd docs &&\nbash search.sh"],
    # Reserved words, NAME=value prefixes, wrappers, code builtins and `&` hide a shell too.
    ["bash", "-lc", "if true; then bash search.sh; fi"],
    ["bash", "-lc", "cd docs\ncommand bash search.sh"],
    ["bash", "-lc", "X=1 bash search.sh"],
    ["bash", "-lc", "nohup bash search.sh"],
    ["bash", "-lc", "cd docs && . ./search.sh"],
    ["bash", "-lc", "source search.sh"],
    ["bash", "-lc", "eval \"$SEARCH\""],
    ["bash", "-lc", "cd docs & bash search.sh"],
    ["command", "bash", "search.sh"],
    # Commands in a substitution or subshell have no command position this reader sees.
    ["bash", "-lc", "echo $(bash search.sh)"],
    ["bash", "-lc", "echo \"`bash search.sh`\""],
    ["bash", "-lc", "(bash search.sh)"],
    # A Windows-recorded tool outside the supported set is not proof of no retrieval.
    ["C:/tools/rg.exe", "--json", "needle", "docs"],
])
def test_unreadable_shell_forms_stay_incomplete(tmp_path, command):
    # A search this reader cannot decode must not count as complete coverage.
    item = {"command": command, "exit_code": 0, "aggregated_output": ""}
    assert _command(item, tmp_path) == (None, False, None), command


@pytest.mark.parametrize("tool", ["rg", "C:/tools/rg.exe", "C:\\tools\\rg.exe"])
def test_a_windows_recorded_tool_is_read_as_that_tool(tmp_path, tool):
    # rg exited 1 (no match) in scope: complete coverage with no material, on any reader OS.
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    item = {"command": [tool, "-n", "needle", "."], "cwd": corpus.as_uri(),
            "exit_code": 1, "aggregated_output": ""}
    event, complete, _ = _command(item, corpus)
    assert event is not None and event["tool"] == "rg" and complete


def test_a_multi_line_script_keeps_its_line_boundaries():
    assert _recorded_argv({"command": ["bash", "-lc", "cd docs\nrg -n needle ."]}) == (
        ["cd", "docs", ";", "rg", "-n", "needle", "."], True)


def test_a_quoted_newline_is_not_a_line_boundary():
    assert _recorded_argv({"command": ["bash", "-lc", "rg -n 'a\nbash' docs"]}) == (
        ["rg", "-n", "a\nbash", "docs"], True)


def test_a_windows_recorded_shell_wrapper_decodes_end_to_end(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    item = {"command": ["C:\\Program Files\\Git\\bin\\bash.exe", "-lc", "rg -n needle ."],
            "cwd": corpus.as_uri(), "exit_code": 1, "aggregated_output": ""}
    event, complete, _ = _command(item, corpus)
    assert event is not None and event["tool"] == "rg" and complete


def test_dash_c_after_double_dash_names_a_script_file():
    # bash -- -c runs a script file named -c, so no inline code is visible.
    assert _recorded_argv({"command": ["bash", "--", "-c", "rg -n needle docs"]}) == (None, False)


@pytest.mark.parametrize("script, argv", [
    ("rg -n if docs", ["rg", "-n", "if", "docs"]),
    ("rg -n '$(bash x)' docs", ["rg", "-n", "$(bash x)", "docs"]),
    ("rg -n '&>' docs", ["rg", "-n", "&>", "docs"]),
    ("rg -n '2>&1' docs", ["rg", "-n", "2>&1", "docs"]),
    ("rg -n '|&' docs", ["rg", "-n", "|&", "docs"]),
])
def test_shell_syntax_inside_a_quoted_or_tool_argument_still_decodes(script, argv):
    assert _recorded_argv({"command": ["bash", "-lc", script]}) == (argv, False)


def test_a_compound_command_without_a_shell_or_tool_is_still_no_retrieval(tmp_path):
    item = {"command": ["bash", "-lc", "cd docs && ls"], "exit_code": 0, "aggregated_output": ""}
    assert _command(item, tmp_path) == (None, True, None)


@pytest.mark.parametrize("command", [
    ["rg", "-n", "&", "."],
    ["bash", "-lc", "rg -n '&' ."],
    ["bash", "-lc", "rg -n \\& ."],
    ["bash", "-lc", "rg -n \"a & b\" ."],
])
def test_a_literal_ampersand_is_an_argument_not_a_background_operator(tmp_path, command):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    item = {"command": command, "cwd": corpus.as_uri(), "exit_code": 1, "aggregated_output": ""}
    event, complete, _ = _command(item, corpus)
    assert event is not None and event["tool"] == "rg" and complete


@pytest.mark.parametrize("script, argv", [
    ("rg -n needle docs 2>&1", ["rg", "-n", "needle", "docs", "2", ">", "1"]),
    ("rg -n needle docs &> out.txt", ["rg", "-n", "needle", "docs", ">", "out.txt"]),
    ("rg -n needle docs |& cat", ["rg", "-n", "needle", "docs", "|", "cat"]),
    ("rg -n needle docs <&0", ["rg", "-n", "needle", "docs", "<", "0"]),
])
def test_an_unquoted_redirection_becomes_one_plain_operator(script, argv):
    assert _recorded_argv({"command": ["bash", "-lc", script]}) == (argv, True)


def test_a_background_ampersand_between_commands_is_a_command_boundary():
    assert _recorded_argv({"command": ["bash", "-lc", "rg -n needle docs & cd ."]}) == (
        ["rg", "-n", "needle", "docs", ";", "cd", "."], True)


@pytest.mark.parametrize("script", [
    "rg -n needle docs 2>&1",
    "rg -n needle docs &> out.txt",
    "rg -n needle docs &>> out.txt",
    "rg -n needle docs |& cat",
    "rg -n needle docs >&2",
    "rg -n needle docs <&0",
    "rg -n needle docs >| out.txt",
    "rg -n needle docs <> out.txt",
    "rg -n needle docs <<< input",
])
def test_a_redirection_is_not_decoded_as_search_scope(tmp_path, script):
    # The redirection target or file descriptor is not a path the search covered, so the
    # command yields no event and no complete coverage, even though docs/a.md matched.
    corpus = tmp_path / "corpus"
    (corpus / "docs").mkdir(parents=True)
    (corpus / "docs" / "a.md").write_text("needle\n", encoding="utf-8")
    item = {"command": ["bash", "-lc", script], "cwd": corpus.as_uri(),
            "exit_code": 0, "aggregated_output": "docs/a.md:1:needle\n"}
    assert _command(item, corpus) == (None, False, None)


def test_a_redirection_does_not_hide_the_next_command_position():
    assert _command({"command": ["bash", "-lc", "rg -n needle . |& bash search.sh"],
                     "exit_code": 0, "aggregated_output": ""}, Path("/")) == (None, False, None)


def test_a_shell_name_as_a_search_pattern_is_not_a_nested_shell():
    assert _recorded_argv({"command": ["bash", "-lc", "rg -n bash docs"]}) == (
        ["rg", "-n", "bash", "docs"], False)
