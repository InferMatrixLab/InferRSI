"""Scripted subprocess telemetry; no model, network, or billed tokens."""

import json
import sys
from pathlib import Path

mode, final, answer, tokens = sys.argv[1:]
output = json.loads(Path(answer).read_text(encoding="utf-8"))
if mode == "incorrect":
    output["claim_scope"] = "production"
Path(final).write_text(json.dumps(output), encoding="utf-8")
for _ in range(2):
    print(json.dumps({"type": "item.completed", "item": {
        "type": "command_execution", "command": "fixture-read", "exit_code": 0}}))
usage = {"input_tokens": int(tokens) - 10, "output_tokens": 10, "cached_input_tokens": 20}
if mode == "malformed_usage":
    usage = [1]
print(json.dumps({"type": "turn.completed", "usage": None if mode == "unknown" else usage}))
raise SystemExit(7 if mode == "runner_error" else 0)
