import json
import shutil
import subprocess

import pytest

from inferrsi.benchmark.validators.video import (
    METRICS,
    Clip,
    MediaContract,
    VideoQualityGate,
    compare_videos,
    load_clip,
    measure_pair,
    summarize,
)
from inferrsi.harness.evaluator import inspect_project_step

CONTRACT = MediaContract(width=48, height=32, fps="24/1", frames=8)
CONTROL = {"precision": "mxfp8", "parallel_layout": "usp4", "inputs": "prompt-0"}
# Test bounds only; campaigns freeze their own.
GATE = VideoQualityGate(
    matched_controls=("precision", "parallel_layout", "inputs"),
    sample_bounds={"sharpness_ratio": (0.7, 1.4), "temporal_ratio": (0.7, 1.4),
                   "luma_delta": (-10, 10)},
    aggregate_bounds={"sharpness_ratio": (0.9, 1.1), "temporal_ratio": (0.9, 1.1),
                      "luma_delta": (-3, 3)},
)


def measured(sample_id, sharpness=1.0, temporal=1.0, luma=0.0):
    return {"id": sample_id, "status": "MEASURED", "reasons": [],
            "metrics": {"sharpness_ratio": sharpness, "temporal_ratio": temporal,
                        "luma_delta": luma}}


def missing(sample_id):
    return {"id": sample_id, "status": "INCONCLUSIVE", "reasons": ["reference_missing"]}


@pytest.mark.parametrize("change", [
    {"matched_controls": ()},
    {"matched_controls": ["precision"]},
    {"matched_controls": ("precision", "precision")},
    {"sample_bounds": {"sharpness_ratio": (0.7, 1.4), "temporal_ratio": (0.7, 1.4)}},
    {"sample_bounds": {**GATE.sample_bounds, "luma_delta": (5, -5)}},
    {"aggregate_bounds": {**GATE.aggregate_bounds, "sharpness_ratio": (0.9, float("inf"))}},
    {"aggregate_bounds": {**GATE.aggregate_bounds, "temporal_ratio": (True, 1.1)}},
])
def test_gate_requires_explicit_two_sided_bounds_for_every_metric(change):
    fields = {"matched_controls": GATE.matched_controls, "sample_bounds": GATE.sample_bounds,
              "aggregate_bounds": GATE.aggregate_bounds, **change}
    with pytest.raises(ValueError):
        VideoQualityGate(**fields)


@pytest.mark.parametrize("fields", [
    {"width": 0, "height": 32, "fps": "24/1", "frames": 8},
    {"width": 48, "height": 32, "fps": "24/1", "frames": 1},
    {"width": 48, "height": 32, "fps": "0/1", "frames": 8},
    {"width": 48, "height": 32, "fps": 24, "frames": 8},
])
def test_media_contract_rejects_invalid_geometry_timing_and_length(fields):
    with pytest.raises(ValueError):
        MediaContract(**fields)


def test_samples_inside_both_levels_pass():
    report = summarize([measured("a", 1.05, 0.95, 1.0), measured("b", 0.97, 1.02, -0.5)],
                       CONTRACT, GATE)
    assert report["verdict"] == "PASS" and report["passed"] is True
    assert [s["status"] for s in report["samples"]] == ["PASS", "PASS"]
    assert report["aggregate"]["median"]["sharpness_ratio"] == pytest.approx(1.01)
    assert report["reasons"] == []


@pytest.mark.parametrize("metric, value", [
    ("sharpness_ratio", 0.5),  # blur
    ("sharpness_ratio", 1.8),  # noise or oversharpening
    ("temporal_ratio", 0.2),   # frozen motion
    ("temporal_ratio", 2.5),   # flicker or reordered frames
    ("luma_delta", 25.0),      # brightness shift
    ("luma_delta", -25.0),
])
def test_a_sample_outside_either_side_of_its_bounds_is_a_severe_defect(metric, value):
    values = {"sharpness": 1.0, "temporal": 1.0, "luma": 0.0}
    values[{"sharpness_ratio": "sharpness", "temporal_ratio": "temporal",
            "luma_delta": "luma"}[metric]] = value
    report = summarize([measured("ok"), measured("bad", **values)], CONTRACT, GATE)
    assert report["verdict"] == "FAIL" and report["passed"] is False
    assert [s["status"] for s in report["samples"]] == ["PASS", "FAIL"]
    assert report["reasons"][0].startswith("bad: " + metric)


def test_aggregate_bounds_fail_a_set_whose_samples_each_pass():
    # Every sample stays inside the wide per-sample bounds; the median does not.
    report = summarize([measured(name, sharpness=1.25) for name in "abc"], CONTRACT, GATE)
    assert [s["status"] for s in report["samples"]] == ["PASS"] * 3
    assert report["verdict"] == "FAIL"
    assert report["reasons"] == ["aggregate: sharpness_ratio 1.25 outside [0.9, 1.1]"]


def test_missing_evidence_is_inconclusive_and_never_a_failure():
    report = summarize([measured("a"), missing("b")], CONTRACT, GATE)
    assert report["verdict"] == "INCONCLUSIVE" and report["passed"] is None
    assert report["aggregate"] is None
    assert report["reasons"] == ["b: reference_missing"]


def test_an_observed_defect_fails_even_when_another_sample_lacks_evidence():
    report = summarize([measured("a", sharpness=0.4), missing("b")], CONTRACT, GATE)
    assert report["verdict"] == "FAIL" and report["passed"] is False


@pytest.mark.parametrize("records", [
    [],
    [measured("a"), measured("a")],
    [{**measured("a"), "metrics": {"sharpness_ratio": 1.0, "temporal_ratio": 1.0}}],
    [measured("a", luma=float("nan"))],
    [{"id": "a", "status": "INCONCLUSIVE", "reasons": []}],
    [{"id": "a", "status": "PASS", "reasons": ["x"]}],
])
def test_summary_rejects_malformed_measurements(records):
    with pytest.raises(ValueError):
        summarize(records, CONTRACT, GATE)


@pytest.mark.parametrize("records, status", [
    ([measured("a")], "completed"),
    ([measured("a", sharpness=0.5)], "candidate_failure"),
    ([missing("a")], "infrastructure_failure"),
])
def test_report_maps_onto_the_project_harness_quality_branches(tmp_path, records, status):
    # A project campaign sets quality_key to "passed"; null must not read as a rejection.
    report = summarize(records, CONTRACT, GATE)
    result = tmp_path / "execution" / "quality-candidate" / "result.json"
    result.parent.mkdir(parents=True)
    result.write_text(json.dumps(report, allow_nan=False), encoding="utf-8")
    checked = inspect_project_step(
        tmp_path, {"quality_key": "passed", "metric_key": "unused"},
        {"id": "quality-candidate", "phase": "quality", "side": "candidate"},
        {"status": "completed"},
    )
    assert checked["status"] == status
    if status == "infrastructure_failure":
        assert checked["reason"] == "missing_boolean_quality_evidence"


@pytest.mark.parametrize("change", [
    {"reference": {"path": "r.mkv", "control": CONTROL}},
    {"candidate": {"path": "c.mkv"}},
    {"candidate": {"path": "c.mkv", "control": CONTROL, "sha256": "abc"}},
    {"id": ""},
])
def test_compare_rejects_malformed_sample_entries(change):
    sample = {"id": "a", "reference": {"path": "r.mkv", "control": CONTROL, "sha256": "0" * 64},
              "candidate": {"path": "c.mkv", "control": CONTROL}, **change}
    with pytest.raises(ValueError):
        compare_videos([sample], CONTRACT, GATE)


def test_compare_reports_absent_media_as_inconclusive(tmp_path):
    sample = {"id": "a",
              "reference": {"path": str(tmp_path / "r.mkv"), "control": CONTROL,
                            "sha256": "0" * 64},
              "candidate": {"path": str(tmp_path / "c.mkv"), "control": CONTROL}}
    report = compare_videos([sample], CONTRACT, GATE)
    assert report["verdict"] == "INCONCLUSIVE" and report["passed"] is None
    assert report["samples"][0]["reasons"] == ["reference_missing", "candidate_missing"]


# Synthetic clips: a textured pattern moving one pixel per frame.
def _pattern(np):
    y, x = np.mgrid[0:CONTRACT.height, 0:CONTRACT.width]
    return 128 + 50 * np.sin(x / 2.5) * np.cos(y / 3.5) + 20 * np.sin((x + 2 * y) / 1.7)


def _frames(np, shift=0):
    base = _pattern(np)
    return np.stack([np.roll(base, t + shift, axis=1) for t in range(CONTRACT.frames)])


def _u8(np, frames):
    return np.clip(np.rint(frames), 0, 255).astype(np.uint8)


def _blur(np, frames, passes=3):
    for _ in range(passes):
        frames = (frames + np.roll(frames, 1, 1) + np.roll(frames, -1, 1)
                  + np.roll(frames, 1, 2) + np.roll(frames, -1, 2)) / 5
    return frames


def _clip(luma, control=CONTROL, fps="24/1"):
    return Clip(luma, fps, dict(control))


def _variants(np):
    frames = _frames(np)
    rng = np.random.default_rng(0)
    flicker = frames + np.where(np.arange(CONTRACT.frames) % 2, 15, -15)[:, None, None]
    return {
        "identical": frames,
        "trajectory_drift": _frames(np, shift=3),
        "blurred": _blur(np, frames),
        "noisy": frames + rng.normal(0, 8, frames.shape),
        "flicker": flicker,
        "reordered": frames[[0, 4, 1, 6, 2, 7, 3, 5]],
        "frozen": np.repeat(frames[:1], CONTRACT.frames, axis=0),
        "brighter": frames + 25,
    }


def test_luma_statistics_separate_drift_from_blur_where_psnr_does_not():
    np = pytest.importorskip("numpy")
    reference = _clip(_u8(np, _frames(np)))
    variants = _variants(np)
    results = {name: measure_pair(name, reference, _clip(_u8(np, frames)), CONTRACT, GATE)
               for name, frames in variants.items()}
    # The #364 inversion: PSNR ranks the blurred clip above the sharp drifted one.
    assert results["blurred"]["diagnostics"]["psnr_db"] > (
        results["trajectory_drift"]["diagnostics"]["psnr_db"] + 2)
    report = summarize(list(results.values()), CONTRACT, GATE)
    statuses = {sample["id"]: sample["status"] for sample in report["samples"]}
    assert statuses == {"identical": "PASS", "trajectory_drift": "PASS", "blurred": "FAIL",
                        "noisy": "FAIL", "flicker": "FAIL", "reordered": "FAIL",
                        "frozen": "FAIL", "brighter": "FAIL"}
    failed = {sample["id"]: sample["reasons"][0].split()[0] for sample in report["samples"]
              if sample["status"] == "FAIL"}
    assert failed == {"blurred": "sharpness_ratio", "noisy": "sharpness_ratio",
                      "flicker": "temporal_ratio", "reordered": "temporal_ratio",
                      "frozen": "temporal_ratio", "brighter": "luma_delta"}
    assert results["identical"]["metrics"] == {"sharpness_ratio": 1.0, "temporal_ratio": 1.0,
                                               "luma_delta": 0.0}


def test_media_contract_and_control_checks_precede_quality():
    np = pytest.importorskip("numpy")
    frames = _u8(np, _frames(np))
    reference = _clip(frames)
    cases = {
        "dropped_frame": (_clip(frames[:-1]), "FAIL", "candidate_media_contract: frames 7 != 8"),
        "wrong_fps": (_clip(frames, fps="25/1"), "FAIL", "candidate_media_contract: fps"),
        "wrong_size": (_clip(frames[:, :, :40]), "FAIL", "candidate_media_contract: width"),
        "layout_mismatch": (_clip(frames, {**CONTROL, "parallel_layout": "tp4"}),
                            "INCONCLUSIVE", "control_mismatch: parallel_layout"),
        "control_missing": (_clip(frames, {"precision": "mxfp8", "parallel_layout": "usp4"}),
                            "INCONCLUSIVE", "control_missing: inputs"),
    }
    for name, (candidate, status, reason) in cases.items():
        result = measure_pair(name, reference, candidate, CONTRACT, GATE)
        assert result["status"] == status, name
        assert result["reasons"][0].startswith(reason), name
        assert "metrics" not in result
    flat = _clip(np.full(frames.shape, 90, dtype=np.uint8))
    result = measure_pair("flat_reference", flat, reference, CONTRACT, GATE)
    assert result["status"] == "INCONCLUSIVE"
    assert result["reasons"] == ["reference_zero_sharpness", "reference_zero_temporal"]


def _encode(path, luma, fps="24"):
    frames, height, width = luma.shape
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray",
         "-s", f"{width}x{height}", "-r", fps, "-i", "-", "-c:v", "ffv1", str(path)],
        input=luma.tobytes(), check=True, capture_output=True,
    )


def test_decoded_files_are_hash_checked_and_judged_end_to_end(tmp_path):
    np = pytest.importorskip("numpy")
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        pytest.skip("ffmpeg and ffprobe are required to encode and decode the fixtures")
    frames = _u8(np, _frames(np))
    paths = {name: tmp_path / f"{name}.mkv" for name in ("reference", "drift", "fps25")}
    _encode(paths["reference"], frames)
    _encode(paths["drift"], _u8(np, _frames(np, shift=3)))
    _encode(paths["fps25"], frames, fps="25")
    decoded = load_clip(paths["reference"], CONTROL)
    assert decoded.fps == "24/1" and np.array_equal(decoded.luma, frames)

    def sample(name, candidate, reference_hash=decoded.sha256):
        return {"id": name,
                "reference": {"path": str(paths["reference"]), "control": CONTROL,
                              "sha256": reference_hash},
                "candidate": {"path": str(candidate), "control": CONTROL}}

    report = compare_videos([sample("drift", paths["drift"])], CONTRACT, GATE)
    assert report["verdict"] == "PASS" and report["decoder"].startswith("ffmpeg version")
    report = compare_videos(
        [sample("drift", paths["drift"]), sample("stale", paths["drift"], "0" * 64),
         sample("fps25", paths["fps25"]), sample("absent", tmp_path / "absent.mkv")],
        CONTRACT, GATE)
    reasons = {s["id"]: (s["status"], s["reasons"][:1]) for s in report["samples"]}
    assert reasons == {
        "drift": ("PASS", []),
        "stale": ("INCONCLUSIVE", ["reference_hash_mismatch"]),
        "fps25": ("FAIL", ["candidate_media_contract: fps 25/1 != 24/1"]),
        "absent": ("INCONCLUSIVE", ["candidate_missing"]),
    }
    assert report["verdict"] == "FAIL" and report["aggregate"] is None
    assert set(report["samples"][0]["metrics"]) == set(METRICS)
    json.dumps(report, allow_nan=False)
