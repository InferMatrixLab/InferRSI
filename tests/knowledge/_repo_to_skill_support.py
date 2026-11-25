"""Common CLI inputs and subprocess setup for repo-to-skill helpers."""

import os
import subprocess
import sys

MALFORMED_HELPER_INPUTS = (
    b"", b"null", b"[]", b"{}", b"not-json-private-payload", b"\xff",
    b'{"schema_version":1,"schema_version":2}', b'{"schema_version":NaN}',
    b'{"schema_version":Infinity}', b"[" * 1500 + b"0" + b"]" * 1500,
)


def run_helper_cli(script, *args, data=None, cwd=None):
    return subprocess.run(
        [sys.executable, str(script), *args], input=data, capture_output=True,
        timeout=10, cwd=cwd, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


def assert_cli_size_limit(call_cli, area, valid_json, limit, tmp_path):
    # Trailing JSON whitespace changes the byte count without changing the document.
    at_limit = valid_json.ljust(limit, b" ")
    assert len(at_limit) == limit
    input_file = tmp_path / "size-boundary.json"
    for data, expected_code in ((at_limit, 0), (at_limit + b" ", 2)):
        input_file.write_bytes(data)
        for result in (
            call_cli(area, "-", data=data, cwd=tmp_path),
            call_cli(area, str(input_file), cwd=tmp_path),
        ):
            assert result.returncode == expected_code, (result.args, len(data), result.stderr)
            if expected_code == 2:
                assert not result.stdout and b"Traceback" not in result.stderr
