"""Generate a synthetic partial campaign and its offline dashboard; no model execution.

Usage: python tests/fixtures/dashboard_experiments.py <output-directory>
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from inferrsi.observability.dashboard import write_dashboard
from inferrsi.observability.optimization_log import record_log


def write(path: Path, data: dict) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(data, indent=2).encode()
    path.write_bytes(raw)
    return {"path": path.name, "sha256": hashlib.sha256(raw).hexdigest()}


def metric(workload="W1", value=8, **extra):
    return {
        "id": f"{workload}-latency", "name": "latency", "workload": workload,
        "unit": "s", "scope": "http_e2e", "direction": "minimize",
        "aggregation": "median", "aggregate": value, "sample_count": 5,
        "configuration": {"model": "synthetic-image", "model_revision": "fixture-v1",
                          "shape": "1024x1024", "batch": 1, "precision": "bf16",
                          "hardware": "synthetic-npu", "protocol": "http-warmed-v1"},
        "references": [
            {"id": "local", "role": "local_baseline", "value": 12, "unit": "s",
             "provenance": "Synthetic local control; fixture data"},
            {"id": "author", "role": "external_reference", "value": 4, "unit": "s",
             "provenance": "Synthetic author report on other hardware; not locally reproduced"},
            {"id": "target", "role": "frozen_target", "value": 0.5, "unit": "s",
             "definition": "inverse_latency_ratio", "relative_to": "author", "frozen": True,
             "provenance": "Synthetic frozen plan; ratio target"},
        ], **extra,
    }


def external(root, name, round_number, metrics, *, candidate_id=None, quality="PASS",
             verdict="INCONCLUSIVE", state="completed", events=None):
    record = {
        "schema_version": 1, "kind": "external_optimization_record",
        "candidate_id": candidate_id or name, "backend": "ascend", "protocol": "synthetic-v1",
        "source_refs": [write(root / f"{name}-source.json", {"synthetic": True})],
        "metrics": metrics, "quality": {"verdict": quality}, "performance_verdict": verdict,
        "state": state, "events": events or [], "note": "Synthetic fixture; no campaign claim.",
    }
    ref = write(root / f"{name}.json", record)
    write(root / "candidates" / name / "candidate.json", {
        "candidate_id": candidate_id or name, "title": name, "round": round_number,
        "external_record_ref": ref,
        "details": {"summary": f"Synthetic optimization: {name}"},
    })


def build(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    write(root / "campaign.json", {"campaign_id": "synthetic-experiment-curves", "synthetic": True})
    for round_number, name, values in [(1, "native-control", [12, 18, 24]),
                                        (2, "vae-graph", [10, 16, 21]),
                                        (3, "parallel-stream", [8.8, 14, 19])]:
        metrics = []
        for i, value in enumerate(values, 1):
            item = metric(f"W{i}", value, timestamp=f"2026-01-01T12:0{round_number}:00Z")
            item["references"][0]["value"] = [12, 18, 24][i - 1]
            item["references"][1]["value"] = [4, 6, 8][i - 1]
            metrics.append(item)
        external(root, name, round_number, metrics)
    external(root, "quality-rejected", 4, [metric(value=7.5)], quality="FAIL", verdict="FAIL",
             events=[{"stage": "validation", "category": "quality", "workload": "W1",
                      "summary": "Measured latency retained; image quality failed"}])
    external(root, "graph-capture-failed", 5, [], state="failed", quality="NOT_RUN",
             events=[{"stage": "execution", "category": "failure", "workload": "W1",
                      "scope": "http_e2e",
                      "summary": "Graph capture failed before benchmark; no E2E result"}])
    for name, value in [("repeat-a", 8.6), ("repeat-b", 8.7)]:
        external(root, name, 6, [metric(value=value)], candidate_id="repeated-candidate")
    changed = metric(value=7.9)
    changed["configuration"]["precision"] = "fp16"
    external(root, "different-precision", 7, [changed])
    for name in ("unknown-a", "unknown-b"):
        unknown = metric(value=9.2)
        unknown["configuration"].pop("hardware")
        external(root, name, 8, [unknown])
    component = metric(value=20, id="tile", unit="ms", scope="vae_tile", references=[])
    external(root, "tile-only", 9, [component], quality="NOT_RUN")
    external(root, "undated", None, [metric(value=9)])
    external(root, "missing-artifact", 10, [metric(value=9)])
    (root / "missing-artifact-source.json").unlink()
    external(root, "legacy-metric", None, [{"name": "old latency", "unit": "s",
                                          "aggregate": 11, "aggregation": "median",
                                          "baseline": 12, "target": 8}])
    # Two native runs with the same candidate and round exercise precise native drilldown.
    for name, value in [("native-run-a", 105), ("native-run-b", 106)]:
        run = root / "runs" / name
        write(root / "candidates" / name / "candidate.json", {
            "candidate_id": "native-repeat", "title": name, "run_id": name, "round": 3})
        write(run / "run.lock.json", {
            "model": "synthetic-model", "model_revision": "fixture-v1", "backend": "cuda",
            "workload_id": "W-throughput", "scenario": "http", "comparison_scope": "http_e2e",
            "device_ids": ["0"], "baseline_command": ["python", "benchmark.py"],
            "candidate_command": ["python", "benchmark.py"],
            "validation_command": ["python", "validate.py"], "repetitions": 3,
            "metric_key": "throughput", "metric_unit": "tokens/s", "direction": "maximize",
            "min_improvement_pct": 10,
        })
        write(run / "repositories.lock.json", {"baseline": {"snapshot_hash": "a" * 64}})
        write(run / "environment.json", {
            "host": {"platform": "synthetic-os"},
            "target_python": {"environment": {"python": "synthetic-version",
                                               "packages": {"torch": "fixture",
                                                            "vllm": "fixture"}}},
            "device": {"status": "available", "selection_verified": True,
                       "devices": [{"index": "0", "uuid": "synthetic-device", "name": "fixture",
                                    "driver_version": "fixture"}]},
        })
        write(run / "evaluation.json", {
            "verdict": "FAIL", "metric_key": "throughput", "metric_unit": "tokens/s",
            "direction": "maximize", "improvement_pct": value - 100,
            "baseline": {"median": 100, "values": [99, 100, 101]},
            "candidate": {"median": value, "values": [value - 1, value, value + 1]},
        })
        write(run / "status.json", {"state": "completed"})
        write(run / "validation" / "execution.json", {"status": "completed", "returncode": 0})
    log = {
        "schema_version": 2, "reviewed_by_caller": True,
        "campaign_id": "synthetic-experiment-curves",
        "goal": {"statement": "Synthetic partial campaign: performance and failures",
                 "metric": "Per-workload absolute measurements; independent scopes"},
        "knowledge": [], "search_space": {"state": "partial", "missing_reason": "Fixture",
                                           "dimensions": []}, "iterations": [],
        "summary": {"state": "partial", "missing_reason": "Synthetic campaign remains incomplete",
                    "successes": [{"text": "VAE graph improved measured latency",
                                   "evidence": ["candidate:vae-graph"]},
                                  {"text": "Repeated native runs retain separate identities",
                                   "evidence": ["candidate:native-repeat"]}],
                    "failures": [{"text": "Graph capture failed before measurement",
                                  "evidence": ["candidate:graph-capture-failed"],
                                  "cause_stage": "execution"},
                                 {"text": "Legacy text-only failure: 123 s is narrative, not data",
                                  "evidence": []}],
                    "lessons": ["Keep component and service results separate"],
                    "limitations": ["Synthetic data; E2E campaign acceptance unverified"]},
    }
    path = root / "story-input.json"
    write(path, log)
    record_log(root, path)
    return write_dashboard(root)


if __name__ == "__main__":
    print(build(Path(sys.argv[1])))
