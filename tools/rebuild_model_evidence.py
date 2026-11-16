"""Rebuild compact published-record views from an explicitly verified archive.

This indexes published observations, including revisions of the same attempt.
It cannot reconstruct unpublished controller records or qualify model behavior.
Projection rules and original files are authenticated inputs, never executed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import Counter
from pathlib import Path

if __package__:
    from . import evidence_archives as archive
else:
    import evidence_archives as archive


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def pointer(value, path):
    for part in path.removeprefix("/").split("/") if path else ():
        part = part.replace("~1", "/").replace("~0", "~")
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def walk(value, path=""):
    if isinstance(value, dict):
        yield path, value
        for key, child in value.items():
            escaped = key.replace("~", "~0").replace("/", "~1")
            yield from walk(child, path + "/" + escaped)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, path + "/" + str(index))


def attempt_identity(value):
    for key in ("trial", "native_run_id", "run", "job_id", "job"):
        item = value.get(key)
        if type(item) in (str, int) and str(item).strip():
            return f"{key}:{item}"
    return None


def status(value):
    for path in (
        "/status", "/run_state", "/scheduler_state", "/slurm_state", "/state",
        "/execution", "/model_controller/status", "/scheduler/JobState",
    ):
        try:
            result = pointer(value, path)
        except (KeyError, TypeError):
            continue
        if isinstance(result, str) and result:
            return result
    return "recorded"  # Missing execution status never implies completion.


def conclusion(value):
    fields = ("campaign_verdict", "verdict", "quality_verdict", "duration_verdict",
              "native_verdict", "decision", "scope")
    result = {key: value[key] for key in fields if isinstance(value.get(key), str)}
    return canonical(result) if result else "INCONCLUSIVE: no standalone verdict recorded"


def build_index(originals, projection, artifact_id):
    rows, sources = {}, []
    for name, payload in sorted(originals.items()):
        if not name.startswith("results/") or not name.endswith(".json"):
            continue
        if name in projection["integrity_manifests"]:
            continue
        document = archive.parse_json(payload)
        sources.append(name)
        for offset, value in walk(document):
            identity = attempt_identity(value)
            # Whole published reports remain discoverable even without an attempt
            # ID. Explicit attempt collections also retain anonymous failures.
            collection = offset.rsplit("/", 1)[0].rsplit("/", 1)[-1]
            if (offset and identity is None
                    and collection not in ("runs", "attempts", "gpu_attempts")):
                continue
            ref = projection["campaign"] + "/" + name + "#" + offset
            digest = hashlib.sha256(canonical(value).encode()).hexdigest()
            # Only repeated observations of the SAME named attempt collapse.
            # Revisions with different bytes, retries, and anonymous records stay.
            key = (identity or ref, digest)
            if key in rows:
                rows[key]["source_records"].append(ref)
                continue
            row_id = hashlib.sha256(canonical(key).encode()).hexdigest()
            rows[key] = {
                "id": row_id,
                "kind": "attempt_observation" if identity else "published_record",
                "identity": identity,
                "configuration": {
                    "record_sha256": digest,
                    "campaign_records": [projection["campaign"] + "/" + name
                                         for name in projection["configuration"]],
                },
                "status": status(value),
                "conclusion": conclusion(value),
                "artifact_id": artifact_id,
                "source_record": ref,
                "source_records": [ref],
            }
    return sorted(rows.values(), key=lambda row: row["id"]), sources


def distribution(samples):
    archive.require(
        isinstance(samples, list) and bool(samples)
        and all(type(n) in (int, float) and math.isfinite(n) for n in samples),
        "recompute_mismatch", "Expected a nonempty finite measurement group",
    )
    return {"count": len(samples), "min": min(samples), "max": max(samples),
            "median": statistics.median(samples), "mean": statistics.mean(samples),
            "stdev": statistics.stdev(samples) if len(samples) > 1 else None}


def build_views(originals, projection, manifest):
    def read(spec):
        return pointer(archive.parse_json(originals[spec["path"]]), spec.get("pointer", ""))

    rows, sources = build_index(originals, projection, manifest["archive"]["id"])
    metrics = {}
    for spec in projection["metrics"]:
        samples = read(spec)
        if "field" in spec:
            samples = [row[spec["field"]] for row in samples
                       if all(row[key] == value for key, value in spec.get("where", {}).items())]
        metrics[spec["name"]] = {"source": spec, "distribution": distribution(samples)}
    summary = {
        "schema_version": 2,
        "source_revision": manifest["archive"]["source_revision"],
        "artifact_id": manifest["archive"]["id"],
        "campaign_verdict": read(projection["verdict"]),
        "coverage": {
            "original_files": len(originals),
            "original_bytes": sum(map(len, originals.values())),
            "indexed_result_documents": sources,
            "index_entries": len(rows),
            "named_attempt_identities": len({r["identity"] for r in rows if r["identity"]}),
            "record_occurrences": sum(len(r["source_records"]) for r in rows),
            "status_counts": dict(sorted(Counter(r["status"] for r in rows).items())),
            "unit": "published record/attempt observation; not a count of independent trials",
        },
        "recomputed_metrics": metrics,
        "recorded_results": [
            {"source": spec, "value": read(spec)} for spec in projection["recorded_results"]
        ],
        "limitations": projection["limitations"],
    }
    return summary, rows


def replay(manifest, source):
    contents = {}
    archive.verify_archive(source, manifest, capture=contents)
    keys = manifest["archive"]["key_files"]
    snapshot = archive.parse_json(contents[keys["snapshot"]])
    projection = archive.parse_json(contents[keys["projection"]])
    root = manifest["archive"]["root"]
    archive.require(projection["campaign"] == root, "metadata", "Projection campaign mismatch")
    archive.require(snapshot["source_revision"] == manifest["archive"]["source_revision"],
                    "metadata", "Snapshot source mismatch")
    originals = {name[len(root) + 1:]: data for name, data in contents.items()
                 if name.startswith(root + "/")}
    archive.require(set(originals) == set(snapshot["files"]), "missing_file",
                    "Original snapshot membership differs")
    for name, data in originals.items():
        archive.require(hashlib.sha256(data).hexdigest() == snapshot["files"][name],
                        "bad_hash", "Original file differs from frozen snapshot")
    # Bind the code actually used for regeneration, without executing a script
    # retrieved from the archive. The manifest pins these same archive members.
    for script in (Path(__file__), Path(archive.__file__)):
        archive.require(contents["replay/" + script.name] == script.read_bytes(),
                        "bad_hash", "Use the replay implementation pinned by this archive")
    for name in projection["integrity_manifests"]:
        mapping = archive.parse_json(originals[name])
        for path, expected in mapping.items():
            archive.require(path in originals, "missing_file", "Frozen manifest target missing")
            archive.require(hashlib.sha256(originals[path]).hexdigest() == expected,
                            "bad_hash", "Frozen integrity check failed")
    return build_views(originals, projection, manifest)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path,
                        help="New directory, separate from retained results")
    args = parser.parse_args(argv)
    try:
        manifest = archive.normalize_manifest(archive.read_json(args.manifest))
        summary, rows = replay(manifest, args.archive)
        # Refuse any existing destination, including the retained evidence tree.
        args.output.mkdir(parents=True, exist_ok=False)
        results = args.output / "results"
        results.mkdir()
        (results / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        (results / "trials.jsonl").write_text("".join(canonical(row) + "\n" for row in rows))
        print(json.dumps({"recomputed_index_entries": len(rows),
                          "campaign_verdict": summary["campaign_verdict"]}))
        return 0
    except (archive.VerificationError, OSError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"verification": "failed", "failure": getattr(exc, "code", "replay"),
                          "campaign_verdict": "unchanged"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
