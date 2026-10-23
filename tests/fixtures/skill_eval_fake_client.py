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
if mode == "invalid_utf8":
    Path(final_path).write_bytes(b"\xff\xfe")
elif mode == "markdown_fence":
    Path(final_path).write_text("````\n# Untrusted heading\n[link](https://example.invalid)\n"
                                "````````\n", encoding="utf-8")
elif mode != "missing_output":
    Path(final_path).write_text(
        "{broken" if mode == "invalid_json" else json.dumps(answer), encoding="utf-8"
    )
event = {"type": "turn.completed"}
if mode != "unknown_usage":
    event["usage"] = {"input_tokens": 17, "output_tokens": 3}
    if mode == "partial_usage":
        del event["usage"]["output_tokens"]
print("{broken" if mode == "invalid_trace" else json.dumps(event), flush=True)
raise SystemExit(7 if mode == "nonzero" else 0)
