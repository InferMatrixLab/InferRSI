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
])
def test_unreadable_shell_forms_stay_incomplete(tmp_path, command):
    # A search this reader cannot decode must not count as complete coverage.
    item = {"command": command, "exit_code": 0, "aggregated_output": ""}
    assert _command(item, tmp_path) == (None, False, None)


def test_dash_c_after_double_dash_names_a_script_file():
    # bash -- -c runs a script file named -c, so no inline code is visible.
    assert _recorded_argv({"command": ["bash", "--", "-c", "rg -n needle docs"]}) == (None, False)
