"""Independent trusted evaluator. Direct imports are for trusted controls only."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


def load_traces(split="all", path=None):
    path = Path(path) if path else Path(__file__).with_name("fixtures.json")
    document = json.loads(path.read_text(encoding="utf-8"))
    if document["schema"] != "synthetic-kv-reclamation-traces-v1":
        raise ValueError("unsupported fixture schema")
    return [t for t in document["traces"] if split == "all" or t["split"] == split]


def _json_bytes(value):
    # Unlike Python equality this distinguishes true from 1, or 1.0 from 1.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def expected_actual(trace):
    return {
        "observations": trace["expected"],
        "pending": trace["expected"][-1]["pending"] if trace["expected"] else [],
    }


def compare(trace, actual):
    """Compare the isolated driver JSON envelope against trusted frozen expected bytes."""
    try:
        return _json_bytes(actual) == _json_bytes(expected_actual(trace))
    except (ValueError, TypeError):
        return False


def verify_observations(trace, actual):
    if compare(trace, actual):
        return {"id": trace["id"], "passed": True}
    result = {"id": trace["id"], "passed": False, "reason": "output envelope mismatch"}
    if not isinstance(actual, dict) or not isinstance(actual.get("observations"), list):
        return result
    observations = actual["observations"]
    if len(observations) != len(trace["expected"]):
        result["reason"] = "observation count mismatch"
        return result
    for index, (expected, observed) in enumerate(zip(trace["expected"], observations)):
        try:
            equal = _json_bytes(expected) == _json_bytes(observed)
        except (ValueError, TypeError):
            equal = False
        if not equal:
            result.update(reason="event observation mismatch", event_index=index)
            return result
    result["reason"] = "final pending or envelope mismatch"
    return result


def _pending_snapshot(value):
    if type(value) is not list:
        raise TypeError("pending return must be a list")
    result = []
    for item in value:
        if (
            type(item) is not tuple
            or len(item) != 3
            or type(item[0]) is not str
            or type(item[1]) is not int
            or type(item[2]) is not tuple
            or any(type(block) is not int for block in item[2])
        ):
            raise TypeError("invalid pending return type")
        result.append([item[0], item[1], list(item[2])])
    return result


def observe_trusted(factory, trace):
    """No security isolation: use only for author-controlled test doubles or controls."""
    candidate = factory()
    observations = []
    for event in trace["events"]:
        try:
            reclaimed = candidate.apply(json.loads(json.dumps(event)))
        except Exception as error:
            observation = {"error": type(error).__name__}
        else:
            if type(reclaimed) is not list or any(type(b) is not int for b in reclaimed):
                observation = {"error": "ReturnTypeError"}
            else:
                observation = {"reclaimed": list(reclaimed)}
        try:
            observation["pending"] = _pending_snapshot(candidate.pending())
        except Exception as error:
            observation["pending_error"] = type(error).__name__
        observations.append(observation)
    try:
        pending = _pending_snapshot(candidate.pending())
    except Exception as error:
        pending = {"pending_error": type(error).__name__}
    return {"observations": observations, "pending": pending}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trusted-candidate", type=Path, required=True,
                        help="Direct import, not sandboxed: trusted authored controls ONLY")
    parser.add_argument("--split", choices=("all", "development", "grader"), default="all")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("trusted_kv_candidate", args.trusted_candidate)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    results = [verify_observations(t, observe_trusted(module.Reclaimer, t))
               for t in load_traces(args.split)]
    report = {"mode": "trusted-direct-import-only", "passed": all(r["passed"] for r in results),
              "trace_count": len(results), "results": results}
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
