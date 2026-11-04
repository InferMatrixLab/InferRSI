import copy
import hashlib
import importlib.util
import json
from pathlib import Path

p = Path(__file__).with_name("paired_statistics_8k_v1.py")
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
    "identity_metric_pass_only",
    len(report["metrics"]) == 2
    and all(
        r["metric_verdict"] == "PASS"
        and r["median_paired_ratio"] == 1
        and r["upper_one_sided_95"] == 1
        for r in report["metrics"]
    )
    and report["campaign_verdict"] == "INCONCLUSIVE"
    and report["statistics_approved"] is True,
)
check("bootstrap_repeatability", report == m.summarize(rows))
check("row_order_invariant", report == m.summarize(list(reversed(rows))))
report = m.summarize(fixture([1.04] * 10))
check(
    "slower_than_margin_fails",
    all(r["metric_verdict"] == "FAIL" for r in report["metrics"]),
)
report = m.summarize(fixture([0.99] * 5 + [1.06] * 5))
check(
    "uncertainty_inconclusive",
    all(
        r["metric_verdict"] == "INCONCLUSIVE"
        and abs(r["median_paired_ratio"] - 1.025) < 1e-12
        and r["upper_one_sided_95"] > 1.03
        for r in report["metrics"]
    ),
)

check("matrix_size_8k_only", len(rows) == 60 and m.LENGTHS == (8192,))
varied = copy.deepcopy(rows)
for row in varied:
    if row["arm"] == "candidate":
        ratio = 0.9 + int(row["case"].split("s")[1]) * 0.01 + row["repetition"] * 0.001
        row["ttft_s"] = ratio
        row["latency_s"] = ratio * 20
cluster_report = m.summarize(varied)
check("retains_three_repetitions_per_input", all(
    len(clusters) == 10 and all(len(values) == 3 for values in clusters)
    and all(abs(values[1]-values[0]-0.001) < 1e-12
            and abs(values[2]-values[1]-0.001) < 1e-12 for values in clusters)
    for clusters in [metric["paired_ratios_by_input"] for metric in cluster_report["metrics"]]
))
boundary = m.summarize(fixture([1.03] * 10))
check("inclusive_margin", all(row["metric_verdict"] == "PASS" for row in boundary["metrics"]))

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
    ("unsupported_64k", "input_tokens", 65536),
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
            "scope": "synthetic_approved_8k_reducer_checks_only",
            "validator_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "checks_passed": len(checks),
            "checks": checks,
            "bootstrap_sample_sha256": m.summarize(rows)["bootstrap"]["sample_indices_sha256"],
        },
        indent=2,
    )
)
