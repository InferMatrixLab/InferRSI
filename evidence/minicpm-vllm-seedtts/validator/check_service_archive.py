"""CPU-only retrospective archive checks; not the frozen campaign evaluator.

Requires NumPy and PyYAML. Checks published projections, not external WAVs,
model weights, full traces, source execution or service qualification.
"""

import hashlib
import json
import math
import posixpath
import statistics
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]


def read(relative):
    return json.loads((ROOT / relative).read_text())


def digest(content):
    return hashlib.sha256(content).hexdigest()


def check():
    archives = {
        path.name: json.loads(path.read_text())
        for path in sorted((ROOT / "results").glob("service*development.json"))
    }
    original = {}
    for name, data in archives.items():
        assert data["verdict"] == "INCONCLUSIVE"
        for variant in data.get("variants", [data]):
            for cell in variant["cells"]:
                key = (name, variant["name"], cell["cell"])
                assert key not in original
                original[key] = cell

    timing = read("results/service-timing.json")
    assert timing["columns"] == [
        "request_id",
        "t_dispatch",
        "t_last_unique_audio",
        "t_complete",
        "unique_samples",
        "sample_rate",
    ]
    seen, trace_hashes = set(), {}
    requests = 0
    completion_differs = 0
    for cell in timing["cells"]:
        key = (cell["archive"], cell["variant"], cell["cell"])
        assert key not in seen
        seen.add(key)
        trace_hashes[(cell["variant"], cell["cell"])] = cell["source_traces_sha256"]
        old = original[key]
        recorded = {r["request_id"]: r for r in old["requests"]}
        assert len(recorded) == len(old["requests"]) == old["n_requests"]
        assert len(cell["rows"]) == len(recorded)
        assert {r[0] for r in cell["rows"]} == set(recorded)
        rtfs = []
        for ident, start, last, complete, samples, rate in cell["rows"]:
            assert all(math.isfinite(n) for n in (start, last, complete, samples, rate))
            assert start <= last <= complete and samples > 0 and rate > 0
            row = recorded[ident]
            duration = samples / rate
            rtf = (last - start) / duration
            assert duration == row["duration_s"]
            assert math.isclose(complete - start, row["e2e_s"], rel_tol=0, abs_tol=1e-12)
            assert math.isclose(rtf, row["rtf"], rel_tol=0, abs_tol=1e-12)
            completion_differs += abs(row["e2e_s"] / duration - rtf) > 1e-6
            rtfs.append(rtf)
        assert math.isclose(statistics.mean(rtfs), old["rtf_mean"], rel_tol=0, abs_tol=1e-12)
        assert sum(not row["ok"] for row in recorded.values()) == old["n_failed"]
        requests += len(rtfs)
    assert seen == set(original)

    provenance = read("plan/service-review-provenance.json")
    configs = read("plan/service-phase1314-config-chains.json")["files"]
    configs.update(provenance["config_files"])
    for config in configs.values():
        assert digest(config["content"].encode()) == config["sha256"]
    source = provenance["omni_source"]
    assert digest((ROOT / source["patch"]).read_bytes()) == source["patch_sha256"]
    for name, arm in provenance["phase5_arms"].items():
        if name == "engine-paired-phase5":
            continue
        assert arm["source_tree_sha256"] == source["source_tree_sha256"]
        chain = arm["config_chain_leaf_to_root"]
        assert configs[chain[0]]["sha256"] == arm["config_sha256"]
        for index, path in enumerate(chain):
            parent = yaml.safe_load(configs[path]["content"]).get("base_config")
            if index + 1 == len(chain):
                assert parent is None
            else:
                assert (
                    posixpath.normpath(posixpath.join(posixpath.dirname(path), parent))
                    == chain[index + 1]
                )
    for name, control in provenance["engine_controls"].items():
        assert configs[control["config_path"]]["sha256"] == control["config_sha256"]
        data = archives[Path(control["archive"]).name]
        old = next(v for v in data["variants"] if v["name"] == name)
        if "source_tree_sha256" in old:
            assert old["source_tree_sha256"] == control["source_tree_sha256"]
        assert control["source_tree_sha256"] == provenance["engine_source"]["source_tree_sha256"]

    quality = read("results/service-quality-reference.json")
    phase6 = archives["service-phase6-development.json"]
    uncertainty = phase6["quality_uncertainty"]
    assert uncertainty["reference"] == "clean-k8"
    candidate = next(v for v in phase6["variants"] if v["name"] == uncertainty["candidate"])
    rng = np.random.default_rng(uncertainty["seed"])
    for concurrency in (1, 16, 32):
        reference = quality["clean_k8_cells"][str(concurrency)]
        name = f"c{concurrency}-k0"
        assert reference["run"] == "clean-k8" and reference["cell"] == name
        original_cell = original[("service-development.json", "clean-k8", name)]
        assert reference["rtf_mean"] == original_cell["rtf_mean"]
        base_rows = reference["quality"]["seed_tts_wer_eval_items"]
        candidate_cell = next(c for c in candidate["cells"] if c["cell"] == name)
        candidate_rows = candidate_cell["quality"]["seed_tts_wer_eval_items"]
        baseline = {r["utterance_id"]: r for r in base_rows}
        treatment = {r["utterance_id"]: r for r in candidate_rows}
        assert set(baseline) == set(treatment) == set(reference["wav_sha256"])
        assert set(baseline) == {r["request_id"] for r in original_cell["requests"]}
        assert len(baseline) == len(base_rows) == len(candidate_rows) == 64
        # Original capture order; one generator across C1, C16, C32. Within
        # each concurrency all three metrics share the same paired draws.
        ids = list(baseline)
        indices = rng.integers(0, len(ids), size=(uncertainty["replicates"], len(ids)))
        for metric in ("wer", "sim", "utmos"):
            direction = -1 if metric == "wer" else 1
            delta = np.array(
                [direction * (treatment[i][metric] - baseline[i][metric]) for i in ids]
            )
            expected = uncertainty["cells"][str(concurrency)][metric]
            assert math.isclose(
                delta.mean(), expected["improvement_mean"], rel_tol=0, abs_tol=1e-12
            )
            interval = np.percentile(delta[indices].mean(1), [2.5, 97.5])
            assert np.allclose(interval, expected["percentile_95_interval"], rtol=0, atol=1e-12)

    sv = archives["service-phase78-development.json"]["speaker_verification_reference"]
    assert set(quality["speaker_verification_runs"]) == set(sv)
    for name, cells in quality["speaker_verification_runs"].items():
        assert set(cells) == set(sv[name])
        for concurrency, capture in cells.items():
            assert capture["run"] == name and capture["cell"] == f"c{concurrency}-k0"
            assert capture["source_traces_sha256"] == trace_hashes[(name, capture["cell"])]
            scores = sv[name][concurrency]
            assert set(capture["wav_sha256"]) == set(scores["rows"])
            assert len(scores["rows"]) == scores["count"] == 64
            assert math.isclose(
                statistics.mean(scores["rows"].values()), scores["mean"], rel_tol=0, abs_tol=1e-12
            )
            assert (
                digest((json.dumps(scores, indent=2) + "\n").encode())
                == capture["quality_sv_sha256"]
            )

    return {
        "service_cells": len(seen),
        "request_timings_recomputed": requests,
        "e2e_over_duration_differs_from_rtf": completion_differs,
        "config_files_verified": len(configs),
        "phase5_source_patch_hash_verified": True,
        "phase6_bootstrap_intervals_reproduced": 9,
        "speaker_verification_runs_traced": len(sv),
        "campaign_verdict": "INCONCLUSIVE",
        "limits": "No GPU rerun, external audio/model verification or service qualification.",
    }


if __name__ == "__main__":
    print(json.dumps(check(), indent=2))
