"""Issue-scoped proposed metric reducer; cannot award campaign acceptance.

Input is a JSON list of independently authenticated per-request records.
This reducer validates completeness and numeric fields only. Source, device,
protocol, timing integrity and quality require separate frozen validators.
"""

import argparse
import hashlib
import json
import math
import random
from pathlib import Path

LENGTHS = (8192, 65536, 131072)
REPETITIONS = (0, 1, 2)
ARMS = ("baseline", "candidate")
DRAWS = 10000
SEED = 670032
LIMIT = 1.03


def quantile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    left = math.floor(position)
    right = math.ceil(position)
    return ordered[left] + (ordered[right] - ordered[left]) * (position - left)


def median(values):
    return quantile(values, 0.5)


def positive(value):
    try:
        return type(value) in (int, float) and math.isfinite(value) and value > 0
    except OverflowError:
        return False


def parse_records(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_json_key:" + key)
            result[key] = value
        return result

    return json.loads(text, object_pairs_hook=unique)


def summarize(rows):
    output = {
        "campaign_verdict": "INCONCLUSIVE",
        "activated": False,
        "scope": "proposed_statistics_only",
        "metrics": [],
        "errors": [],
    }
    expected = {
        (length, f"n{length}-s{case}", rep, arm)
        for length in LENGTHS
        for case in range(10)
        for rep in REPETITIONS
        for arm in ARMS
    }
    indexed = {}
    if not isinstance(rows, list):
        output["errors"].append("records_must_be_list")
        return output
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            output["errors"].append(f"invalid_record:{index}")
            continue
        try:
            key = (row["input_tokens"], row["case"], row["repetition"], row["arm"])
            identity_valid = (
                type(key[0]) is int
                and type(key[2]) is int
                and isinstance(key[1], str)
                and isinstance(key[3], str)
            )
            if not identity_valid or key not in expected or key in indexed:
                raise ValueError("identity")
            if (
                row.get("valid") is not True
                or type(row.get("output_tokens")) is not int
                or row["output_tokens"] != 2048
                or not positive(row.get("ttft_s"))
                or not positive(row.get("latency_s"))
                or row["latency_s"] <= row["ttft_s"]
                or row["latency_s"] > 1800
                or not positive((row["latency_s"] - row["ttft_s"]) / 2047)
            ):
                raise ValueError("measurement")
            indexed[key] = row
        except (KeyError, TypeError, ValueError):
            output["errors"].append(f"invalid_or_duplicate_record:{index}")
    if set(indexed) != expected:
        output["errors"].append(f"incomplete_matrix:{len(indexed)}/180")
    if output["errors"]:
        return output
    rng = random.Random(SEED)
    samples = [[rng.randrange(10) for _ in range(10)] for _ in range(DRAWS)]
    output["bootstrap"] = {
        "draws": DRAWS,
        "seed": SEED,
        "cluster": "input_id_all_three_repetitions",
        "quantile": "linear",
        "sample_indices_sha256": hashlib.sha256(
            json.dumps(samples, separators=(",", ":")).encode()
        ).hexdigest(),
    }
    for length in LENGTHS:
        for metric in ("ttft_s", "tpot_s"):
            arms = {arm: [] for arm in ARMS}
            clusters = []

            def value(row):
                if metric == "ttft_s":
                    return row["ttft_s"]
                return (row["latency_s"] - row["ttft_s"]) / (row["output_tokens"] - 1)

            for case in range(10):
                ratios = []
                for rep in REPETITIONS:
                    measured = {
                        arm: value(indexed[(length, f"n{length}-s{case}", rep, arm)])
                        for arm in ARMS
                    }
                    for arm in ARMS:
                        arms[arm].append(measured[arm])
                    ratio = measured["candidate"] / measured["baseline"]
                    if not positive(ratio):
                        output["errors"].append("nonfinite_or_underflowed_ratio")
                        output["metrics"] = []
                        return output
                    ratios.append(ratio)
                clusters.append(ratios)
            ratios = [ratio for cluster in clusters for ratio in cluster]
            primary = median(ratios)
            upper = quantile(
                [median([ratio for i in sample for ratio in clusters[i]]) for sample in samples],
                0.95,
            )
            verdict = "FAIL" if primary > LIMIT else ("INCONCLUSIVE" if upper > LIMIT else "PASS")
            output["metrics"].append(
                {
                    "input_tokens": length,
                    "metric": metric,
                    "paired_ratios_by_input": clusters,
                    "median_paired_ratio": primary,
                    "paired_ratio_p10": quantile(ratios, 0.1),
                    "paired_ratio_p90": quantile(ratios, 0.9),
                    "upper_one_sided_95": upper,
                    "limit": LIMIT,
                    "proposed_metric_verdict": verdict,
                    "arms": {
                        arm: {
                            "median": median(values),
                            "p10": quantile(values, 0.1),
                            "p90": quantile(values, 0.9),
                        }
                        for arm, values in arms.items()
                    },
                }
            )
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records", type=Path)
    args = parser.parse_args()
    try:
        result = summarize(parse_records(args.records.read_text()))
    except (ValueError, OSError) as error:
        result = {
            "campaign_verdict": "INCONCLUSIVE",
            "activated": False,
            "metrics": [],
            "errors": [type(error).__name__ + ":invalid_input"],
        }
    print(json.dumps(result, indent=2, allow_nan=False))
    return int(bool(result["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
