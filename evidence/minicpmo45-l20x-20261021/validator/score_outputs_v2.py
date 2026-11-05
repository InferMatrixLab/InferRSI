"""Score saved WAVs, refusing to resume onto different audio.

``score_outputs.py`` is the historical frozen scorer and is unchanged. This
successor checks prompt IDs, WAV hashes, durations and scorer-file provenance
before it writes audio provenance or skips a completed task. A reused output
whose inputs differ is rejected and left untouched.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

WAV_FIELDS = ("wav_sha256", "duration_s")


class StaleScoringOutput(ValueError):
    """Saved scores do not belong to the current audio or scorers."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical(value):
    return json.loads(json.dumps(value, allow_nan=False))


def scorer_provenance(scorers: Path) -> dict:
    """Content hashes of every file currently under the scorer directory."""
    root = Path(scorers)
    files = {
        path.relative_to(root).as_posix(): _sha256(path)
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    }
    if not files:
        raise ValueError("scorer directory contains no files")
    return {"successor": "score_outputs_v2", "files": files}


def bind_resume(existing, ids, wav_by_id, provenance):
    """Return a document that is safe to continue, without mutating inputs.

    ``existing`` is ``None`` for a new output. A stored document is returned
    unchanged when its IDs, WAV provenance and scorer provenance match.
    """
    if not isinstance(ids, list) or not ids or len(ids) != len(set(ids)):
        raise ValueError("request ids must be unique and nonempty")
    if set(wav_by_id) != set(ids):
        raise ValueError("wav provenance must cover exactly the request ids")
    fresh_wavs = {}
    for request_id in ids:
        record = wav_by_id[request_id]
        if not isinstance(record, dict) or set(record) != set(WAV_FIELDS):
            raise ValueError("wav provenance must contain only hash and duration")
        digest = record["wav_sha256"]
        duration = record["duration_s"]
        hexadecimal = set("0123456789abcdef")
        digest_ok = (
            isinstance(digest, str)
            and len(digest) == 64
            and all(char in hexadecimal for char in digest)
        )
        if not digest_ok:
            raise ValueError("wav hash must be a lowercase SHA-256 digest")
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not duration > 0:
            raise ValueError("duration must be a positive number")
        fresh_wavs[request_id] = {"wav_sha256": digest, "duration_s": duration}
    if not isinstance(provenance, dict) or set(provenance) != {"successor", "files"}:
        raise ValueError("scorer provenance must identify score_outputs_v2 files")
    if provenance["successor"] != "score_outputs_v2" or not isinstance(provenance["files"], dict):
        raise ValueError("scorer provenance must identify score_outputs_v2 files")
    if not provenance["files"]:
        raise ValueError("scorer provenance must contain at least one file")
    canonical_provenance = _canonical(provenance)
    canonical_wavs = _canonical(fresh_wavs)
    if existing is None:
        return {
            "rows": {request_id: dict(canonical_wavs[request_id]) for request_id in ids},
            "tasks": [],
            "scorer_provenance": canonical_provenance,
        }
    if not isinstance(existing, dict):
        raise StaleScoringOutput("existing scoring output is not an object")
    rows = existing.get("rows")
    tasks = existing.get("tasks")
    recorded = existing.get("scorer_provenance")
    if not isinstance(rows, dict) or not isinstance(tasks, list) or not isinstance(recorded, dict):
        raise StaleScoringOutput(
            "existing scoring output is missing rows, tasks, or scorer provenance"
        )
    if set(rows) != set(ids):
        raise StaleScoringOutput("prompt IDs differ from the existing scoring output")
    if _canonical(recorded) != canonical_provenance:
        raise StaleScoringOutput("scorer provenance differs from the existing scoring output")
    for request_id in ids:
        row = rows[request_id]
        if not isinstance(row, dict):
            raise StaleScoringOutput(f"row {request_id} is not an object")
        stored = {field: row.get(field) for field in WAV_FIELDS}
        try:
            stored_canonical = _canonical(stored)
        except (TypeError, ValueError) as exc:
            raise StaleScoringOutput(f"WAV provenance for {request_id} is not comparable") from exc
        if stored_canonical != canonical_wavs[request_id]:
            raise StaleScoringOutput(
                f"WAV provenance differs for {request_id}; refusing to replace it with new audio"
            )
    return copy.deepcopy(existing)


def resume_output(path: Path, ids, wav_by_id, provenance):
    """Load ``path`` when it exists and resume, or start a new document.

    Raises ``StaleScoringOutput`` before any write when the saved output does
    not belong to these inputs.
    """
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    return bind_resume(existing, ids, wav_by_id, provenance)


def _fingerprint_wav(path: Path) -> dict:
    import numpy as np
    import soundfile as sf

    audio, sample_rate = sf.read(path)
    if len(audio) == 0 or not np.isfinite(audio).all() or sample_rate <= 0:
        raise ValueError(f"invalid audio: {path}")
    return {
        "wav_sha256": _sha256(path),
        "duration_s": len(audio) / sample_rate,
    }


def _load_run(run: Path):
    from bench.workload import load_seed_tts_rows

    rows = {row.row_id: row for row in load_seed_tts_rows()}
    metrics = [json.loads(line) for line in (run / "requests.jsonl").read_text().splitlines()]
    if not metrics or not all(item["ok"] for item in metrics):
        raise ValueError("run has no successful requests")
    ids = sorted(item["request_id"] for item in metrics)
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate request ids")
    wavs = {request_id: _fingerprint_wav(run / "wav" / f"{request_id}.wav") for request_id in ids}
    return rows, ids, wavs


def _save(path: Path, document) -> None:
    path.write_text(json.dumps(document, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _score_missing(args, document, rows, ids, wavs) -> None:
    wav_paths = [str(Path(args.run) / "wav" / f"{request_id}.wav") for request_id in ids]
    if "wer" in args.tasks and "wer" not in document["tasks"]:
        import concurrent.futures

        from benchmarks.metrics.wer import SampleOutput
        from benchmarks.tasks.asr import apply_wer, load_qwen3_asr, transcribe

        asr = load_qwen3_asr(args.asr_port)

        def score(pair):
            request_id, wav_path = pair
            hypothesis = transcribe(asr, wav_path, "en", args.device)
            result = apply_wer(
                SampleOutput(sample_id=request_id, target_text=rows[request_id].target_text),
                hypothesis,
                "en",
            )
            if not result.is_success:
                raise RuntimeError(result.error)
            values = {
                key: getattr(result, key)
                for key in ("wer", "substitutions", "deletions", "insertions", "hits")
            }
            values["hyp_text"] = hypothesis
            return request_id, values

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for request_id, result in pool.map(score, zip(ids, wav_paths)):
                document["rows"][request_id]["wer"] = result
        document["tasks"].append("wer")
        _save(Path(args.out), document)
    if "sim" in args.tasks and "sim" not in document["tasks"]:
        from benchmarks.metrics.speaker_similarity import WavLMSpeakerSimilarity

        weights = Path(args.scorers) / "sim"
        scorer = WavLMSpeakerSimilarity(
            finetune_checkpoint=weights / "wavlm_large_finetune.pth",
            wavlm_base=weights / "wavlm_large.pt",
            device=args.device,
        )
        for start in range(0, len(ids), 4):
            batch = ids[start:start + 4]
            scores = scorer.score_batch(
                [rows[request_id].ref_wav_path for request_id in batch],
                wav_paths[start:start + 4],
            )
            for request_id, score in zip(batch, scores):
                document["rows"][request_id]["sim"] = float(score)
        document["tasks"].append("sim")
        _save(Path(args.out), document)
        del scorer
    if "utmos" in args.tasks and "utmos" not in document["tasks"]:
        from benchmarks.metrics.utmos import UTMOSScorer

        scorer = UTMOSScorer(device=args.device, cache_dir=Path(args.scorers) / "utmos")
        for start in range(0, len(ids), 8):
            batch = ids[start:start + 8]
            scores = scorer.score_batch(wav_paths[start:start + 8])
            for request_id, score in zip(batch, scores):
                document["rows"][request_id]["utmos"] = float(score)
        document["tasks"].append("utmos")
        _save(Path(args.out), document)


def _summary(document) -> dict:
    import numpy as np

    summary = {"n": len(document["rows"])}
    for key in ("sim", "utmos"):
        if key in document["tasks"]:
            summary[key] = float(np.mean([row[key] for row in document["rows"].values()]))
    if "wer" in document["tasks"]:
        counts = {
            key: sum(row["wer"][key] for row in document["rows"].values())
            for key in ("substitutions", "deletions", "insertions", "hits")
        }
        errors = ("substitutions", "deletions", "insertions")
        denominator = ("substitutions", "deletions", "hits")
        error_count = sum(counts[key] for key in errors)
        summary["wer"] = error_count / sum(counts[key] for key in denominator)
        summary["wer_counts"] = counts
        means = [row["wer"]["wer"] for row in document["rows"].values()]
        summary["wer_mean"] = float(np.mean(means))
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--scorers", required=True)
    parser.add_argument("--asr-port", type=int, default=29181)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--tasks", nargs="+", default=["wer", "sim", "utmos"])
    args = parser.parse_args(argv)
    rows, ids, wavs = _load_run(Path(args.run))
    provenance = scorer_provenance(Path(args.scorers))
    out = Path(args.out)
    document = resume_output(out, ids, wavs, provenance)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists():
        _save(out, document)
    _score_missing(args, document, rows, ids, wavs)
    document["summary"] = _summary(document)
    _save(out, document)
    print(json.dumps(document["summary"]), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
