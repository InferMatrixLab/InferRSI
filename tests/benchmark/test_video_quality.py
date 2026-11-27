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
DATASET = "video-quality-fixture-v1"


def measured(sample_id, sharpness=1.0, temporal=1.0, luma=0.0):
    return {"id": sample_id, "status": "MEASURED", "reasons": [],
            "metrics": {"sharpness_ratio": sharpness, "temporal_ratio": temporal,
                        "luma_delta": luma}}


def missing(sample_id):
    return {"id": sample_id, "status": "INCONCLUSIVE", "reasons": ["reference_missing"]}


def summary(records):
    return summarize(records, CONTRACT, GATE, dataset=DATASET)


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
    report = summary([measured("a", 1.05, 0.95, 1.0), measured("b", 0.97, 1.02, -0.5)])
    assert report["verdict"] == "PASS" and report["passed"] is True
    assert report["dataset"] == DATASET
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
    report = summary([measured("ok"), measured("bad", **values)])
    assert report["verdict"] == "FAIL" and report["passed"] is False
    assert [s["status"] for s in report["samples"]] == ["PASS", "FAIL"]
    assert report["reasons"][0].startswith("bad: " + metric)


def test_aggregate_bounds_fail_a_set_whose_samples_each_pass():
    # Every sample stays inside the wide per-sample bounds; the median does not.
    report = summary([measured(name, sharpness=1.25) for name in "abc"])
    assert [s["status"] for s in report["samples"]] == ["PASS"] * 3
    assert report["verdict"] == "FAIL"
    assert report["reasons"] == ["aggregate: sharpness_ratio 1.25 outside [0.9, 1.1]"]


def test_missing_evidence_is_inconclusive_and_never_a_failure():
    report = summary([measured("a"), missing("b")])
    assert report["verdict"] == "INCONCLUSIVE" and report["passed"] is None
    assert report["aggregate"] is None
    assert report["reasons"] == ["b: reference_missing"]


def test_an_observed_defect_fails_even_when_another_sample_lacks_evidence():
    report = summary([measured("a", sharpness=0.4), missing("b")])
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
        summary(records)


@pytest.mark.parametrize("dataset", ["", "  ", None])
def test_summary_requires_a_frozen_dataset_identity(dataset):
    with pytest.raises(ValueError):
        summarize([measured("a")], CONTRACT, GATE, dataset=dataset)


def test_gate_snapshots_bounds_so_later_edits_cannot_change_the_verdict():
    sample = {"sharpness_ratio": [0.7, 1.4], "temporal_ratio": (0.7, 1.4),
              "luma_delta": (-10, 10)}
    aggregate = dict(GATE.aggregate_bounds)
    gate = VideoQualityGate(("precision",), sample, aggregate)
    before = summarize([measured("a", sharpness=1.5)], CONTRACT, gate, dataset=DATASET)
    # Each edit alone would turn this FAIL into a PASS if the gate shared the caller's values.
    sample["sharpness_ratio"][1] = 2.0
    sample["luma_delta"] = (-100, 100)
    aggregate["sharpness_ratio"] = (0.0, 9.0)
    after = summarize([measured("a", sharpness=1.5)], CONTRACT, gate, dataset=DATASET)
    assert after == before and after["verdict"] == "FAIL"
    assert after["gate"]["sample_bounds"]["sharpness_ratio"] == [0.7, 1.4]
    assert after["gate"]["aggregate_bounds"]["sharpness_ratio"] == [0.9, 1.1]
    with pytest.raises(TypeError):
        gate.sample_bounds["sharpness_ratio"] = (0.0, 9.0)


def test_clip_snapshots_scalar_controls():
    np = pytest.importorskip("numpy")
    frames = _u8(np, _frames(np))
    control = dict(CONTROL)
    reference, candidate = Clip(frames, "24/1", control), Clip(frames, "24/1", control)
    control["precision"] = "bf16"
    result = measure_pair("a", reference, candidate, CONTRACT, GATE)
    assert result["status"] == "MEASURED" and result["controls"]["precision"] == "mxfp8"
    with pytest.raises(TypeError):
        reference.control["precision"] = "bf16"
    for bad in (["prompt-0"], float("inf"), float("-inf"), float("nan")):
        with pytest.raises(ValueError):
            Clip(frames, "24/1", {**CONTROL, "inputs": bad})


def test_a_report_with_finite_numeric_controls_is_strict_json():
    np = pytest.importorskip("numpy")
    frames = _u8(np, _frames(np))
    # An unmatched control may be null; matched ones carry finite, typed values.
    control = {**CONTROL, "cfg_scale": 7.5, "steps": 50, "tiled": False, "seed": None}
    gate = VideoQualityGate(("precision", "cfg_scale", "steps", "tiled"),
                            GATE.sample_bounds, GATE.aggregate_bounds)
    result = measure_pair("a", Clip(frames, "24/1", control), Clip(frames, "24/1", control),
                          CONTRACT, gate)
    report = summarize([result], CONTRACT, gate, dataset=DATASET)
    assert report["verdict"] == "PASS"
    assert json.loads(json.dumps(report, allow_nan=False))["samples"][0]["controls"] == {
        "precision": "mxfp8", "cfg_scale": 7.5, "steps": 50, "tiled": False}


@pytest.mark.parametrize("reference_value, candidate_value, reason", [
    (None, None, "control_missing"),        # null on both sides is not a verified match
    ("prompt-0", None, "control_missing"),
    (True, 1, "control_mismatch"),          # Python treats these as equal; JSON does not
    (1, True, "control_mismatch"),
    (1, 1.0, "control_mismatch"),
    (False, 0, "control_mismatch"),
])
def test_matched_controls_need_present_values_of_the_same_type(reference_value,
                                                               candidate_value, reason):
    np = pytest.importorskip("numpy")
    frames = _u8(np, _frames(np))
    reference = Clip(frames, "24/1", {**CONTROL, "inputs": reference_value})
    candidate = Clip(frames, "24/1", {**CONTROL, "inputs": candidate_value})
    result = measure_pair("a", reference, candidate, CONTRACT, GATE)
    assert result["status"] == "INCONCLUSIVE"
    assert result["reasons"] == [reason + ": inputs"]
    assert summarize([result], CONTRACT, GATE, dataset=DATASET)["verdict"] == "INCONCLUSIVE"


# A project campaign sets quality_key to "passed". An intake-approved campaign also
# freezes quality_benchmark to the report's dataset and may bound "passed" as a boolean.
HARNESS_SETTINGS = {
    "quality key only": {"quality_key": "passed", "metric_key": "unused"},
    "frozen benchmark": {"quality_key": "passed", "metric_key": "unused",
                         "quality_benchmark": DATASET},
    "frozen benchmark and bound": {
        "quality_key": "passed", "metric_key": "unused", "quality_benchmark": DATASET,
        "quality_bound": {"metric": "passed", "comparator": "equal", "limit": 1,
                          "unit": "boolean"}},
}


def _inspect(tmp_path, report, settings):
    result = tmp_path / "execution" / "quality-candidate" / "result.json"
    result.parent.mkdir(parents=True, exist_ok=True)
    result.write_text(json.dumps(report, allow_nan=False), encoding="utf-8")
    return inspect_project_step(
        tmp_path, settings, {"id": "quality-candidate", "phase": "quality", "side": "candidate"},
        {"status": "completed"},
    )


@pytest.mark.parametrize("settings", HARNESS_SETTINGS.values(), ids=HARNESS_SETTINGS.keys())
@pytest.mark.parametrize("records, status, reason", [
    ([measured("a")], "completed", None),
    ([measured("a", sharpness=0.5)], "candidate_failure", "candidate_check_rejected"),
    # Missing evidence must reach the missing-evidence branch, not a rejection.
    ([missing("a")], "infrastructure_failure", "missing_boolean_quality_evidence"),
])
def test_report_maps_onto_the_project_harness_quality_branches(tmp_path, settings, records,
                                                               status, reason):
    checked = _inspect(tmp_path, summary(records), settings)
    assert checked["status"] == status
    assert checked.get("reason") == reason


def test_a_report_for_another_dataset_is_rejected_by_the_frozen_benchmark(tmp_path):
    report = summarize([measured("a")], CONTRACT, GATE, dataset="another-sample-set")
    checked = _inspect(tmp_path, report, HARNESS_SETTINGS["frozen benchmark and bound"])
    assert checked["reason"] == "quality_benchmark_mismatch"


@pytest.mark.parametrize("change", [
    {"reference": {"path": "r.mkv", "control": CONTROL}},
    {"candidate": {"path": "c.mkv"}},
    {"candidate": {"path": "c.mkv", "control": CONTROL, "sha256": "abc"}},
    {"candidate": {"path": "c.mkv", "control": CONTROL, "sha256": "G" * 64}},
    {"id": ""},
])
def test_compare_rejects_malformed_sample_entries(change):
    sample = {"id": "a", "reference": {"path": "r.mkv", "control": CONTROL, "sha256": "0" * 64},
              "candidate": {"path": "c.mkv", "control": CONTROL}, **change}
    with pytest.raises(ValueError):
        compare_videos([sample], CONTRACT, GATE, dataset=DATASET)


def test_compare_rejects_duplicate_ids_and_a_missing_dataset_before_decoding(tmp_path):
    sample = {"id": "a",
              "reference": {"path": str(tmp_path / "r.mkv"), "control": CONTROL,
                            "sha256": "0" * 64},
              "candidate": {"path": str(tmp_path / "c.mkv"), "control": CONTROL}}
    with pytest.raises(ValueError, match="distinct"):
        compare_videos([sample, dict(sample)], CONTRACT, GATE, dataset=DATASET)
    # Non-finite controls could not be written as strict JSON; the plan is rejected.
    for role in ("reference", "candidate"):
        for bad in (float("inf"), float("nan"), [1]):
            entry = {**sample[role], "control": {**CONTROL, "cfg_scale": bad}}
            with pytest.raises(ValueError, match="finite number"):
                compare_videos([{**sample, role: entry}], CONTRACT, GATE, dataset=DATASET)
    with pytest.raises(ValueError, match="dataset"):
        compare_videos([sample], CONTRACT, GATE, dataset="")


def test_compare_reports_absent_media_as_inconclusive(tmp_path):
    sample = {"id": "a",
              "reference": {"path": str(tmp_path / "r.mkv"), "control": CONTROL,
                            "sha256": "0" * 64},
              "candidate": {"path": str(tmp_path / "c.mkv"), "control": CONTROL}}
    report = compare_videos([sample], CONTRACT, GATE, dataset=DATASET)
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
    report = summary(list(results.values()))
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

    report = compare_videos([sample("drift", paths["drift"])], CONTRACT, GATE, dataset=DATASET)
    assert report["verdict"] == "PASS" and report["decoder"].startswith("ffmpeg version")
    report = compare_videos(
        [sample("drift", paths["drift"]), sample("stale", paths["drift"], "0" * 64),
         sample("fps25", paths["fps25"]), sample("absent", tmp_path / "absent.mkv")],
        CONTRACT, GATE, dataset=DATASET)
    reasons = {s["id"]: (s["status"], s["reasons"][:1]) for s in report["samples"]}
    assert reasons == {
        "drift": ("PASS", []),
        "stale": ("INCONCLUSIVE", ["reference_hash_mismatch"]),
        "fps25": ("FAIL", ["candidate_media_contract: fps 25/1 != 24/1"]),
        "absent": ("INCONCLUSIVE", ["candidate_missing"]),
    }
    assert report["verdict"] == "FAIL" and report["aggregate"] is None
    assert set(report["samples"][0]["metrics"]) == set(METRICS)
    # The decoded report passes the intake-frozen benchmark check and is a rejection.
    checked = _inspect(tmp_path, report, HARNESS_SETTINGS["frozen benchmark and bound"])
    assert checked["status"] == "candidate_failure"


def _with_display_matrix(source, target, option):
    # Stream copy keeps the coded pixels and only attaches a container display matrix.
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *option, "-i", str(source),
                    "-c", "copy", str(target)], check=True, capture_output=True)


def test_a_display_matrix_is_reported_and_never_reshapes_coded_frames(tmp_path):
    np = pytest.importorskip("numpy")
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        pytest.skip("ffmpeg and ffprobe are required to encode and decode the fixtures")
    # A non-square clip: autorotation would emit 32x48 frames with the same byte count.
    frames = _u8(np, _frames(np))
    plain, rotated, flipped = (tmp_path / f"{name}.mkv" for name in ("plain", "rot", "flip"))
    _encode(plain, frames)
    _with_display_matrix(plain, rotated, ["-display_rotation", "90"])
    _with_display_matrix(plain, flipped, ["-display_hflip"])
    clips = {path.stem: load_clip(path, CONTROL) for path in (plain, rotated, flipped)}
    for clip in clips.values():
        assert clip.luma.shape == (CONTRACT.frames, CONTRACT.height, CONTRACT.width)
        assert np.array_equal(clip.luma, frames)
    assert clips["plain"].display_rotation is None
    assert clips["rot"].display_rotation == 90
    assert clips["flip"].display_rotation is not None

    def sample(name, reference, candidate):
        return {"id": name,
                "reference": {"path": str(reference), "control": CONTROL,
                              "sha256": clips[reference.stem].sha256},
                "candidate": {"path": str(candidate), "control": CONTROL}}

    report = compare_videos([sample("rotated_candidate", plain, rotated),
                             sample("flipped_candidate", plain, flipped),
                             sample("rotated_reference", rotated, plain)],
                            CONTRACT, GATE, dataset=DATASET)
    outcome = {s["id"]: (s["status"], s["reasons"][0]) for s in report["samples"]}
    assert outcome["rotated_candidate"] == (
        "FAIL", "candidate_media_contract: display matrix present (rotation 90)")
    assert outcome["flipped_candidate"][0] == "FAIL"
    assert outcome["flipped_candidate"][1].startswith(
        "candidate_media_contract: display matrix present")
    assert outcome["rotated_reference"] == (
        "INCONCLUSIVE", "reference_media_contract: display matrix present (rotation 90)")
    assert report["samples"][0]["media"]["candidate"]["display_rotation"] == 90
