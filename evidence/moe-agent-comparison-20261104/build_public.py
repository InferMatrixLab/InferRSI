"""Extract the historical campaign without running an agent or a device.

The source is a private, already audited archive. This script selects public
fields; it does not sanitize arbitrary logs. Review source text before sharing.
"""

import argparse
import csv
import gzip
import hashlib
import json
import math
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OBS_FIELDS = (
    "role round_index candidate_sha256 task_sha256 grader_sha256 source_revision "
    "source_bundle_sha256 correctness valid_measurement aggregation speedup "
    "effective_speedup best_exploration_speedup cleanup_verified queue_seconds "
    "token_boundary_status cumulative_input_tokens cumulative_cached_input_tokens "
    "cumulative_output_tokens cumulative_total_tokens cumulative_uncached_input_tokens "
    "cumulative_reasoning_output_tokens round_input_tokens round_cached_input_tokens "
    "round_output_tokens round_total_tokens round_uncached_input_tokens"
).split()
USAGE_FIELDS = (
    "request_records input_tokens cached_input_tokens output_tokens total_tokens "
    "uncached_input_tokens reasoning_output_tokens monetary_cost"
).split()
AUDIT_FIELDS = (
    "candidate_outcome expected_calls_per_rank timed_samples_per_label_per_case "
    "max_rank_samples_checked pair_geometric_speedups audit_scope audit_status "
    "frozen_source_files_verified cleanup_verified"
).split()
RANK_FIELDS = (
    "rank calls timed_samples local_failed_calls max_errors_by_label "
    "minimum_warm_input_rms_difference minimum_warm_output_nrmse_difference"
).split()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def select(obj, fields):
    return {key: obj[key] for key in fields if key in obj}


def write(path, data):
    path.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def csv_write(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build(source, target):
    source, target = source.resolve(), target.resolve()
    if target.is_relative_to(source) or source.is_relative_to(target):
        raise ValueError("Source archive and publication destination must not overlap")
    for part in ("plan", "results", "patch/final", "validator/task", "validator/runner"):
        (target / part).mkdir(parents=True, exist_ok=True)
    original = read(source / "results/summary.json")
    plan = read(source / "common/plan.json")
    extension = read(source / "extension-plan.json")
    assert original["campaign_complete"] and original["condition_comparison_verified"]
    assert len(original["sessions"]) == 6
    public = select(
        original,
        (
            "schema_version",
            "campaign_id",
            "expected_session_count",
            "campaign_complete",
            "condition_comparison_verified",
        ),
    )
    public["publication_type"] = "redacted field extract; not the original summary"
    public["sessions"] = []
    measurements, rows, usage_rows, candidates, audits = [], [], [], [], []
    originals = {}
    for name in (
        "results/summary.json",
        "common/plan.json",
        "extension-plan.json",
        "results/comparison-overview.png",
        "analysis/render_overview.py",
    ):
        originals[name] = {
            "sha256": digest(source / name),
            "bytes": (source / name).stat().st_size,
            "availability": "external original; no private paths published",
        }
    originals["results/comparison-overview.png"]["availability"] = (
        "published byte-identical copy at results/comparison-overview.png"
    )
    archive_path = target / "patch/exploration-candidates.zip"
    with zipfile.ZipFile(
        archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for index, session in enumerate(original["sessions"]):
            key = session["key"]
            audit_path = source / f"analysis/raw-audit-{index}.json"
            raw_audit = read(audit_path)
            assert raw_audit["status"] == "PASS" and raw_audit["acceptance_ready"]
            condition_audit = read(source / f"analysis/condition-audit-{index}.json")
            assert condition_audit["status"] == "verified"
            for kind, suffix in (
                ("raw-audit", "json"),
                ("condition-audit", "json"),
                ("source-audit", "md"),
            ):
                name = f"analysis/{kind}-{index}.{suffix}"
                originals[name] = {
                    "sha256": digest(source / name),
                    "availability": "external audit original",
                }
            s = select(
                session,
                (
                    "key",
                    "label",
                    "model",
                    "knowledge",
                    "status",
                    "rounds_completed",
                    "rounds_expected",
                    "validation_status",
                    "best_exploration_speedup",
                    "final_speedup",
                    "post_measurement_reporting_tokens",
                ),
            )
            s["reasoning_effort"] = session["usage"]["efforts"]
            s["usage"] = select(session["usage"], USAGE_FIELDS)
            s["queue_seconds"] = session["recorded_queue_seconds"]
            s["allocation_process_seconds"] = session["recorded_device_active_seconds"]
            s["observations"] = []
            for observation in session["observations"]:
                original_path = Path(observation["observation_path"])
                actual = read(original_path)
                remote_path = original_path.parent / "remote/results/summary.json"
                remote_summary = read(remote_path) if remote_path.exists() else {}
                assert remote_path.exists() or observation["correctness"] == "FAIL"
                assert observation["cases"] == actual.get("cases") == remote_summary.get("cases")
                assert (
                    observation["speedup"] is None and actual.get("speedup") is None
                ) or math.isclose(observation["speedup"], actual["speedup"], rel_tol=1e-12)
                implementation = original_path.parent / "implementation.py"
                assert digest(implementation) == observation["candidate_sha256"]
                o = select(observation, OBS_FIELDS)
                o["allocation_process_seconds"] = observation["device_active_seconds"]
                o["original_observation_sha256"] = digest(original_path)
                o["original_device_summary_sha256"] = (
                    digest(remote_path) if remote_path.exists() else None
                )
                o["attempt"] = actual["attempt"]
                o["round_consumed"] = actual["round_consumed"]
                o["execution_status"] = actual["status"]
                o["performance_verdict"] = "PASS" if o["valid_measurement"] else "INCONCLUSIVE"
                o["failure_reason"] = (
                    None
                    if o["correctness"] == "PASS"
                    else (
                        "Candidate rejected on both ranks before timing: installed "
                        "npu_moe_finalize_routing does not accept keyword argument 'k'."
                    )
                )
                s["observations"].append(o)
                measurements.append({"session_key": key, **o, "cases": observation["cases"]})
                rows.append({"session_key": key, **o})
                audit = next(
                    a
                    for a in raw_audit["attempts"]
                    if a["role"] == o["role"] and a["round_index"] == o["round_index"]
                )
                audits.append(
                    {
                        "session_key": key,
                        "role": o["role"],
                        "round_index": o["round_index"],
                        **select(audit, AUDIT_FIELDS),
                        "ranks": [select(rank, RANK_FIELDS) for rank in audit["ranks"]],
                    }
                )
                if o["role"] == "exploratory":
                    name = f"{key}/round-{o['round_index']:02d}.py"
                    entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                    entry.compress_type = zipfile.ZIP_DEFLATED
                    entry.external_attr = 0o644 << 16
                    archive.writestr(entry, implementation.read_bytes())
                    location = f"patch/exploration-candidates.zip!{name}"
                else:
                    location = f"patch/final/{key}.py"
                    shutil.copyfile(implementation, target / location)
                    s["selected_round"] = next(
                        r["round_index"]
                        for r in s["observations"]
                        if r["role"] == "exploratory"
                        and r["candidate_sha256"] == o["candidate_sha256"]
                    )
                    s["final_candidate_sha256"] = o["candidate_sha256"]
                candidates.append(
                    {
                        "session_key": key,
                        "role": o["role"],
                        "round_index": o["round_index"],
                        "file": location,
                        "sha256": digest(implementation),
                        "bytes": implementation.stat().st_size,
                    }
                )
            public["sessions"].append(s)
            usage_rows.append(
                {
                    "session_key": key,
                    "model": s["model"],
                    "knowledge": s["knowledge"],
                    "exploration_tokens": s["observations"][7]["cumulative_total_tokens"],
                    "final_stage_tokens": s["observations"][8]["round_total_tokens"],
                    "report_tail_tokens": s["post_measurement_reporting_tokens"],
                    **s["usage"],
                    "queue_seconds": s["queue_seconds"],
                    "allocation_process_seconds": s["allocation_process_seconds"],
                }
            )
    write(target / "results/summary.json", public)
    with (target / "results/measurements.jsonl.gz").open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
            for measurement in measurements:
                stream.write((json.dumps(measurement, separators=(",", ":")) + "\n").encode())
    csv_write(target / "results/rounds.csv", rows)
    csv_write(target / "results/session-usage.csv", usage_rows)
    csv_write(target / "patch/candidates.csv", candidates)
    write(
        target / "results/audit-extract.json",
        {"type": "selected fields from original audits", "attempts": audits},
    )
    public_plan = select(
        plan,
        (
            "schema_version campaign_id status frozen_at_utc task_id task_contract qualification "
            "rounds_per_session sessions execution_order round_definition final_definition "
            "source_revision source_hashes bundle_lock_sha256 execution_adapter "
            "runtime_observed measurement tolerance knowledge_sources_on common_sources "
            "knowledge_access_isolation forbidden_cross_session_sources "
            "collection_recovery token_accounting resource_accounting inference_limit"
        ).split(),
    )
    public_plan["publication_type"] = "redacted field extract; private launch configuration omitted"
    public_plan["allocation"] = select(
        plan["allocation"],
        (
            "gpus",
            "automatic",
            "inner_timeout_seconds",
            "allocation_timeout_seconds",
            "queue_bound_seconds",
        ),
    )
    public_plan["extension"] = select(
        extension,
        (
            "registered_at_utc base_plan_sha256 base_source_revision expected_session_count "
            "existing_session_keys rounds_per_session final_remeasurement execution_order "
            "unchanged prompt_change isolation interpretation"
        ).split(),
    )
    public_plan["extension"]["additional_conditions"] = [
        select(c, ("key", "label", "model", "thinking", "knowledge"))
        for c in extension["additional_conditions"]
    ]
    write(target / "plan/publication.json", public_plan)
    write(
        target / "plan/provenance.json",
        {
            "original_artifacts": originals,
            "omissions": [
                "Private connection settings, personal paths and identities, "
                "chat identifiers, raw session logs",
                "Raw rank calls and full original audits remain outside this repository",
                "Host-specific launchers and frozen dependency bytes "
                "are identified by source hashes only",
            ],
            "extracts_have_separate_hashes": True,
        },
    )
    for name in ("baseline.py", "oracle.py", "task.json", "TASK.md", "workload.py"):
        src = source / "common/task" / name
        assert digest(src) == plan["source_hashes"][f"task/{name}"]
        shutil.copyfile(src, target / "validator/task" / name)
    grader = source / "common/runner/grade.py"
    assert digest(grader) == plan["source_hashes"]["runner/grade.py"]
    shutil.copyfile(grader, target / "validator/runner/grade.py")
    shutil.copyfile(
        source / "results/comparison-overview.png", target / "results/comparison-overview.png"
    )
    files = {
        p.relative_to(target).as_posix(): digest(p)
        for p in sorted(target.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts and p.name != "integrity.json"
    }
    write(target / "plan/integrity.json", files)
    print(
        f"Extracted {len(measurements)} attempts and {len(candidates)} immutable source identities."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", required=True, type=Path, help="Authorized local campaign archive"
    )
    parser.add_argument("--output", type=Path, default=ROOT, help="Public bundle destination")
    args = parser.parse_args()
    build(args.source, args.output)
