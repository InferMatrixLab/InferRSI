"""Derive this pilot's summary/index from its unchanged published snapshot.

This is a projection of retained records, not an experiment controller. It
cannot enumerate missing private trials or supply their missing measurements.
"""

import argparse
import json
import math
import statistics
from collections import Counter
from pathlib import Path

SNAPSHOT = "dec7a734f27215092f62728f78b98fe26cd58ba2"
ARTIFACT_ID = "minicpm-seedtts-dec7a734-v1"
TOLERANCE = 1e-12


def require(condition, message):
    if not condition:
        raise ValueError(message)


def same(actual, expected, location="root"):
    """Exact structure/counts/identities, absolute 1e-12 for finite floats."""
    if isinstance(expected, float):
        require(
            isinstance(actual, (float, int))
            and not isinstance(actual, bool)
            and math.isfinite(actual)
            and math.isfinite(expected)
            and abs(actual - expected) <= TOLERANCE,
            f"numeric mismatch: {location}",
        )
    elif isinstance(expected, dict):
        require(
            isinstance(actual, dict) and actual.keys() == expected.keys(),
            f"key mismatch: {location}",
        )
        for key in expected:
            same(actual[key], expected[key], f"{location}/{key}")
    elif isinstance(expected, list):
        require(
            isinstance(actual, list) and len(actual) == len(expected),
            f"length mismatch: {location}",
        )
        for i, (a, b) in enumerate(zip(actual, expected)):
            same(a, b, f"{location}/{i}")
    else:
        require(
            type(actual) is type(expected) and actual == expected, f"value mismatch: {location}"
        )


def read(root, relative):
    return json.loads((root / relative).read_text())


def quality_metrics(cell):
    output = {}
    for key in (
        "quality",
        "quality_embedding_proxy",
        "quality_speaker_verification",
        "speaker_verification",
    ):
        if key not in cell:
            continue
        quality = cell[key]
        if "rows" in quality:
            values = list(quality["rows"].values())
            same(len(values), quality["count"])
            same(statistics.mean(values), quality["mean"])
            output[key] = {
                "count": len(values),
                "mean": statistics.mean(values),
                "scale": quality["scale"],
            }
        else:
            metrics = {}
            for metric, mean_key, count_key in (
                ("wer", "seed_tts_content_error_mean", "seed_tts_content_evaluated"),
                ("sim", "seed_tts_sim_mean", "seed_tts_sim_evaluated"),
                ("utmos", "seed_tts_utmos_mean", "seed_tts_utmos_evaluated"),
            ):
                if mean_key not in quality:
                    continue
                values = [
                    row[metric]
                    for row in quality.get("seed_tts_wer_eval_items", [])
                    if isinstance(row.get(metric), (int, float))
                ]
                if values:
                    same(len(values), quality[count_key])
                    same(statistics.mean(values), quality[mean_key])
                metrics[metric] = {
                    "mean": quality[mean_key],
                    "count": quality[count_key],
                    "basis": "per_item" if values else "archived_aggregate",
                }
            output[key] = metrics
    return output


def generate(root):
    trials, groups, sources = [], [], {}

    def add(path, pointer, name, kind, status, conclusion, **fields):
        ident = f"{path}#{pointer}"
        trials.append(
            {
                "trial_id": ident,
                "artifact_id": ARTIFACT_ID,
                "record": {"path": path, "pointer": pointer},
                "name": name,
                "kind": kind,
                "execution_status": status,
                "conclusion": conclusion,
                **fields,
            }
        )

    def service(path, pointer, variant, conclusion="INCONCLUSIVE", interrupted=False):
        grouped = {}
        for index, cell in enumerate(variant["cells"]):
            label = cell["cell"]
            concurrency, repeat = map(int, label[1:].split("-k"))
            rows = cell.get("requests")
            basis = "archived_aggregate"
            if rows is not None:
                same(len(rows), cell["n_requests"])
                require(len({r["request_id"] for r in rows}) == len(rows), "duplicate request")
                same(sum(not r["ok"] for r in rows), cell["n_failed"])
                same(statistics.mean(r["rtf"] for r in rows), cell["rtf_mean"])
                basis = "per_request"
            failed = cell["n_failed"]
            status = (
                "interrupted" if interrupted and failed else "failed" if failed else "completed"
            )
            add(
                path,
                f"{pointer}/cells/{index}",
                f"{variant['name']}/{label}",
                "service",
                status,
                conclusion,
                concurrency=concurrency,
                repetition=repeat,
                requests=cell["n_requests"],
                failed=failed,
                metric_basis=basis,
                eligibility="excluded_interrupted_run" if interrupted else "development_only",
            )
            grouped.setdefault(concurrency, []).append((cell, quality_metrics(cell)))
        for concurrency, cells in sorted(grouped.items()):
            means = [c["rtf_mean"] for c, _ in cells]
            groups.append(
                {
                    "source": path,
                    "variant": variant["name"],
                    "concurrency": concurrency,
                    "repetitions": len(cells),
                    "requests": sum(c["n_requests"] for c, _ in cells),
                    "failed": sum(c["n_failed"] for c, _ in cells),
                    "eligible_for_comparison": not interrupted
                    and not any(c["n_failed"] for c, _ in cells),
                    "rtf": {
                        "mean": statistics.mean(means),
                        "min": min(means),
                        "max": max(means),
                        "stdev": statistics.stdev(means) if len(means) > 1 else None,
                        "per_repetition": means,
                    },
                    "quality": {c["cell"]: q for c, q in cells if q},
                    "configuration": {k: v for k, v in variant.items() if k != "cells"},
                }
            )

    for file in sorted((root / "results").glob("service*development.json")):
        path = file.relative_to(root).as_posix()
        data = read(root, path)
        sources[path] = {
            k: data[k]
            for k in (
                "scope",
                "protocol",
                "hardware",
                "hardware_group",
                "shared_host",
                "limitations",
                "comparison_limit",
                "comparison_reference",
            )
            if k in data
        }
        for index, variant in enumerate(data.get("variants", [data])):
            # The phase-15 wrapper is both the source record and its single variant.
            item = (
                variant
                if "variants" in data
                else {
                    k: variant[k]
                    for k in ("name", "cells", "source_tree_sha256", "config_sha256", "treatment")
                    if k in variant
                }
            )
            service(path, f"/variants/{index}" if "variants" in data else "", item)
        for name, reason in data.get("pruned", {}).items():
            add(path, f"/pruned/{name}", name, "proposal", "not_run", reason)
        for key in (
            "component",
            "real_weight_component",
            "setup_diagnostic",
            "cpu_reference_checks",
            "configured_setup_cost_diagnostic",
            "async-history_gpu_check",
            "batched-history_gpu_check",
            "control_waveform_stability",
            "treatment_waveform_comparison",
            "isolated_cpu_diagnostic",
            "repeat_quality_reference_c32_k1",
        ):
            if key not in data:
                continue
            value = data[key]
            # Shape/config cells are trials; per-utterance waveform comparisons are samples.
            if key == "component" and "cells" in value:
                for index, cell in enumerate(value["cells"]):
                    add(
                        path,
                        f"/{key}/cells/{index}",
                        f"{file.stem}/{key}/{index}",
                        "diagnostic",
                        "completed",
                        "component_only",
                        configuration=cell,
                    )
            else:
                add(
                    path,
                    f"/{key}",
                    f"{file.stem}/{key}",
                    "diagnostic",
                    "completed",
                    value.get("scope", "diagnostic_only"),
                )

    path = "results/replica4-interrupted.json"
    data = read(root, path)
    sources[path] = {k: v for k, v in data.items() if k != "cells"}
    service(path, "", {"name": data["variant"], "cells": data["cells"]}, data["reason"], True)
    path = "results/hift-service-precision-diagnostic.json"
    data = read(root, path)
    sources[path] = {k: data[k] for k in ("scope", "reason", "limitations")}
    for index, variant in enumerate(data["service_controls"]):
        service(path, f"/service_controls/{index}", variant)
    for index, cell in enumerate(data["configured_precision_component"]["cells"]):
        add(
            path,
            f"/configured_precision_component/cells/{index}",
            f"hift/{index}",
            "diagnostic",
            "completed",
            "no_service_gain",
            configuration=cell,
        )
    add(path, "/reason", "hift-tf32-treatment", "proposal", "not_run", data["reason"])
    path = "results/dependency-audit.json"
    data = read(root, path)
    for index, name in enumerate(data["excluded_screens"]):
        add(
            path,
            f"/excluded_screens/{index}",
            name,
            "excluded_screen",
            "not_recorded",
            data["reason"],
            availability="Raw measurements were never in this public snapshot.",
        )

    component = {}
    for phase in ("s3-round", "s3-final"):
        scores = {"baseline": [], "candidate": []}
        for file in sorted((root / "results" / phase / "execution").glob("*/result.json")):
            path = file.relative_to(root).as_posix()
            data = read(root, path)
            if "latency_ms" in data:
                same(statistics.median(data["samples_ms"]), data["latency_ms"])
                scores[file.parent.name.rsplit("-", 1)[1]].append(data["latency_ms"])
            add(
                path,
                "",
                f"{phase}/{file.parent.name}",
                "component",
                "completed",
                "component_only",
                result={k: v for k, v in data.items() if k != "samples_ms"},
            )
        assessment = read(root, f"results/{phase}/assessment.json")
        same(scores["baseline"], assessment["metrics"]["samples"]["baseline"])
        same(scores["candidate"], assessment["metrics"]["samples"]["candidate"])
        same(statistics.median(scores["baseline"]), assessment["baseline_score"])
        same(statistics.median(scores["candidate"]), assessment["score"])
        same(
            100 * (1 - assessment["score"] / assessment["baseline_score"]),
            assessment["improvement_pct"],
        )
        component[phase] = {
            k: assessment[k]
            for k in ("verdict", "scope", "baseline_score", "score", "improvement_pct", "metrics")
        }

    ids = [t["trial_id"] for t in trials]
    require(len(ids) == len(set(ids)), "duplicate trial IDs")
    summary = {
        "snapshot_revision": SNAPSHOT,
        "artifact_id": ARTIFACT_ID,
        "service_verdict": "INCONCLUSIVE",
        "qualification": False,
        "coverage": {
            "trial_records": len(trials),
            "by_kind": dict(Counter(t["kind"] for t in trials)),
            "by_status": dict(Counter(t["execution_status"] for t in trials)),
            "scope": (
                "Every retained service cell, managed component execution, named "
                "diagnostic/proposal and excluded screen in the dec7a734 public result records. "
                "Per-request samples are not trials. No completeness claim for unarchived "
                "private runs or logs."
            ),
        },
        "metric_definitions": {
            "request_rtf": "(last unique-audio arrival - dispatch) / delivered duration",
            "cell_rtf": "Unweighted mean of per-request RTFs; terminal completion is separate.",
            "group_rtf": (
                "Mean/min/max/sample stdev of the recorded cell means; "
                "per-repetition values retained."
            ),
            "repetition_scope": (
                "Two tuning repetitions in one server; not fresh-server uncertainty."
            ),
            "quality": (
                "WER, embedding-cosine SIM and UTMOS; WavLM speaker verification is separately "
                "labelled. Descriptive, not non-inferiority."
            ),
        },
        "component": component,
        "sources": sources,
        "service_groups": groups,
    }
    return summary, trials


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    summary, trials = generate(args.snapshot)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (args.output / "trials.jsonl").write_text("".join(json.dumps(row) + "\n" for row in trials))


if __name__ == "__main__":
    main()
