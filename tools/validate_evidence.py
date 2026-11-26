"""Read-only inventory/layout/hash checks; never adjudicate campaign verdicts."""

import argparse
import hashlib
import json
import re
from pathlib import Path

if __package__:
    from . import optimization_records
    from .evidence_archives import normalize_manifest
    from .evidence_archives import read_json as read_archive_json
else:
    import optimization_records
    from evidence_archives import normalize_manifest
    from evidence_archives import read_json as read_archive_json

SEGMENTS = ("plan", "results", "patch", "validator")
REQUIRED = {
    "template": [f"{part}/README.md" for part in SEGMENTS],
    "campaign": list(SEGMENTS),
    "import": [f"{part}/README.md" for part in SEGMENTS],
    "archive": ["results", "patch"],
    "review": ["results/summary.json"],
    "optimization-records": ["README.md"],
}


def safe_path(root, name):
    if not isinstance(name, str) or not name or "\\" in name or ":" in name:
        raise ValueError("unsafe relative path")
    if any(part in ("", ".", "..") for part in name.split("/")):
        raise ValueError("unsafe relative path")
    path = root.joinpath(*name.split("/"))
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("path escapes its declared root")
    return path


def read_object(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value


def check_digest(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("expected a lowercase SHA-256 digest")


def verify_file(path, expected, size=None):
    check_digest(expected)
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != expected:
        raise ValueError("SHA-256 mismatch")
    if size is not None and path.stat().st_size != size:
        raise ValueError("byte count mismatch")


def validate_manifest(repo, bundle, entry, unavailable):
    path = safe_path(bundle, entry["path"])
    data = read_object(path)
    schema = entry["schema"]
    checked = 0
    if schema in ("bundle-sha256", "historical-sha256"):
        if not data:
            raise ValueError("empty hash manifest")
        mapping = entry.get("files", {})
        if schema == "historical-sha256" and set(mapping) != set(data):
            raise ValueError("historical path mapping must cover exactly the recorded files")
        for name, expected in data.items():
            local = safe_path(bundle, name)
            check_digest(expected)
            if schema == "historical-sha256":
                source = mapping[name]
                if set(source) == {"external"} and isinstance(source["external"], str):
                    if not source["external"].strip():
                        raise ValueError("external dependency needs an explanation")
                    unavailable.append(f"{bundle.name}/{entry['path']}: {name} (external source)")
                    continue
                if set(source) != {"local"}:
                    raise ValueError("historical file requires one local or external source")
                local = safe_path(repo, source["local"])
            verify_file(local, expected)
            checked += 1
    elif schema == "archive-sha256":
        # The campaign document owns the metadata. Inventory entries remain
        # pointers; validation never downloads or implies remote availability.
        if "schema_version" in data and "archive" in data:
            normalized = normalize_manifest(read_archive_json(path))
            if entry.get("field") != "archive":
                raise ValueError("versioned archive inventory must reference field archive")
            data = normalized
        if "field" in entry:
            data = data[entry["field"]]
        if not isinstance(data, dict):
            raise ValueError("expected an archive object")
        check_digest(data["sha256"])
        size = data["bytes"]
        if type(size) is not int or size < 0:
            raise ValueError("invalid archive byte count")
        artifact = safe_path(bundle, entry["artifact"])
        if "file" in data:
            safe_path(bundle, data["file"])
            if data["file"] != artifact.name:
                raise ValueError("archive filename disagrees with inventory")
        if artifact.exists():
            verify_file(artifact, data["sha256"], size)
            checked += 1
        else:
            unavailable.append(f"{bundle.name}/{entry['artifact']}: external archive unavailable")
    else:
        raise ValueError("unknown manifest schema")
    return checked


def validate_inventory(repo, inventory=None):
    repo = Path(repo).resolve()
    report = {"errors": [], "unavailable": [], "bundles": [], "checked_hashes": 0}
    errors, unavailable = report["errors"], report["unavailable"]
    try:
        inventory = read_object(inventory or repo / "tools/evidence_inventory.json")
        if inventory["version"] != 1 or not isinstance(inventory["bundles"], dict):
            raise ValueError("unsupported inventory version or bundle map")
        entries = inventory["bundles"]
        evidence = repo / "evidence"
        actual = {path.name for path in evidence.iterdir() if path.is_dir() or path.is_symlink()}
        if actual != set(entries):
            errors.append(
                "inventory directories differ: " + ", ".join(sorted(actual ^ set(entries)))
            )
        for name, entry in entries.items():
            try:
                if "/" in name:
                    raise ValueError("bundle name must be one directory")
                bundle = safe_path(evidence, name)
                kind = entry["kind"]
                if kind not in REQUIRED:
                    raise ValueError("unknown bundle kind")
                report["bundles"].append({"name": name, "kind": kind})
                if kind == "optimization-records":
                    if name != "records" or entry.get("manifests") != []:
                        raise ValueError("Expected a single dedicated optimization-records root")
                    optimization_records.regular(evidence, directory=True)
                    optimization_records.regular(bundle, directory=True)
                    optimization_records.regular(bundle / "README.md")
                    for record in sorted(bundle.iterdir()):
                        if record.name == "README.md":
                            continue
                        try:
                            _, files = optimization_records.load_record(record)
                            report["checked_hashes"] += len(files) - 1
                        except (OSError, ValueError, KeyError, TypeError) as exc:
                            record_name = record.name if re.fullmatch(
                                optimization_records.RECORD_ID, record.name
                            ) else "<invalid record name>"
                            errors.append(
                                f"records/{record_name}: invalid record ({type(exc).__name__})"
                            )
                    continue
                for required in REQUIRED[kind]:
                    target = safe_path(bundle, required)
                    present = target.is_dir() if required in SEGMENTS else target.is_file()
                    if not present:
                        errors.append(f"{name}: missing required {required}")
                manifests = entry["manifests"]
                if not isinstance(manifests, list):
                    raise ValueError("manifests must be a list")
                declared = [item["path"] for item in manifests]
                if len(set(declared)) != len(declared):
                    raise ValueError("duplicate manifest declaration")
                # Catch new manifests that have not yet received a schema decision.
                for path in bundle.rglob("*.json"):
                    safe_path(bundle, path.relative_to(bundle).as_posix())
                    json.loads(path.read_text(encoding="utf-8"))
                    if (
                        "manifest" in path.name
                        or path.name in (
                            "freeze.json", "frozen-compatibility.json", "artifacts.json"
                        )
                    ) and path.relative_to(bundle).as_posix() not in declared:
                        errors.append(f"{name}: unclassified manifest {path.relative_to(bundle)}")
                for manifest in manifests:
                    try:
                        if (
                            manifest["path"] == "results/artifacts.json"
                            and entry.get("external_assets")
                        ):
                            raise ValueError(
                                "external_assets duplicates authoritative artifacts.json"
                            )
                        report["checked_hashes"] += validate_manifest(
                            repo, bundle, manifest, unavailable
                        )
                    except (OSError, ValueError, KeyError, TypeError) as exc:
                        errors.append(
                            f"{name}: manifest {manifest.get('path', '?')}: "
                            f"{type(exc).__name__}: {exc}"
                        )
                external = entry.get("external", [])
                if not isinstance(external, list) or not all(
                    isinstance(item, str) and item.strip() for item in external
                ):
                    raise ValueError("external dependencies must be nonempty descriptions")
                unavailable.extend(f"{name}: {item}" for item in external)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                errors.append(f"{name}: {type(exc).__name__}: {exc}")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(f"inventory: {type(exc).__name__}: {exc}")
    return report


def budget_assets(repo):
    """Generate #328's legacy input shape from authority; do not persist a second index."""
    inventory = read_object(repo / "tools/evidence_inventory.json")
    bundles = {}
    for name, entry in inventory["bundles"].items():
        assets = []
        for manifest in entry["manifests"]:
            if manifest["path"] != "results/artifacts.json":
                continue
            path = safe_path(safe_path(repo / "evidence", name), manifest["path"])
            record = normalize_manifest(read_archive_json(path))["archive"]
            assets.append({
                key: record[key] for key in ("url", "sha256", "bytes", "retention_owner")
            })
        if assets:
            if entry.get("external_assets"):
                raise ValueError("external_assets duplicates authoritative artifacts.json")
            bundles[name] = {"external_assets": assets}
    return {"bundles": bundles}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--budget-assets", action="store_true",
                        help="Emit a derived, disposable external-assets view for the R6 checker")
    args = parser.parse_args()
    if args.budget_assets:
        try:
            print(json.dumps(budget_assets(args.root.resolve()), indent=2))
            return 0
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(json.dumps({"errors": [str(exc)]}))
            return 1
    report = validate_inventory(args.root)
    print(json.dumps(report, indent=2))
    return int(bool(report["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
