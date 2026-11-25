"""Read-only replay of the historical observer export. Never invokes its executables."""

import re
from pathlib import Path
from statistics import median

import pytest

from inferrsi.harness import project
from inferrsi.harness.artifact_primitives import sha256

from .audit import image_requests, inside, read


@pytest.fixture(scope="module")
def archive(pytestconfig):
    location = pytestconfig.getoption("e2e_archived_evidence")
    if location is None:
        pytest.skip("Select a retained #479 actor evidence directory")
    return Path(location)


@pytest.fixture(scope="module")
def replay(pytestconfig):
    location = pytestconfig.getoption("e2e_archived_retest")
    if location is None:
        pytest.skip("Select a retained #479 independent attempt")
    return Path(location)


def sample_groups(parent, steps, workload_sha):
    """Recompute each recorded median and compare every decoded image by seed."""
    samples = {"baseline": [], "candidate": []}
    reference_pixels = None
    count = 0
    for step in steps:
        directory = parent / step
        result = read(directory / "result.json")
        assert result["workload_sha256"] == workload_sha, step
        pixels = image_requests(directory, result)
        if reference_pixels is None:
            reference_pixels = pixels
        assert pixels == reference_pixels, f"RGBA comparison differs for {step}"
        if step.startswith("measurement-"):
            samples[step.split("-")[-1]].append(result["median_ms"])
        count += len(pixels)
    return samples, count, reference_pixels


def test_archived_rounds_and_session_final(archive):
    plan = read(archive / "plan/actor-plan.json")
    state = read(archive / "results/actor-state.json")
    settings = plan["evaluation_settings"]
    assert settings["direction"] == "minimize"
    expected = [step["id"] for step in project.steps(settings)]
    workload = plan["frozen_files"]["protocol/workload.json"]
    best = plan["baseline_sha256"]
    best_score = None
    seen = {best}
    assert len(state["rounds"]) >= 2
    reference_pixels = None
    for index, record in enumerate([*state["rounds"], state["final"]], start=1):
        final = index > len(state["rounds"])
        folder = "actor-final" if final else f"round-{index:02d}"
        execution = record["execution"]
        assert [step["id"] for step in execution["steps"]] == expected, folder
        assert all(step["returncode"] == 0 for step in execution["steps"]), folder
        identities = {
            "baseline": plan["baseline_sha256"],
            "candidate": record["candidate_sha256"],
        }
        assert [check["step"] for check in execution["source_checks"]] == expected
        for check in execution["source_checks"]:
            assert check["verified"] and check["actual"] == check["expected"] == identities
        samples, _, pixels = sample_groups(
            archive / "results/actor" / folder, expected, workload
        )
        if reference_pixels is None:
            reference_pixels = pixels
        assert pixels == reference_pixels, folder
        baseline, candidate = (median(samples[arm]) for arm in ("baseline", "candidate"))
        assessment = record["assessment"]
        assert assessment["quality_passed"] is True
        assert assessment["metrics"]["samples"] == samples
        assert (assessment["baseline_score"], assessment["score"]) == (baseline, candidate)
        if final:
            assert record["candidate_sha256"] == best == state["best"]["sha256"]
            continue
        assert record["candidate_sha256"] not in seen
        seen.add(record["candidate_sha256"])
        if best_score is None:
            best_score = baseline
        gain = (1 - candidate / baseline) * 100
        if candidate < best_score and gain >= settings["min_improvement_pct"]:
            best, best_score = record["candidate_sha256"], candidate
        assert (record["best_after"]["sha256"], record["best_after"]["score"]) == (
            best,
            best_score,
        )


def test_archived_independent_measurements(replay):
    freeze = read(replay / "evaluator-freeze.json")
    seal = read(replay / "sealed-source.json")
    summary = read(replay / "independent-result.json")
    assert (
        freeze["baseline_revision"] == summary["baseline_revision"] == seal["baseline_revision"]
    )
    assert summary["candidate_id"] == seal["candidate_id"]
    assert summary["source_sha256"] == seal["source_sha256"]
    assert sha256(replay / "candidate.patch") == seal["patch_sha256"]
    assert freeze["validator_sha256"] == summary["validator_sha256"] == seal["validator_sha256"]
    for name in ("benchmark.py", "model-manifest.json", "workload.json"):
        assert sha256(replay / "protocol" / name) == freeze["validator_sha256"][name]
    order = re.search(r"\b(?:AB|BA)(?:/(?:AB|BA))*\b", freeze["statistics"])
    assert order and "median of group medians" in freeze["statistics"]
    expected = ["quality-baseline", "quality-candidate"]
    for index, pair in enumerate(order.group().split("/"), start=1):
        arms = {"A": "baseline", "B": "candidate"}
        expected.extend(f"measurement-{index:03d}-{arms[arm]}" for arm in pair)
    assert [r["step"] for r in summary["execution"]] == expected
    assert [c["step"] for c in summary["source_checks"]] == expected
    for receipt, check in zip(summary["execution"], summary["source_checks"], strict=True):
        directory = replay / "results" / receipt["step"]
        assert receipt == read(directory / "receipt.json")
        assert receipt["returncode"] == 0 and receipt["result_sha256"] == sha256(
            directory / "result.json"
        )
        assert check["verified"] and check["after_execution_verified"]
        assert {arm: check[arm] for arm in ("baseline", "candidate")} == seal["source_sha256"]
    samples, count, pixels = sample_groups(
        replay / "results", expected, freeze["validator_sha256"]["workload.json"]
    )
    assert summary["samples"] == samples
    baseline, candidate = median(samples["baseline"]), median(samples["candidate"])
    assert summary["baseline_ms"] == baseline and summary["candidate_ms"] == candidate
    assert summary["latency_reduction_ms"] == pytest.approx(baseline - candidate)
    assert summary["latency_reduction_pct"] == pytest.approx(100 * (1 - candidate / baseline))
    assert summary["raw_request_timings"] == summary["decoded_pngs_verified"] == count
    assert summary["quality_pairs_passed"] == len(pixels)


def test_archived_patch_matches_selected_snapshot(archive, replay):
    """Evaluate the current exact-source requirement against the old evidence."""
    state = read(archive / "results/actor-state.json")
    seal = read(replay / "sealed-source.json")
    chosen = next(r for r in state["rounds"] if r["candidate_id"] == seal["candidate_id"])
    assert seal["candidate_attempt"] == chosen["path"] + "/candidate"
    assert (
        seal["measured_candidate_sha256"]
        == chosen["candidate_sha256"]
        == state["final"]["candidate_sha256"]
    )
    assert (
        sha256(archive / "patch/qwen21-a2.patch")
        == sha256(replay / "candidate.patch")
        == seal["patch_sha256"]
    )
    for mapping in seal["delivery_format_mapping"]:
        measured_result = read(
            archive / "results/actor/actor-final/measurement-001-candidate/result.json"
        )
        digest_fields = {
            "autoencoder_kl_qwenimage21.py": "vae_sha256",
            "qwen_image_21_transformer.py": "transformer_sha256",
            "pipeline_qwen_image_21.py": "pipeline_sha256",
        }
        measured = measured_result[digest_fields[Path(mapping["file"]).name]]
        rebuilt = sha256(inside(replay / "candidate", mapping["file"]))
        assert (measured, rebuilt) == (mapping["measured_sha256"], mapping["delivery_sha256"])
        assert rebuilt == measured, (
            f"Reconstructed {Path(mapping['file']).name} differs from the measured VAE"
        )
    assert seal["matches_actor_snapshot_bytes"] is True, (
        "The historical reconstruction receipt records a byte mismatch with the Agent snapshot."
    )
