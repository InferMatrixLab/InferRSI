"""CPU-only integrity/statistics verification; does not execute candidates."""

import argparse
import csv
import gzip
import hashlib
import json
import math
import re
import statistics
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def close(actual, expected):
    assert math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12), (actual, expected)


def csv_rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def scan_text(name, data):
    text = data.decode("utf-8")
    patterns = {
        "personal absolute path": r"(?i)(?:(?<![A-Za-z])[A-Z]:[\\/]|/(?:home|Users)/)",
        "network address": r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])",
        "chat identifier": r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        "SSH invocation": r"\bssh\s+(?:-\S+\s+)*\S+@",
        "credential marker": r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----",
    }
    for category, pattern in patterns.items():
        assert not re.search(pattern, text), f"{name}: {category} requires publication review"


def verify(root, source=None):
    if not __debug__:
        raise RuntimeError("Verification requires Python assertions; do not use -O")
    integrity = read(root / "plan/integrity.json")
    actual_files = {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.name != "integrity.json"
    }
    assert set(integrity) == actual_files, "Bundle file inventory changed"
    for name, expected in integrity.items():
        assert not Path(name).is_absolute() and ".." not in Path(name).parts
        data = (root / name).read_bytes()
        assert sha(data) == expected, name
        if Path(name).suffix in {".py", ".md", ".json", ".csv"}:
            scan_text(name, data)
    summary = read(root / "results/summary.json")
    with gzip.open(root / "results/measurements.jsonl.gz", "rt", encoding="utf-8") as stream:
        measurements = [json.loads(line) for line in stream]
    scan_text("measurements", json.dumps(measurements).encode())
    audits = read(root / "results/audit-extract.json")["attempts"]
    csv_rounds = csv_rows(root / "results/rounds.csv")
    usage_rows = csv_rows(root / "results/session-usage.csv")
    assert len(measurements) == len(audits) == len(csv_rounds) == 54
    assert len(summary["sessions"]) == len(usage_rows) == 6
    candidates = csv_rows(root / "patch/candidates.csv")
    assert len(candidates) == 54
    source_bytes = {}
    with zipfile.ZipFile(root / "patch/exploration-candidates.zip") as archive:
        assert len(archive.namelist()) == 48
        for candidate in candidates:
            location = candidate["file"]
            data = (
                archive.read(location.split("!", 1)[1])
                if "!" in location
                else (root / location).read_bytes()
            )
            scan_text(location, data)
            assert sha(data) == candidate["sha256"]
            assert len(data) == int(candidate["bytes"])
            source_bytes[
                (candidate["session_key"], candidate["role"], candidate["round_index"])
            ] = data
    valid = failed = samples = final_count = 0
    for session, usage in zip(summary["sessions"], usage_rows):
        key = session["key"]
        assert session["reasoning_effort"] == ["xhigh"]
        assert session["knowledge"] in {"on", "off"}
        obs = session["observations"]
        assert [o["round_index"] for o in obs[:8]] == list(range(1, 9))
        assert [o["role"] for o in obs] == ["exploratory"] * 8 + ["final"]
        best, previous = (
            1.0,
            {k: 0 for k in ("input", "cached_input", "output", "total", "uncached_input")},
        )
        for o in obs:
            identity = (key, o["role"], o["round_index"])
            row = next(
                m
                for m in measurements
                if (m["session_key"], m["role"], m["round_index"]) == identity
            )
            assert {k: row[k] for k in o} == o
            audit = next(
                a for a in audits if (a["session_key"], a["role"], a["round_index"]) == identity
            )
            assert audit["audit_status"] == "PASS" and audit["cleanup_verified"]
            assert o["cleanup_verified"] and o["token_boundary_status"] == "verified"
            assert o["attempt"] == 1 and o["round_consumed"]
            source_key = (key, o["role"], "" if o["round_index"] is None else str(o["round_index"]))
            assert sha(source_bytes[source_key]) == o["candidate_sha256"]
            for kind in previous:
                cumulative = o[f"cumulative_{kind}_tokens"]
                assert cumulative - previous[kind] == o[f"round_{kind}_tokens"]
                previous[kind] = cumulative
            assert (
                o["cumulative_total_tokens"]
                == o["cumulative_input_tokens"] + o["cumulative_output_tokens"]
            )
            assert (
                o["cumulative_input_tokens"]
                == o["cumulative_cached_input_tokens"] + o["cumulative_uncached_input_tokens"]
            )
            assert 0 <= o["cumulative_reasoning_output_tokens"] <= o["cumulative_output_tokens"]
            if o["valid_measurement"]:
                valid += 1
                assert o["correctness"] == o["performance_verdict"] == "PASS"
                assert len(row["cases"]) == 3 and {r["rank"] for r in audit["ranks"]} == {0, 1}
                count = 32 if o["role"] == "final" else 16
                case_speedups = []
                for case in row["cases"]:
                    for label in ("baseline", "candidate"):
                        values = case["samples_ms"][label]
                        assert len(values) == count and all(
                            math.isfinite(v) and v > 0 for v in values
                        )
                        samples += len(values)
                        close(statistics.median(values), case[f"{label}_median_ms"])
                    ratio = case["baseline_median_ms"] / case["candidate_median_ms"]
                    close(ratio, case["speedup"])
                    case_speedups.append(ratio)
                close(statistics.geometric_mean(case_speedups), o["speedup"])
                assert all(r["local_failed_calls"] == 0 for r in audit["ranks"])
                assert all(
                    r["calls"] == (424 if o["role"] == "final" else 232) for r in audit["ranks"]
                )
                if o["role"] == "exploratory":
                    best = max(best, o["speedup"])
                else:
                    final_count += 1
            else:
                failed += 1
                assert key.startswith("gpt6astra-") and o["round_index"] == 4
                assert o["correctness"] == "FAIL" and o["performance_verdict"] == "INCONCLUSIVE"
                assert o["speedup"] is None and row["cases"] is None and o["failure_reason"]
            close(o["best_exploration_speedup"], best)
        selected = obs[session["selected_round"] - 1]
        assert (
            selected["candidate_sha256"]
            == obs[-1]["candidate_sha256"]
            == session["final_candidate_sha256"]
        )
        close(session["final_speedup"], obs[-1]["speedup"])
        u = session["usage"]
        assert (
            u["total_tokens"]
            == obs[-1]["cumulative_total_tokens"] + session["post_measurement_reporting_tokens"]
        )
        assert u["total_tokens"] == u["input_tokens"] + u["output_tokens"]
        assert u["input_tokens"] == u["cached_input_tokens"] + u["uncached_input_tokens"]
        assert u["reasoning_output_tokens"] <= u["output_tokens"]
        assert int(usage["total_tokens"]) == u["total_tokens"]
        assert int(usage["exploration_tokens"]) == obs[7]["cumulative_total_tokens"]
        assert int(usage["final_stage_tokens"]) == obs[8]["round_total_tokens"]
        assert int(usage["report_tail_tokens"]) == session["post_measurement_reporting_tokens"]
        close(sum(o["queue_seconds"] for o in obs), session["queue_seconds"])
        close(
            sum(o["allocation_process_seconds"] for o in obs), session["allocation_process_seconds"]
        )
    assert (valid, failed, final_count, samples) == (52, 2, 6, 5568)
    assert sum(s["usage"]["total_tokens"] for s in summary["sessions"]) == 79562339
    for csv_row, row in zip(csv_rounds, measurements):
        for field, value in row.items():
            if field not in csv_row:
                continue
            assert csv_row[field] == ("" if value is None else str(value)), field
    plan = read(root / "plan/publication.json")
    for prefix, files in (
        ("task", (root / "validator/task").iterdir()),
        ("runner", (root / "validator/runner").iterdir()),
    ):
        for path in files:
            assert sha(path.read_bytes()) == plan["source_hashes"][f"{prefix}/{path.name}"]
    if source is not None:
        original = read(source / "results/summary.json")
        for public_session, original_session in zip(summary["sessions"], original["sessions"]):
            assert public_session["key"] == original_session["key"]
            shared_fields = public_session.keys() & original_session.keys()
            for field in shared_fields - {"observations", "usage"}:
                assert public_session[field] == original_session[field], field
            for field, value in public_session["usage"].items():
                assert value == original_session["usage"][field], field
            assert public_session["reasoning_effort"] == original_session["usage"]["efforts"]
            assert public_session["queue_seconds"] == original_session["recorded_queue_seconds"]
            assert public_session["allocation_process_seconds"] == original_session[
                "recorded_device_active_seconds"
            ]
            for public_row, original_row in zip(
                public_session["observations"], original_session["observations"]
            ):
                for field in public_row.keys() & original_row.keys():
                    assert public_row[field] == original_row[field], field
                m = next(
                    r
                    for r in measurements
                    if r["session_key"] == public_session["key"]
                    and r["role"] == public_row["role"]
                    and r["round_index"] == public_row["round_index"]
                )
                assert m["cases"] == original_row["cases"]
                p = Path(original_row["observation_path"])
                assert sha(p.read_bytes()) == m["original_observation_sha256"]
                source_key = (
                    public_session["key"],
                    m["role"],
                    "" if m["round_index"] is None else str(m["round_index"]),
                )
                assert source_bytes[source_key] == (p.parent / "implementation.py").read_bytes()
        for name, entry in read(root / "plan/provenance.json")["original_artifacts"].items():
            assert sha((source / name).read_bytes()) == entry["sha256"], name
    print(
        json.dumps(
            {
                "status": "PASS",
                "attempts": 54,
                "exploration_pass": 46,
                "exploration_fail": 2,
                "final_pass": final_count,
                "timing_samples": samples,
                "candidate_sources": 54,
                "source_archive_compared": source is not None,
                "scope": "public extraction integrity/statistics; no device rerun",
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, help="Optional authorized original archive for byte comparison"
    )
    args = parser.parse_args()
    verify(ROOT, args.source)
