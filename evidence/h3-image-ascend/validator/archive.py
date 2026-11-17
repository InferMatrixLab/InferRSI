"""CPU-only archive verification and derived views for the H3 evidence pilot.

Never execute archived scripts or extract archive paths to the filesystem.
The published snapshot is the source of records; generated views are not a
campaign controller. This module does not adjudicate campaign acceptance.
"""

import argparse
import gzip
import hashlib
import io
import json
import math
import statistics
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path, PurePosixPath

PREFIX = "h3-image-ascend/"
MAX_ARCHIVE = 96 * 1024 * 1024
MAX_EXPANDED = 96 * 1024 * 1024
MAX_MEMBERS = 256
MAX_SECONDS = 120
CONFIG_KEYS = (
    "block",
    "layer",
    "tokens",
    "seq",
    "rank",
    "batch",
    "variant",
    "case",
    "mode",
    "dtype",
    "shape",
    "output_parts",
    "alignment",
    "padded_rows",
    "heads_per_batch",
    "padded_heads",
    "input_scale",
    "weight_group_size",
    "activation_groups",
    "correction_rank",
    "bf16_channels",
    "keep_ratio",
    "requested_keep_ratio",
    "round",
)
# These arrays describe observations within a trial, not separate trial executions.
OBSERVATIONS = {
    "checks",
    "quality_checks",
    "output_checks",
    "operators",
    "step_summary",
    "groups",
    "requests",
    "images",
    "reports",
    "warmup_requests",
}
EXTRA_ATTEMPTS = {
    "current-profile-round8.json": [("/analysis_validation", "execution_error")],
    "nz-load-order-diagnosis.json": [
        ("/round14", "execution_error"),
        ("/round15", "recorded"),
    ],
    "outlier-fc1-rejection.json": [
        ("/round17", "execution_error"),
        ("/round18", "recorded"),
    ],
    "nov14-component-search.json": [
        ("/initial_hccl_launch_failure", "execution_error"),
        ("/persistent_pack/termination", "interrupted"),
    ],
    "nov14-native-attention-followup.json": [("/failed_attempt", "execution_error")],
}


class VerificationError(ValueError):
    """A named verification gap, distinct from experimental acceptance."""


def require(condition, reason):
    if not condition:
        raise VerificationError(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_name(name):
    require(isinstance(name, str) and bool(name), "unsafe_archive_path")
    parts = name.split("/")
    require(
        not PurePosixPath(name).is_absolute()
        and not any(p in ("", ".", "..") for p in parts)
        and "\\" not in name
        and ":" not in name,
        "unsafe_archive_path",
    )


class LimitedStream:
    """Bound decompression, including metadata consumed internally by tarfile."""

    def __init__(self, stream, started):
        self.stream, self.started, self.read_bytes = stream, started, 0

    def read(self, size):
        require(time.monotonic() - self.started < MAX_SECONDS, "archive_time_limit")
        data = self.stream.read(min(size, MAX_EXPANDED - self.read_bytes + 1))
        self.read_bytes += len(data)
        require(self.read_bytes <= MAX_EXPANDED, "archive_expansion_limit")
        return data


def read_archive(path, manifest):
    """Authenticate compressed bytes before bounded, in-memory decompression."""
    started = time.monotonic()
    spec = manifest["archive"]
    require(0 < spec["bytes"] <= MAX_ARCHIVE, "archive_size_limit")
    require(path.stat().st_size == spec["bytes"], "archive_byte_count_mismatch")
    with path.open("rb") as stream:
        payload = stream.read(MAX_ARCHIVE + 1)
    require(len(payload) == spec["bytes"], "archive_byte_count_mismatch")
    require(digest(payload) == spec["sha256"], "archive_sha256_mismatch")
    members = {}
    expanded = 0
    with (
        gzip.GzipFile(fileobj=io.BytesIO(payload)) as expanded_stream,
        tarfile.open(fileobj=LimitedStream(expanded_stream, started), mode="r|") as archive,
    ):
        for member in archive:
            require(time.monotonic() - started < MAX_SECONDS, "archive_time_limit")
            safe_name(member.name)
            require(member.isfile() and not member.issparse(), "unsupported_archive_member")
            require(member.name not in members, "duplicate_archive_member")
            require(len(members) < MAX_MEMBERS, "archive_member_limit")
            expanded += member.size
            require(0 <= member.size and expanded <= MAX_EXPANDED, "archive_expansion_limit")
            stream = archive.extractfile(member)
            data = stream.read(member.size + 1)
            require(len(data) == member.size, "truncated_archive_member")
            members[member.name] = data
    require("snapshot.json" in members, "missing_snapshot")
    snapshot = json.loads(members.pop("snapshot.json"))
    require(snapshot["source_revision"] == manifest["source_revision"], "source_mismatch")
    require(set(members) == {PREFIX + p for p in snapshot["files"]}, "file_coverage_mismatch")
    for name, identity in snapshot["files"].items():
        safe_name(name)
        data = members[PREFIX + name]
        require(
            len(data) == identity["bytes"] and digest(data) == identity["sha256"],
            "snapshot_file_mismatch: " + name,
        )
    files = {name.removeprefix(PREFIX): data for name, data in members.items()}
    frozen = json.loads(files["export-manifest.json"])
    require(set(frozen) == set(files) - {"export-manifest.json"}, "frozen_export_coverage")
    for name, expected in frozen.items():
        require(digest(files[name]) == expected, "frozen_export_hash: " + name)
    require(len(files) == spec["original_files"], "original_file_count_mismatch")
    require(sum(map(len, files.values())) == spec["original_bytes"], "original_byte_count_mismatch")
    return files


class HTTPSRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        require(newurl.startswith("https://"), "non_https_redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(manifest, destination):
    spec = manifest["archive"]
    require(
        spec["url"].startswith("https://github.com/InferMatrixLab/InferRSI/releases/download/"),
        "unsupported_archive_url",
    )
    require(0 < spec["bytes"] <= MAX_ARCHIVE, "archive_size_limit")
    started = time.monotonic()
    try:
        with (
            urllib.request.build_opener(HTTPSRedirects()).open(spec["url"], timeout=30) as response,
            destination.open("xb") as sink,
        ):
            received = 0
            while block := response.read(1024 * 1024):
                received += len(block)
                require(received <= spec["bytes"], "download_size_limit")
                require(time.monotonic() - started < MAX_SECONDS, "download_time_limit")
                sink.write(block)
    except urllib.error.HTTPError as exc:
        reason = "restricted_access" if exc.code in (401, 403) else "archive_unavailable"
        raise VerificationError(reason) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise VerificationError("download_unavailable") from exc


def pointer(value, path):
    for part in path.split("/")[1:]:
        key = part.replace("~1", "/").replace("~0", "~")
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def stats(samples):
    require(
        bool(samples)
        and all(
            isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x >= 0
            for x in samples
        ),
        "invalid_timing_samples",
    )
    return {
        "n": len(samples),
        "median": statistics.median(samples),
        "min": min(samples),
        "max": max(samples),
    }


def walk(value, path=""):
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk(child, path + "/" + key.replace("~", "~0").replace("/", "~1"))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from walk(child, path + "/" + str(i))


def measurements(value):
    timings, quality = {}, {}
    for path, node in walk(value):
        if isinstance(node, dict) and "samples_s" in node:
            computed = stats(node["samples_s"])
            require(computed["median"] == node["median_s"], "historical_median_mismatch")
            timings[path] = {
                **computed,
                "target_s": node["target_s"],
                "target_met": computed["median"] <= node["target_s"],
            }
            require(timings[path]["target_met"] == node["target_met"], "target_result_mismatch")
        if (
            isinstance(node, list)
            and node
            and isinstance(node[0], dict)
            and (
                "numerical_screen_pass" in node[0] or ("exact" in node[0] and "workload" in node[0])
            )
        ):
            flags = [c.get("numerical_screen_pass", c.get("exact")) for c in node]
            quality[path] = {
                "checks": len(node),
                "passed": sum(f is True for f in flags),
                "failed": sum(f is False for f in flags),
                "exact": sum(c.get("exact") is True for c in node),
                "min_finite_psnr_db": min(
                    (c["psnr_db"] for c in node if c.get("psnr_db") is not None), default=None
                ),
                "min_ssim": min((c["ssim"] for c in node if "ssim" in c), default=None),
            }
    return {"http_seconds": timings, "recorded_image_checks": quality}


def component_rows(value, path=""):
    if isinstance(value, list):
        for i, row in enumerate(value):
            if isinstance(row, dict):
                yield path + "/" + str(i), row
    elif isinstance(value, dict):
        for key, child in value.items():
            if key in OBSERVATIONS or key in {"latency", "quality", "source", "screen"}:
                continue
            child_path = path + "/" + key
            if isinstance(child, list) and child and isinstance(child[0], dict):
                # Timing repetitions belong to their containing component case.
                if key in {
                    "samples",
                    "cases",
                    "completed_cases",
                    "experiments",
                    "failed_attempts",
                } or (any(k in child[0] for k in CONFIG_KEYS) and "samples_ms" not in child[0]):
                    yield from component_rows(child, child_path)
            elif isinstance(child, dict):
                yield from component_rows(child, child_path)


def trial(file, path, value, kind, status=None):
    row = {
        "id": file.removeprefix("results/").removesuffix(".json") + "#" + path,
        "kind": kind,
        "status": status or "recorded",
    }
    if not isinstance(value, dict):
        row["result"] = value
        return row
    row["config"] = {k: value[k] for k in CONFIG_KEYS if k in value}
    for key in ("execution_status", "status"):
        if key in value:
            row["status"] = value[key]
    if any(k in value for k in ("reason", "observation", "observed")):
        row["result"] = value.get("reason", value.get("observation", value.get("observed")))
    elif "exact" in value:
        row["result"] = "exact" if value["exact"] else "numerical_difference"
    elif "psnr_db" in value:
        row["result"] = "recorded_image_score"
    else:
        row["result"] = value.get("decision", value.get("verdict", "see source record"))
    timing = {}
    for key, child in value.items():
        groups = child if isinstance(child, list) else [child]
        if groups and all(isinstance(g, dict) and "samples_ms" in g for g in groups):
            timing[key] = [stats(g["samples_ms"]) for g in groups]
        elif isinstance(child, list) and child and key.endswith("_ms"):
            timing[key] = [stats(child)]
    if timing:
        row["timing_ms"] = timing
        row["status"] = status or "measured"
    quality = {k: value[k] for k in ("psnr_db", "ssim", "relative_rmse") if k in value}
    if quality:
        row["quality_metrics"] = quality
    return row


def build_views(files, manifest):
    """Derive every published case/attempt; retain repeated cases by source offset."""
    rows, groups, support = [], {}, []
    support_names = {
        "request-measurements.json",
        "source-context.json",
        "source-manifest.json",
        "quality-screen.json",
        "exact-quality.json",
        "quality.json",
        "quality-summary.json",
        "images.json",
        "decision.json",
    }
    for file, payload in sorted(files.items()):
        if not file.startswith("results/") or not file.endswith(".json"):
            continue
        value = json.loads(payload)
        if Path(file).name in support_names:
            support.append(file)
            continue
        group = file.removeprefix("results/").removesuffix(".json")
        metadata_keys = (
            "scope",
            "decision",
            "conclusion",
            "purpose",
            "candidate",
            "change",
            "source",
            "base_revision",
            "engine_revision",
            "configuration",
            "workload_protocol",
            "measurement_limits",
            "limitations",
            "provenance_limit",
            "provenance_correction",
            "cache_disclosure",
            "adopted",
            "verdict",
            "observed",
            "cause",
            "lifecycle",
            "server_exit_codes",
            "service_exit_codes",
            "runtime_receipt",
        )
        metadata = (
            {k: value[k] for k in metadata_keys if k in value} if isinstance(value, dict) else {}
        )
        groups[group] = {"record": file, **metadata, **measurements(value)}
        findings = {
            path: node
            for path, node in walk(value)
            if isinstance(node, str)
            and path.rsplit("/", 1)[-1]
            in {"finding", "decision", "termination", "interpretation", "performance"}
        }
        if findings:
            groups[group]["findings"] = findings
        directory = file.rsplit("/", 1)[0]
        if Path(file).name.endswith("summary.json"):
            rows.append(trial(file, "", value, "http_run"))
            requests_path = directory + "/request-measurements.json"
            if requests_path in files:
                requests = json.loads(files[requests_path])
                for workload, metrics in value["workloads"].items():
                    samples = [
                        r["latency_s"]
                        for r in requests
                        if r["workload"] == workload and not r["warmup"]
                    ]
                    require(samples == metrics["samples_s"], "request_summary_mismatch")
                groups[group]["requests"] = {
                    "total": len(requests),
                    "warmup": sum(r["warmup"] for r in requests),
                    "failed": sum(not r["complete"] or r["http_status"] != 200 for r in requests),
                }
            else:
                groups[group]["requests"] = {
                    "total": value["requests"],
                    "expected": value["expected_requests"],
                    "complete": value["evidence"]["requests_complete"],
                    "error": value["error"],
                }
            for name in (
                "quality-summary.json",
                "quality-screen.json",
                "exact-quality.json",
                "quality.json",
                "decision.json",
            ):
                sibling = directory + "/" + name
                if sibling in files and not Path(file).name.startswith("control-"):
                    data = json.loads(files[sibling])
                    groups[group][name] = data if name == "decision.json" else measurements(data)
        elif isinstance(value, dict) and "latency" in value:
            rows.append(trial(file, "", value, "http_comparison"))
            if "screen" in value:
                rows.append(trial(file, "/screen", value["screen"], "image_screen"))
        else:
            cases = list(component_rows(value))
            for path, item in cases:
                failed = path.startswith("/failed_attempts") or "execution_status" in item
                rows.append(
                    trial(
                        file,
                        path,
                        item,
                        "execution_attempt" if failed else "component_case",
                        "execution_error" if path.startswith("/failed_attempts") else None,
                    )
                )
            if not cases and Path(file).name not in EXTRA_ATTEMPTS:
                kind = "validation_record" if "checks" in Path(file).name else "diagnostic"
                failure = Path(file).name == "mlp-nz-startup-failure.json"
                rows.append(
                    trial(
                        file,
                        "",
                        value,
                        "execution_attempt" if failure else kind,
                        "execution_error" if failure else None,
                    )
                )
            for path, status in EXTRA_ATTEMPTS.get(Path(file).name, []):
                rows.append(trial(file, path, pointer(value, path), "execution_attempt", status))
            if Path(file).name == "current-profile-round8.json":
                rows.append(trial(file, "", value, "diagnostic"))
    require(len({r["id"] for r in rows}) == len(rows), "duplicate_trial_id")
    summary = {
        "schema_version": 1,
        "source_revision": manifest["source_revision"],
        "campaign_verdict": "INCONCLUSIVE",
        "scope": (
            "Derived from the complete published export; unavailable private runs are not inferred."
        ),
        "metric_definition": "HTTP POST start through complete response receipt; warmups excluded.",
        "comparison": (
            "Exact JSON equality for derived views and integer counts; "
            "archived HTTP medians exactly match recomputation."
        ),
        "quality_limit": (
            "Counts/extrema recomputed from recorded screens, "
            "not PSNR/SSIM rerun from unavailable images."
        ),
        "coverage": {
            "indexed_records": len(rows),
            "kinds": dict(Counter(r["kind"] for r in rows)),
            "statuses": dict(Counter(r["status"] for r in rows)),
            "support_records": support,
        },
        "groups": groups,
    }
    return summary, rows


def verify_views(files, manifest, bundle, write=False):
    safe_name(manifest["retained_files"])
    retained = json.loads((bundle / manifest["retained_files"]).read_text())
    for path, expected in retained.items():
        safe_name(path)
        require(
            digest(files[path]) == expected and digest((bundle / path).read_bytes()) == expected,
            "retained_file_mismatch: " + path,
        )
    summary, rows = build_views(files, manifest)
    summary_path = bundle / "results/summary.json"
    trials_path = bundle / "results/trials.jsonl"
    if write:
        summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        trials_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    else:
        require(json.loads(summary_path.read_text()) == summary, "summary_recomputation_mismatch")
        require(
            [json.loads(line) for line in trials_path.read_text().splitlines()] == rows,
            "trial_coverage_or_content_mismatch",
        )
    return summary["coverage"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--archive", type=Path, help="Verify an already downloaded archive")
    inputs.add_argument("--download", action="store_true", help="Explicit network verification")
    parser.add_argument(
        "--write", action="store_true", help="Regenerate only summary and trial index"
    )
    args = parser.parse_args()
    bundle = Path(__file__).resolve().parents[1]
    manifest = json.loads((bundle / "results/artifacts.json").read_text())
    try:
        with tempfile.TemporaryDirectory(prefix="h3-evidence-") as directory:
            archive = args.archive or Path(directory) / "archive.tar.gz"
            if args.download:
                download(manifest, archive)
            files = read_archive(archive, manifest)
            coverage = verify_views(files, manifest, bundle, write=args.write)
        print(
            json.dumps(
                {
                    "archive_content": "verified",
                    "original_files": len(files),
                    "derived_views": "written" if args.write else "matched",
                    **coverage,
                    "campaign_verdict": "INCONCLUSIVE",
                },
                indent=2,
            )
        )
    except (VerificationError, OSError, ValueError, KeyError, TypeError, tarfile.TarError) as exc:
        print(
            json.dumps(
                {
                    "archive_verification": "incomplete",
                    "reason": str(exc),
                    "campaign_verdict": "INCONCLUSIVE",
                }
            )
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
