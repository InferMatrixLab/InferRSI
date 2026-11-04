import json
import os
import sys
from pathlib import Path

task = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
mode = task["verifier_fault"]
if mode == "exception":
    raise RuntimeError("Deliberate offline verifier fault")
if mode == "missing":
    raise SystemExit(0)
results = {
    "nonobject": [],
    "missing_passed": {"assertions": {"check": True}},
    "string_passed": {"passed": "false", "assertions": {"check": False}},
    "missing_assertions": {"passed": True},
    "empty_assertions": {"passed": True, "assertions": {}},
    "string_assertion": {"passed": True, "assertions": {"check": "false"}},
    "inconsistent": {"passed": True, "assertions": {"check": False}},
    "wrong_exit": {"passed": True, "assertions": {"check": True}},
    "nan_assertion": {"passed": False, "assertions": {"check": float("nan")}},
    "infinite_assertion": {"passed": False, "assertions": {"check": float("inf")}},
}
if mode == "overflow_assertion":
    payload = '{"passed":false,"assertions":{"check":1e999}}'
else:
    payload = "{broken" if mode == "invalid_json" else json.dumps(results[mode])
Path(os.environ["INFERRSI_RESULT_PATH"]).write_text(
    payload, encoding="utf-8"
)
raise SystemExit(7 if mode == "wrong_exit" else 0)
