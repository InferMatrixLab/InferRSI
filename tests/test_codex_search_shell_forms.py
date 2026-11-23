import shlex

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
    # A Windows-recorded tool outside the supported set is not proof of no retrieval.
    ["C:/tools/rg.exe", "--json", "needle", "docs"],
])
def test_unreadable_shell_forms_stay_incomplete(tmp_path, command):
    # A search this reader cannot decode must not count as complete coverage.
    item = {"command": command, "exit_code": 0, "aggregated_output": ""}
    assert _command(item, tmp_path) == (None, False, None)


@pytest.mark.parametrize("direct", [
    ["bash", "search.sh"],
    ["bash", "--", "-c", "rg -n needle docs"],
    ["pwsh", "-Command", "rg -n needle docs"],
])
def test_a_wrapped_shell_reads_like_the_same_shell_run_directly(tmp_path, direct):
    wrapped = ["bash", "-lc", shlex.join(direct)]
    for command in (direct, wrapped):
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


def test_dash_c_after_double_dash_names_a_script_file():
    # bash -- -c runs a script file named -c, so no inline code is visible.
    assert _recorded_argv({"command": ["bash", "--", "-c", "rg -n needle docs"]}) == (None, False)


def test_a_shell_name_as_a_search_pattern_is_not_a_nested_shell():
    assert _recorded_argv({"command": ["bash", "-lc", "rg -n bash docs"]}) == (
        ["rg", "-n", "bash", "docs"], False)
