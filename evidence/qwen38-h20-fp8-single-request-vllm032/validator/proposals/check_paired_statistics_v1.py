import copy
import hashlib
import importlib.util
import json
from pathlib import Path

p = Path(__file__).with_name("paired_statistics_v1.py")
spec = importlib.util.spec_from_file_location("proposal", p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixture(ratios):
    return [
        {
            "input_tokens": n,
            "case": f"n{n}-s{i}",
            "repetition": r,
            "arm": a,
            "valid": True,
            "output_tokens": 2048,
            "ttft_s": (ratios[i] if a == "candidate" else 1),
            "latency_s": 20 * (ratios[i] if a == "candidate" else 1),
        }
        for n in m.LENGTHS
        for i in range(10)
        for r in m.REPETITIONS
        for a in m.ARMS
    ]


checks = []


def check(name, condition):
    assert condition, name
    checks.append(name)


rows = fixture([1] * 10)
report = m.summarize(rows)
check(
    "identity_proposed_pass_only",
    len(report["metrics"]) == 6
    and all(
        r["proposed_metric_verdict"] == "PASS"
        and r["median_paired_ratio"] == 1
        and r["upper_one_sided_95"] == 1
        for r in report["metrics"]
    )
    and report["campaign_verdict"] == "INCONCLUSIVE"
    and report["activated"] is False,
)
check("bootstrap_repeatability", report == m.summarize(rows))
check("row_order_invariant", report == m.summarize(list(reversed(rows))))
report = m.summarize(fixture([1.04] * 10))
check(
    "slower_than_margin_fails",
    all(r["proposed_metric_verdict"] == "FAIL" for r in report["metrics"]),
)
report = m.summarize(fixture([0.99] * 5 + [1.06] * 5))
check(
    "uncertainty_inconclusive",
    all(
        r["proposed_metric_verdict"] == "INCONCLUSIVE"
        and abs(r["median_paired_ratio"] - 1.025) < 1e-12
        and r["upper_one_sided_95"] > 1.03
        for r in report["metrics"]
    ),
)
mutations = {
    "missing": rows[:-1],
    "duplicate": rows + [rows[0]],
    "wrong_top_level": {},
    "bad_record": rows + [[]],
}
for label, field, value in [
    ("huge_int", "ttft_s", 10**500),
    ("nan", "ttft_s", float("nan")),
    ("negative", "ttft_s", -1),
    ("bad_length", "output_tokens", 2047),
    ("bool_length", "output_tokens", True),
    ("false_valid", "valid", False),
    ("unexpected_case", "case", "n8192-s10"),
    ("bad_identity_type", "repetition", True),
    ("unhashable", "case", []),
    ("zero_decode", "latency_s", 1),
    ("over_timeout", "latency_s", 1801),
]:
    altered = copy.deepcopy(rows)
    altered[0][field] = value
    mutations[label] = altered
altered = copy.deepcopy(rows)
altered[0]["ttft_s"] = 5e-324
mutations["ratio_overflow"] = altered
for label, altered in mutations.items():
    result = m.summarize(altered)
    check(
        label,
        bool(result["errors"])
        and not result["metrics"]
        and result["campaign_verdict"] == "INCONCLUSIVE",
    )
check("stable_large_median", m.median([1e308, 1e308]) == 1e308)
try:
    m.parse_records('[{"valid":false,"valid":true}]')
except ValueError:
    check("duplicate_json_key_rejected", True)
else:
    check("duplicate_json_key_rejected", False)
check("linear_quantile", m.quantile([0, 10], 0.95) == 9.5)
print(
    json.dumps(
        {
            "verdict": "INCONCLUSIVE",
            "scope": "synthetic_proposal_checks_only",
            "validator_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "checks_passed": len(checks),
            "checks": checks,
            "bootstrap_sample_sha256": m.summarize(rows)["bootstrap"]["sample_indices_sha256"],
        },
        indent=2,
    )
)
