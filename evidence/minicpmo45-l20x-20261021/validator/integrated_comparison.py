"""Validate updated-main integration; reused cohort, not an untouched holdout."""

import argparse
import json
from pathlib import Path

from noninferiority import evaluate
from summarize_results import aggregate


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--quality-dir", type=Path, required=True)
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    plan = json.loads(a.plan.read_text())
    report = {
        "scope": plan["scope"],
        "baseline": aggregate(a.baseline),
        "candidate": aggregate(a.candidate),
        "quality": {},
        "performance": [],
    }
    try:
        for root in (a.baseline, a.candidate):
            for c in plan["concurrency"]:
                for k in range(1, plan["measured_repeats"] + 1):
                    folder = root / f"c{c}/run{k}"
                    summary = json.loads((folder / "summary.json").read_text())
                    if not summary["valid"] or summary["n_failed"] or summary["n_requests"] != 320:
                        raise ValueError("Invalid measured run")
                    requests = [
                        json.loads(line)
                        for line in (folder / "requests.jsonl").read_text().splitlines()
                    ]
                    if len(requests) != 320 or {x["request_id"] for x in requests} != set(
                        plan["expected_ids"]
                    ):
                        raise ValueError("Wrong measured prompt coverage")
        for c in plan["quality_concurrency"]:
            docs = [
                json.loads((a.quality_dir / f"{prefix}-c{c}.json").read_text())
                for prefix in ("vllm-latest-main", "vllm-integrated-candidate")
            ]
            if any(set(d["rows"]) != set(plan["expected_ids"]) for d in docs):
                raise ValueError("Wrong quality prompt coverage")
            report["quality"][str(c)] = evaluate(*docs, plan["margins"])
            report["quality"][str(c)]["means"] = {
                "baseline": docs[0]["summary"],
                "candidate": docs[1]["summary"],
            }
        for c in (16, 32):
            b, d = [
                next(v for v in report[key] if v["concurrency"] == c)
                for key in ("baseline", "candidate")
            ]
            passed = min(d["throughput_frames_s_runs"]) > max(b["throughput_frames_s_runs"])
            report["performance"].append(
                {
                    "concurrency": c,
                    "gain_ratio": d["throughput_frames_s_mean"] / b["throughput_frames_s_mean"],
                    "all_candidate_runs_exceed_all_baseline_runs": passed,
                }
            )
        passed = all(v["verdict"] == "PASS" for v in report["quality"].values()) and all(
            v["all_candidate_runs_exceed_all_baseline_runs"] for v in report["performance"]
        )
        report["verdict"] = "PASS" if passed else "FAIL"
    except (OSError, ValueError, KeyError, StopIteration) as exc:
        report.update(verdict="INCONCLUSIVE", reason=str(exc))
    a.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"verdict": report["verdict"], "scope": report["scope"]}))


if __name__ == "__main__":
    main()
