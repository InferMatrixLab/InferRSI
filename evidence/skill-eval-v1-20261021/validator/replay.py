import hashlib
import importlib.util
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("frozen_skill_verifier", ROOT / "validator/verify.py")
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    counts = {"PASS": 0, "FAIL": 0, "INCONCLUSIVE": 0}
    replayed, unavailable = 0, 0
    for path in sorted((ROOT / "results").glob("v*/*/record.json")):
        record = load(path)
        counts[record["verdict"]] += 1
        expected_input = record.get("input_hashes", {}).get("task.json")
        if expected_input:
            assert digest(path.parent / "task.json") == expected_input, str(path)
        answer = path.parent / "answer.json"
        if not answer.is_file() or record.get("checks") is None:
            unavailable += 1
            continue
        assert digest(answer) == record["output_sha256"], str(answer)
        checks = verifier.verify(load(path.parent / "task.json"), load(answer))
        assert checks == record["checks"], str(path)
        assert record["execution_state"] == "completed", str(path)
        assert record["inputs_unchanged"], str(path)
        assert record["verdict"] == ("PASS" if checks["passed"] else "FAIL"), str(path)
        replayed += 1
    print(
        json.dumps(
            {
                "replayed_checks": replayed,
                "checks_unavailable": unavailable,
                "original_verdicts": counts,
            }
        )
    )


if __name__ == "__main__":
    main()
