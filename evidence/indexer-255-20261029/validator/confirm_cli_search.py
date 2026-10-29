"""One prospective CLI-search replication; independent of v1, no pooling/retries."""
import argparse
import json
import random
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from tools.evaluate_indexer import cli, digest, identity, percentile, write  # noqa: E402


def summary(groups):
    rows = {}
    for arm in "AB":
        values = [g[arm]["ns"] / 1e6 for g in groups]
        rows[arm] = {"n": len(values), "p50_ms": statistics.median(values),
                     "p95_ms": percentile(values, .95)}
    for metric in ("p50_ms", "p95_ms"):
        rows[metric + "_change_percent"] = 100 * (rows["B"][metric] / rows["A"][metric] - 1)
    rng = random.Random(25504)
    distributions = {"p50_ms": [], "p95_ms": []}
    for _ in range(10000):
        sample = rng.choices(groups, k=len(groups))
        values = {arm: [g[arm]["ns"] for g in sample] for arm in "AB"}
        for metric, estimator in (("p50_ms", statistics.median),
                                  ("p95_ms", lambda v: percentile(v, .95))):
            distributions[metric].append(100 * (estimator(values["B"]) /
                                                estimator(values["A"]) - 1))
    rows["paired_bootstrap_95ci"] = {
        metric: [percentile(v, .025), percentile(v, .975)]
        for metric, v in distributions.items()
    }
    hashes = {g[arm]["output_sha256"] for g in groups for arm in "AB"}
    rows["all_output_parity"] = len(hashes) == 1
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Refusing to overwrite a prior study")
    protocol = json.loads(args.protocol.read_text())
    roots = {"A": args.baseline.resolve(), "B": args.candidate.resolve()}
    assert digest((REPO / "tools/evaluate_indexer.py").read_bytes()) == protocol[
        "frozen_v1_runner_sha256"]
    assert digest((roots["B"] / "src/inferrsi/knowledge_operations.py").read_bytes()) == protocol[
        "candidate_source_sha256"]
    before = {a: identity(root) for a, root in roots.items()}
    assert before["A"]["revision"] == protocol["baseline_revision"]
    assert before["B"]["revision"] == protocol["candidate_revision"]
    assert before["A"]["corpus"] == before["B"]["corpus"]
    v1 = json.loads((REPO / "evidence/indexer-255-20261029/results/paired-run/timing.json")
                    .read_text())
    assert before == v1["before"]
    result = {"study": "confirmation-v2", "protocol_sha256": digest(args.protocol.read_bytes()),
              "wrapper_sha256": digest(Path(__file__).read_bytes()), "before": before,
              "started_utc": datetime.now(timezone.utc).isoformat(),
              "verdict": "INCONCLUSIVE", "confirmation": [], "negative_control": []}
    start = time.monotonic_ns()
    try:
        phases = (("confirmation", protocol["samples"], 25502),
                  ("negative_control", protocol["negative_control"]["pairs"], 25503))
        for name, count, seed in phases:
            order = ["AB"] * (count // 2) + ["BA"] * (count // 2)
            random.Random(seed).shuffle(order)
            for index, sequence in enumerate(order):
                row = {"index": index, "order": sequence,
                       "start_offset_ns": time.monotonic_ns() - start}
                for arm in sequence:
                    root = roots[arm] if name == "confirmation" else roots["A"]
                    offset = time.monotonic_ns() - start
                    row[arm] = {**cli(root, "search", {}), "start_offset_ns": offset}
                result[name].append(row)
                write(args.output, result)
                if (index + 1) % 20 == 0:
                    print(name, index + 1, flush=True)
        result["after"] = {a: identity(root) for a, root in roots.items()}
        assert result["after"] == before
        result["summary"] = {name: summary(result[name])
                             for name in ("confirmation", "negative_control")}
        actual = result["summary"]["confirmation"]
        failed = []
        if not actual["all_output_parity"]:
            failed.append("output mismatch")
        for metric in ("p50", "p95"):
            if actual[metric + "_ms_change_percent"] > protocol["gates"][
                    metric + "_max_regression_percent"]:
                failed.append(metric + " regression")
        result["failed_gates"] = failed
        result["verdict"] = "FAIL" if failed else "PASS"
        result["verdict_scope"] = "Focused confirmation only; v1 remains FAIL"
    except Exception as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
        raise
    finally:
        result["ended_utc"] = datetime.now(timezone.utc).isoformat()
        write(args.output, result)


if __name__ == "__main__":
    main()
