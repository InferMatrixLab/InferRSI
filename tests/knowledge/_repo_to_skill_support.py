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
