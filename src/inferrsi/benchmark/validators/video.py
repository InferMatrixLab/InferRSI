# Paired quality check of diffusion video against a matched dense reference.
# Media integrity is judged before quality, every bound comes from the campaign's frozen
# plan, and pixel distance (PSNR) is only a diagnostic. NumPy is imported only when a clip
# is measured; decoding uses the ffprobe and ffmpeg executables on PATH.

import json
import math
import statistics
import subprocess
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from fractions import Fraction
from pathlib import Path
from types import MappingProxyType

from ..artifacts import sha256

METRICS = ("sharpness_ratio", "temporal_ratio", "luma_delta")
METRICS_VERSION = "inferrsi-video-quality-v1"
DEFINITIONS = {
    "luma": "first video stream decoded by ffmpeg with -noautorotate and -pix_fmt gray, "
            "8-bit values in coded frame layout; a stream with a display matrix breaks "
            "the media contract",
    "sharpness": "per frame, variance of the 4-neighbour Laplacian with edge replication; "
                 "clip value is the mean over frames",
    "temporal": "per transition, mean absolute luma difference of consecutive frames; "
                "clip value is the mean over transitions",
    "sharpness_ratio": "candidate clip sharpness / reference clip sharpness",
    "temporal_ratio": "candidate clip temporal / reference clip temporal",
    "luma_delta": "candidate mean luma - reference mean luma, over all frames and pixels",
    "aggregate": "median of each metric over the complete sample set",
    "psnr_db": "diagnostic only: luma PSNR from the mean squared error of index-aligned frames",
}
SCOPE = ("decoded luma of matched video pairs: sharpness, motion and brightness against a "
         "dense reference; not audio, semantics, prompt adherence or defects confined to "
         "a few frames")
DECODE_TIMEOUT = 3600


def _rate(text):
    try:
        rate = Fraction(text)
    except (ValueError, ZeroDivisionError, TypeError):
        return None
    return rate if rate > 0 else None


def _real(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value))


def _frozen_bounds(name, bounds):
    if not isinstance(bounds, Mapping) or set(bounds) != set(METRICS):
        raise ValueError(f"{name} must give bounds for exactly {', '.join(METRICS)}")
    for metric, pair in bounds.items():
        if (not isinstance(pair, (tuple, list)) or len(pair) != 2
                or not all(_real(v) for v in pair) or pair[0] > pair[1]):
            raise ValueError(f"{name}[{metric}] must be a finite (low, high) pair")
    # Snapshot the caller's values, so later edits to its dict or lists cannot move a bound.
    return MappingProxyType({metric: (float(bounds[metric][0]), float(bounds[metric][1]))
                             for metric in METRICS})


def _check_control(control, owner):
    # Controls are copied into the report, which must stay valid strict JSON.
    if not isinstance(control, Mapping) or any(
        not isinstance(key, str)
        or not (value is None or isinstance(value, (str, bool)) or _real(value))
        for key, value in control.items()
    ):
        raise ValueError(f"{owner} needs a mapping of string, boolean, null or finite "
                         "number control values")


@dataclass(frozen=True)
class MediaContract:
    width: int
    height: int
    fps: str
    frames: int

    def __post_init__(self):
        if any(isinstance(v, bool) or not isinstance(v, int) or v <= 0
               for v in (self.width, self.height)):
            raise ValueError("Positive video dimensions are required")
        if isinstance(self.frames, bool) or not isinstance(self.frames, int) or self.frames < 2:
            raise ValueError("At least two frames are required")
        if not isinstance(self.fps, str) or _rate(self.fps) is None:
            raise ValueError("fps must be a positive rational string such as '24/1'")


@dataclass(frozen=True)
class VideoQualityGate:
    # Control fields that must be equal between a candidate and its dense reference,
    # for example precision, parallel layout and an input digest.
    matched_controls: tuple
    # Two-sided bounds per sample; a sample outside them is a severe defect.
    sample_bounds: Mapping
    # Two-sided bounds on the median of each metric over the complete sample set.
    aggregate_bounds: Mapping

    def __post_init__(self):
        fields = self.matched_controls
        if (not isinstance(fields, tuple) or not fields or len(set(fields)) != len(fields)
                or any(not isinstance(f, str) or not f.strip() for f in fields)):
            raise ValueError("matched_controls must be a nonempty tuple of distinct field names")
        for name in ("sample_bounds", "aggregate_bounds"):
            object.__setattr__(self, name, _frozen_bounds(name, getattr(self, name)))

    def record(self) -> dict:
        return {"matched_controls": list(self.matched_controls),
                **{name: {metric: list(pair) for metric, pair in getattr(self, name).items()}
                   for name in ("sample_bounds", "aggregate_bounds")}}


@dataclass(frozen=True, eq=False)
class Clip:
    luma: object  # uint8 array shaped (frames, height, width)
    fps: str
    control: Mapping
    sha256: str | None = None
    # Rotation of a container display matrix; None when the stream carries no matrix.
    display_rotation: float | None = None

    def __post_init__(self):
        if str(getattr(self.luma, "dtype", "")) != "uint8" or getattr(self.luma, "ndim", 0) != 3:
            raise ValueError("Clip luma must be a uint8 array shaped (frames, height, width)")
        if not isinstance(self.fps, str):
            raise ValueError("Clip needs an fps string")
        if self.display_rotation is not None and not _real(self.display_rotation):
            raise ValueError("display_rotation must be None or a finite number")
        _check_control(self.control, "Clip")
        # Snapshot the provenance, so the recorded match cannot change after construction.
        object.__setattr__(self, "control", MappingProxyType(dict(self.control)))


def _run(command):
    return subprocess.run(command, check=True, capture_output=True,
                          timeout=DECODE_TIMEOUT).stdout


def load_clip(path, control: dict) -> Clip:
    import numpy as np

    path = Path(path)
    digest = sha256(path)
    streams = json.loads(_run([
        "ffprobe", "-v", "error", "-select_streams", "v", "-count_frames",
        "-show_entries",
        "stream=width,height,avg_frame_rate,nb_read_frames:"
        "stream_side_data=side_data_type,rotation",
        "-of", "json", str(path),
    ]))["streams"]
    if len(streams) != 1:
        raise ValueError("Exactly one video stream is required")
    stream = streams[0]
    width, height, frames = stream["width"], stream["height"], int(stream["nb_read_frames"])
    # ffprobe reports coded size. Decoding without autorotation keeps that layout, and
    # any display matrix is recorded so the media contract can reject it.
    matrices = [item.get("rotation", 0) for item in stream.get("side_data_list", [])
                if str(item.get("side_data_type", "")).replace(" ", "").lower()
                == "displaymatrix"]
    raw = _run(["ffmpeg", "-nostdin", "-v", "error", "-noautorotate", "-i", str(path),
                "-map", "0:v:0", "-f", "rawvideo", "-pix_fmt", "gray", "-"])
    if len(raw) != frames * width * height:
        raise ValueError("Decoded luma does not match the probed frame count and size")
    luma = np.frombuffer(raw, dtype=np.uint8).reshape(frames, height, width)
    return Clip(luma, stream["avg_frame_rate"], control, digest,
                float(matrices[0]) if matrices else None)


def _media(clip):
    frames, height, width = clip.luma.shape
    return {"sha256": clip.sha256, "width": width, "height": height, "frames": frames,
            "fps": clip.fps, "display_rotation": clip.display_rotation}


def _contract_errors(clip, contract):
    frames, height, width = clip.luma.shape
    errors = [f"{name} {actual} != {expected}" for name, actual, expected in (
        ("width", width, contract.width), ("height", height, contract.height),
        ("frames", frames, contract.frames)) if actual != expected]
    if _rate(clip.fps) != _rate(contract.fps):
        errors.append(f"fps {clip.fps} != {contract.fps}")
    # Coded frames are judged; a display transform would show viewers other frames.
    if clip.display_rotation is not None:
        errors.append(f"display matrix present (rotation {clip.display_rotation:g})")
    return errors


def _statistics(luma):
    import numpy as np

    sharpness = temporal = brightness = 0.0
    previous = None
    # One frame at a time bounds memory for long, high-resolution clips.
    for frame in luma:
        frame = frame.astype(np.float64)
        padded = np.pad(frame, 1, mode="edge")
        laplacian = (padded[:-2, 1:-1] + padded[2:, 1:-1] + padded[1:-1, :-2]
                     + padded[1:-1, 2:] - 4 * frame)
        sharpness += float(laplacian.var())
        brightness += float(frame.mean())
        if previous is not None:
            temporal += float(np.abs(frame - previous).mean())
        previous = frame
    count = luma.shape[0]
    return {"sharpness": sharpness / count, "temporal": temporal / (count - 1),
            "luma_mean": brightness / count}


def _psnr(reference, candidate):
    import numpy as np

    total = sum(float(np.mean((left.astype(np.float64) - right.astype(np.float64)) ** 2))
                for left, right in zip(reference, candidate))
    mse = total / reference.shape[0]
    return "inf" if mse == 0 else 10 * math.log10(255**2 / mse)


def measure_pair(sample_id: str, reference: Clip, candidate: Clip,
                 contract: MediaContract, gate: VideoQualityGate) -> dict:
    record = {"id": sample_id,
              "media": {"reference": _media(reference), "candidate": _media(candidate)}}
    # A candidate that breaks the frozen media contract is an observed defect.
    defects = _contract_errors(candidate, contract)
    if defects:
        return {**record, "status": "FAIL",
                "reasons": ["candidate_media_contract: " + d for d in defects]}
    reasons = ["reference_media_contract: " + e for e in _contract_errors(reference, contract)]
    for field in gate.matched_controls:
        # A null value is not evidence, and equality needs the same JSON type: true != 1.
        left, right = reference.control.get(field), candidate.control.get(field)
        if left is None or right is None:
            reasons.append("control_missing: " + field)
        elif type(left) is not type(right) or left != right:
            reasons.append("control_mismatch: " + field)
    if reasons:
        return {**record, "status": "INCONCLUSIVE", "reasons": reasons}
    ref, cand = _statistics(reference.luma), _statistics(candidate.luma)
    # Ratios against a flat or motionless reference are undefined.
    zero = [name for name in ("sharpness", "temporal") if ref[name] == 0]
    if zero:
        return {**record, "status": "INCONCLUSIVE",
                "reasons": ["reference_zero_" + name for name in zero]}
    return {**record, "status": "MEASURED", "reasons": [],
            "controls": {field: reference.control[field] for field in gate.matched_controls},
            "metrics": {"sharpness_ratio": cand["sharpness"] / ref["sharpness"],
                        "temporal_ratio": cand["temporal"] / ref["temporal"],
                        "luma_delta": cand["luma_mean"] - ref["luma_mean"]},
            "diagnostics": {"psnr_db": _psnr(reference.luma, candidate.luma),
                            "reference": ref, "candidate": cand}}


def _outside(metrics, bounds):
    return [f"{name} {metrics[name]:.6g} outside [{bounds[name][0]}, {bounds[name][1]}]"
            for name in METRICS if not bounds[name][0] <= metrics[name] <= bounds[name][1]]


def summarize(records: list, contract: MediaContract, gate: VideoQualityGate, *,
              dataset: str) -> dict:
    # dataset names the frozen sample set; the Harness matches it to quality_benchmark.
    if not isinstance(dataset, str) or not dataset.strip():
        raise ValueError("A frozen dataset identity is required")
    if not isinstance(records, list) or not records:
        raise ValueError("At least one sample is required")
    if len({record["id"] for record in records}) != len(records):
        raise ValueError("Sample ids must be distinct")
    samples = []
    for record in records:
        if record["status"] == "MEASURED":
            metrics = record["metrics"]
            if set(metrics) != set(METRICS) or not all(_real(v) for v in metrics.values()):
                raise ValueError("A measured sample needs finite values for every metric")
            violations = _outside(metrics, gate.sample_bounds)
            record = {**record, "status": "FAIL" if violations else "PASS", "reasons": violations}
        elif record["status"] not in ("FAIL", "INCONCLUSIVE") or not record["reasons"]:
            raise ValueError("An unmeasured sample needs FAIL or INCONCLUSIVE with reasons")
        samples.append(record)
    aggregate = None
    # The aggregate is defined only over the complete set of measured samples.
    if all("metrics" in sample for sample in samples):
        median = {name: statistics.median(s["metrics"][name] for s in samples)
                  for name in METRICS}
        aggregate = {"median": median, "violations": _outside(median, gate.aggregate_bounds)}
    reasons = [f"{s['id']}: {reason}" for s in samples
               if s["status"] != "PASS" for reason in s["reasons"]]
    if aggregate:
        reasons += ["aggregate: " + violation for violation in aggregate["violations"]]
    statuses = {sample["status"] for sample in samples}
    # Observed violations fail the set even when other samples lack evidence.
    if "FAIL" in statuses or (aggregate and aggregate["violations"]):
        verdict = "FAIL"
    elif "INCONCLUSIVE" in statuses:
        verdict = "INCONCLUSIVE"
    else:
        verdict = "PASS"
    return {"verdict": verdict, "passed": {"PASS": True, "FAIL": False}.get(verdict),
            "dataset": dataset, "reasons": reasons, "metrics_version": METRICS_VERSION,
            "definitions": DEFINITIONS, "scope": SCOPE, "contract": asdict(contract),
            "gate": gate.record(), "samples": samples, "aggregate": aggregate}


def _check_entry(entry, role):
    if not isinstance(entry, dict) or not isinstance(entry.get("path"), (str, Path)):
        raise ValueError(f"{role} needs a path")
    # A malformed control is a plan error, raised before decoding, not missing evidence.
    _check_control(entry.get("control"), role)
    digest = entry.get("sha256")
    if digest is None and role == "reference":
        raise ValueError("A frozen reference needs its sha256")
    if digest is not None and (not isinstance(digest, str) or len(digest) != 64
                               or set(digest) - set("0123456789abcdef")):
        raise ValueError(f"{role} sha256 must be a lowercase hexadecimal digest")


def _decoder():
    try:
        return _run(["ffmpeg", "-version"]).decode(errors="replace").splitlines()[0]
    except (OSError, subprocess.SubprocessError):
        return None


def compare_videos(samples: list, contract: MediaContract, gate: VideoQualityGate, *,
                   dataset: str) -> dict:
    if not isinstance(samples, list) or not samples:
        raise ValueError("At least one sample is required")
    for sample in samples:
        if not isinstance(sample, dict) or not isinstance(sample.get("id"), str) or not sample[
            "id"
        ]:
            raise ValueError("Each sample needs a nonempty id")
        for role in ("reference", "candidate"):
            _check_entry(sample.get(role), role)
    # Reject a malformed plan before any clip is decoded.
    if len({sample["id"] for sample in samples}) != len(samples):
        raise ValueError("Sample ids must be distinct")
    if not isinstance(dataset, str) or not dataset.strip():
        raise ValueError("A frozen dataset identity is required")
    records = []
    for sample in samples:
        clips, reasons = {}, []
        for role in ("reference", "candidate"):
            entry = sample[role]
            if not Path(entry["path"]).is_file():
                reasons.append(role + "_missing")
                continue
            try:
                clip = load_clip(entry["path"], entry["control"])
            except (OSError, ValueError, KeyError, TypeError,
                    subprocess.SubprocessError) as error:
                reasons.append(f"{role}_undecodable: {type(error).__name__}")
                continue
            if entry.get("sha256") not in (None, clip.sha256):
                reasons.append(role + "_hash_mismatch")
                continue
            clips[role] = clip
        if not reasons:
            records.append(measure_pair(sample["id"], clips["reference"], clips["candidate"],
                                        contract, gate))
            continue
        record = {"id": sample["id"],
                  "media": {role: _media(clip) for role, clip in clips.items()}}
        defects = _contract_errors(clips["candidate"], contract) if "candidate" in clips else []
        if defects:
            records.append({**record, "status": "FAIL",
                            "reasons": ["candidate_media_contract: " + d for d in defects]})
        else:
            records.append({**record, "status": "INCONCLUSIVE", "reasons": reasons})
    report = summarize(records, contract, gate, dataset=dataset)
    report["decoder"] = _decoder()
    return report
