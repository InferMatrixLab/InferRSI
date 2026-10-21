import json
import math
import os
import statistics
import sys
from pathlib import Path


def expected(task):
    contract, baseline, candidate = task["contract"], task["baseline"], task["candidate"]
    findings = set()
    before = statistics.median(statistics.mean(g) for g in baseline["latencies_ms"])
    after = statistics.median(statistics.mean(g) for g in candidate["latencies_ms"])
    gain = (before - after) / before * 100
    verdict, scope = "PASS", "fixed_workload"
    if task["mode"] == "extract":
        return None, gain, set(), "none"
    if baseline["workload"] != candidate["workload"]:
        findings.add("workload_mismatch")
        verdict, scope, gain = "INCONCLUSIVE", "none", None
    elif task["evidence_scope"] == "kernel":
        findings.add("unsupported_service_claim")
        verdict, scope = "INCONCLUSIVE", "kernel_only"
    elif candidate["quality"] == "missing":
        findings.add("quality_missing")
        verdict, scope = "INCONCLUSIVE", "none"
    elif candidate["quality"] == "failed":
        findings.add("quality_failed")
        verdict, scope = "FAIL", "none"
    elif candidate["failed_requests"]:
        findings.add("completion_gate_failed")
        verdict, scope = "FAIL", "none"
        if candidate["reported_requests"] < candidate["total_requests"]:
            findings.add("failed_requests_omitted")
    elif gain < contract["min_reduction_pct"]:
        findings.add("gain_gate_failed")
        verdict, scope = "FAIL", "none"
    return verdict, gain, findings, scope


def verify(task, answer):
    if (
        not isinstance(answer, dict)
        or not isinstance(answer.get("findings"), list)
        or not isinstance(answer.get("evidence"), list)
        or not all(isinstance(v, str) for v in answer["findings"] + answer["evidence"])
    ):
        return {"passed": False, "assertions": {"schema": False}}
    verdict, gain, findings, scope = expected(task)
    required_evidence = {"baseline.latencies_ms", "candidate.latencies_ms"}
    if task["mode"] == "audit":
        required_evidence.add("contract")
    for finding in findings:
        required_evidence.update(
            {
                "workload_mismatch": {"baseline.workload", "candidate.workload"},
                "unsupported_service_claim": {"evidence_scope"},
                "quality_missing": {"candidate.quality"},
                "quality_failed": {"candidate.quality"},
                "completion_gate_failed": {"candidate.failed_requests"},
                "failed_requests_omitted": {
                    "candidate.total_requests",
                    "candidate.reported_requests",
                },
                "gain_gate_failed": {"contract"},
            }[finding]
        )
    checks = {
        "report_verdict": answer.get("report_verdict") == verdict,
        "claim_scope": answer.get("claim_scope") == scope,
        "findings": set(answer.get("findings", [])) == findings,
        "reduction": answer.get("latency_reduction_pct") is None
        if gain is None
        else isinstance(answer.get("latency_reduction_pct"), (int, float))
        and not isinstance(answer.get("latency_reduction_pct"), bool)
        and math.isfinite(answer["latency_reduction_pct"])
        and abs(answer["latency_reduction_pct"] - gain) <= 0.02,
        "evidence": isinstance(answer.get("evidence"), list)
        and bool(answer["evidence"])
        and required_evidence <= set(answer["evidence"])
        and all(isinstance(p, str) and p in task["evidence_keys"] for p in answer["evidence"]),
        "explanation": isinstance(answer.get("reason"), str) and bool(answer["reason"].strip()),
    }
    return {"passed": all(checks.values()), "assertions": checks}


def main():
    task = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    answer = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    result = verify(task, answer)
    Path(os.environ["INFERRSI_RESULT_PATH"]).write_text(json.dumps(result), encoding="utf-8")
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
