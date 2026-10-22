import json
import sys
import time
from pathlib import Path

mode, final_path, answer_path = sys.argv[1:]
answer = json.loads(Path(answer_path).read_text(encoding="utf-8"))
if mode == "timeout":
    time.sleep(60)
elif mode == "incorrect":
    answer["claim_scope"] = "production"
elif mode == "null":
    answer = None
elif mode == "nonobject":
    answer = []
if mode != "missing_output":
    Path(final_path).write_text(
        "{broken" if mode == "invalid_json" else json.dumps(answer), encoding="utf-8"
    )
event = {"type": "turn.completed"}
if mode != "unknown_usage":
    event["usage"] = {"input_tokens": 17, "output_tokens": 3}
print("{broken" if mode == "invalid_trace" else json.dumps(event), flush=True)
raise SystemExit(7 if mode == "nonzero" else 0)
