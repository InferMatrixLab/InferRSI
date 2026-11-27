"""Recompute the two managed comparisons and the direct stock/packed measurement."""

import hashlib
import json
import math
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
ORDER = [
    "quality-baseline",
    "quality-candidate",
    "measurement-001-baseline",
    "measurement-001-candidate",
    "measurement-002-candidate",
    "measurement-002-baseline",
]


def load(path):
    return json.loads((ROOT / path).read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_receipt(row, reference):
    data = row["result"]
    raw = json.dumps(data, indent=2).encode()
    require(hashlib.sha256(raw).hexdigest() == row["result_file_sha256"], "Result hash")
    require(data["quality"] is True, "Quality check failed")
    images = [data["warmup_control"], *data["images"]]
    require([p["seed"] for p in images] == [107, 42, 771], "Image seeds")
    for image in images:
        require(image["sha256"] == reference[str(image["seed"])], "RGB hash changed")
    value = median(p["elapsed_s"] for p in data["images"])
    require(value == data["latency_s"], "Per-invocation median")
    return value


def compare(name, before, after, summary, baseline_key, candidate_key):
    reduction = 100 * (before - after) / before
    for field, value in (
        (baseline_key, before),
        (candidate_key, after),
        ("latency_reduction_pct", reduction),
        ("speedup", before / after),
    ):
        require(math.isclose(summary[field], value, rel_tol=1e-10), f"{name}: {field}")
    if "verdict" in summary:
        require(summary["verdict"] == ("PASS" if reduction >= 3 else "FAIL"), f"{name}: verdict")
    print(f"{name}: {before:.3f} -> {after:.3f} s/image ({reduction:.2f}%)")


def check_cohorts(cohorts, summaries, reference, packed):
    require([c["cohort"] for c in cohorts] == ["round", "independent_final"], "Cohort names")
    for cohort in cohorts:
        phase = cohort["cohort"]
        rows = cohort["trials"]
        require([r["invocation"] for r in rows] == ORDER, "AB/BA order")
        samples = {"baseline": [], "candidate": []}
        control_hash = None
        for row in rows:
            step = row["invocation"]
            value = read_receipt(row, reference)
            if step.startswith("measurement"):
                samples[step.split("-")[-1]].append(value)
            elif packed:
                data = row["result"]
                control = data["different_seed_control"]
                require(
                    control["seed"] == 43 and control["sha256"] != reference["42"],
                    "Changing the teapot seed must change its RGB bytes",
                )
                if step == "quality-baseline":
                    control_hash = control["sha256"]
                else:
                    require(control_hash == control["sha256"], "Changed-seed parity")
                    exact = {
                        s: {"max_channel_delta": 0, "differing_pixels": 0}
                        for s in ("107", "42", "771", "43")
                    }
                    require(data["comparisons"] == exact, "Per-pixel comparisons")
        compare(
            "packed/" + phase if packed else "shared/" + phase,
            median(samples["baseline"]),
            median(samples["candidate"]),
            summaries[phase],
            "baseline_s",
            "candidate_s",
        )


if __name__ == "__main__":
    pins = load("validator/reference.json")
    require(pins == load("incremental/validator/reference.json"), "Reference changed")
    check_cohorts(load("results/trials.json"), load("results/summary.json"), pins, False)
    inc = load("incremental/summary.json")
    check_cohorts(load("incremental/trials.json"), {r["cohort"]: r for r in inc}, pins, True)
    direct = load("results/direct-stock-packed.json")
    inputs = direct["inputs"]
    require(inputs["receipt"] == "results/input-pins-direct.json", "Direct input receipt")
    receipt = load(inputs["receipt"])
    require(
        hashlib.sha256((ROOT / inputs["receipt"]).read_bytes()).hexdigest()
        == inputs["receipt_sha256"],
        "Direct input receipt hash",
    )
    for field, reference in (
        ("baseline_revision", direct["stock_revision"]),
        ("candidate_revision", direct["packed_revision"]),
        ("runtime_image_id", inputs["runtime_image_id"]),
        ("inferrsi_revision", inputs["protocol_inferrsi_revision"]),
    ):
        require(receipt[field] == reference, f"Direct input: {field}")
    rows = direct["trials"]
    require(all(row["phase"] == "measurement" for row in rows), "Direct timing phase")
    require(
        [r["arm"] for r in rows] == ["01-stock", "02-packed", "03-packed", "04-stock"],
        "Direct AB/BA order",
    )
    values = [read_receipt(row, pins) for row in rows]
    compare(
        "stock to packed",
        median([values[0], values[3]]),
        median(values[1:3]),
        direct,
        "stock_s",
        "packed_s",
    )
