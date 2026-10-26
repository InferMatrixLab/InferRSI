"""Scripted answers/usage for controller tests, never model or efficacy measurements."""

import json
import sys
from pathlib import Path

answer_path, final_path, correct, tokens, fault = sys.argv[1:]
answer = json.loads(Path(answer_path).read_text(encoding="utf-8"))
if correct == "no":
    answer["claim_scope"] = "production"
Path(final_path).write_text(json.dumps(answer), encoding="utf-8")
if fault == "hidden_write":
    Path("task.json").write_text("{}", encoding="utf-8")
for i in range(3 if int(tokens) == 100 else 1):
    print(json.dumps({"type": "item.completed", "item": {
        "type": "command_execution", "command": "scripted-audit", "exit_code": 0}}))
event = {"type": "turn.completed"}
if fault != "unknown_usage":
    event["usage"] = {"input_tokens": int(tokens) - 20, "output_tokens": 20,
                      "cached_input_tokens": 10}
print(json.dumps(event))
raise SystemExit(2 if fault == "runner_error" else 0)
