"""Export retained experiment results; never execute, recover, select or assess."""

import errno
import hashlib
import time
import uuid
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory

from ... import __version__
from ..artifacts import file_lock
from ..storage import archive
from . import adapters
from .projection import iterative
from .render import reports
from .schema import INDEX_ID, decode, empty_result, encode, gap, timestamp, validate_result
from .snapshot import Snapshot, SnapshotBusy, SnapshotChanged, relative_path


def _safe_root(path):
    path = Path(path).absolute()
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError("Delivery paths cannot traverse symbolic links")
    return path


def _project(source, export_id, observed_at, agent_job=None):
    root = source if source.is_dir() else source.parent
    snapshot = Snapshot(root, timestamp(observed_at))
    result = empty_result(export_id, observed_at, __version__)
    name = source.name if source.is_file() else None
    if name is None and snapshot.path("state.json").exists():
        iterative(snapshot, result)
    elif name is None and snapshot.path("run.lock.json").exists():
        adapters.legacy(snapshot, result)
    else:
        if name is None:
            name = next(
                (
                    candidate
                    for candidate in ("result.json", "summary.json")
                    if snapshot.path(candidate).exists()
                ),
                None,
            )
        if name is None:
            raise ValueError("No supported retained records; supply a campaign, run or record JSON")
        document, _ = snapshot.object(name, "source_record", required=True)
        if document.get("kind") == "external_optimization_record":
            adapters.external(snapshot, result, name)
        elif "operation" in document:
            adapters.operation(snapshot, result, name)
        elif name == "summary.json":
            adapters.summary(snapshot, result, name)
        else:
            raise ValueError("Unsupported source record schema")
    if agent_job is not None:
        from .benchmark_usage import attach_native_usage

        attach_native_usage(snapshot, result, _safe_root(agent_job))
    # The archive authority stays opaque and canonical. The bundle points to it;
    # it does not fork archive URLs, sizes, ownership or availability observations.
    authority = snapshot.path("results/artifacts.json")
    authority_ref = None
    if authority.exists():
        authority_ref = snapshot.file("results/artifacts.json", "archive_authority")
        result["sources"].append(
            {
                "artifact_ref": authority_ref,
                "type": "archive_authority",
                "revision": snapshot.entries[authority_ref]["source_revision"],
            }
        )
    # Include the negative lookup in the stability check, too.
    else:
        snapshot.file("results/artifacts.json", "optional_archive_authority")
        snapshot.entries.pop("source:results/artifacts.json")
    for entry in snapshot.entries.values():
        if entry["availability"] != "available" or entry["integrity"] != "verified":
            gap(
                result,
                "EVIDENCE_UNVERIFIED",
                entry["id"],
                f"{entry['location']}: availability={entry['availability']}, "
                f"integrity={entry['integrity']}; historical assessment is retained separately",
            )
    for key in ("baseline", "selected_candidate", "metrics", "checks", "rounds"):
        if result[key] is None:
            gap(result, "NOT_RECORDED", key, f"{key} is not established by this source adapter")
    if result["campaign"].get("goal") is None:
        gap(
            result,
            "GOAL_NOT_RECORDED",
            "campaign.goal",
            "No structured goal was recorded; consult the frozen instructions when available",
        )
    for key, usage in result["usage"].items():
        if usage["coverage"] != "complete":
            gap(
                result,
                "USAGE_COVERAGE",
                "usage." + key,
                f"{key} coverage is {usage['coverage']}; unknown observations are not zero",
            )
    validate_result(result)
    return snapshot, result, authority_ref


def project(source: Path, *, export_id: str, observed_at=None, agent_job=None):
    """Read a committed snapshot or fail explicitly; no live summary is authoritative.

    Harness writers hold .session.lock across their operation. A busy writer
    yields an explicit retryable error. Two digest passes additionally detect
    uncoordinated edits to historical/external source files, with three attempts.
    The observation cutoff is fixed across retries.
    """
    source = _safe_root(source)
    if not source.exists():
        raise ValueError("Delivery input does not exist")
    observed_at = time.time() if observed_at is None else observed_at
    root = source if source.is_dir() else source.parent
    managed = source.is_dir() and (root / "state.json").exists()
    lock = _safe_root(root / ".session.lock")
    for _ in range(3):
        try:
            with file_lock(lock) if managed else nullcontext():
                snapshot, result, authority_ref = _project(
                    source, export_id, observed_at, agent_job)
                if snapshot.stable():
                    return snapshot, result, authority_ref
        except SnapshotChanged:
            continue
        except BlockingIOError:
            raise SnapshotBusy(
                "Optimization writer is active; retry after its attempt commits"
            ) from None
    raise SnapshotChanged("Source changed during export; no consistent snapshot could be read")


def read_bundle(directory: Path):
    """Validate published entry files without fetching or executing any source reference."""
    directory = _safe_root(directory)
    index = decode(_safe_root(directory / "artifacts.json").read_bytes())
    if (
        index.get("schema_id") != INDEX_ID
        or type(index.get("schema_version")) is not int
        or index["schema_version"] != 1
    ):
        raise ValueError("Unsupported delivery artifact index")
    entries = index.get("artifacts", [])
    if len({entry["id"] for entry in entries}) != len(entries):
        raise ValueError("Duplicate delivery artifact ID")
    bundled = {}
    for entry in entries:
        if entry["location_kind"] == "source":
            relative_path(entry["location"])
            if entry.get("source_root") is not None:
                archive.validate_output_id(entry["source_root"])
        if entry["location_kind"] != "bundle":
            continue
        name = entry["location"]
        if name in bundled:
            raise ValueError("Duplicate delivery bundle location")
        bundled[name] = entry
    if set(bundled) != {"report.md", "report.html", "campaign-result.json"}:
        raise ValueError("Incomplete delivery bundle")
    for name, entry in bundled.items():
        raw = _safe_root(directory / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry["sha256"] or len(raw) != entry["size_bytes"]:
            raise ValueError("Delivery file integrity mismatch")
    result = decode((directory / "campaign-result.json").read_bytes())
    validate_result(result)
    if result["export"]["id"] != index["export_id"]:
        raise ValueError("Delivery export IDs disagree")
    identities = {entry["id"] for entry in entries}
    if any(source.get("artifact_ref") not in identities for source in result["sources"]):
        raise ValueError("Delivery source does not resolve in its artifact index")
    return result


def export_bundle(source: Path, output: Path, *, export_id=None, agent_job=None):
    """Publish a new four-file bundle atomically, preserving existing destinations."""
    export_id = export_id or uuid.uuid4().hex
    archive.validate_output_id(export_id)
    output = _safe_root(output)
    published = False
    result = None
    try:
        if output.exists():
            raise FileExistsError(errno.EEXIST, "Delivery destination already exists")
        snapshot, result, authority_ref = project(source, export_id=export_id, agent_job=agent_job)
        data = encode(result)
        markdown, html = reports(result, hashlib.sha256(data).hexdigest())
        files = {"campaign-result.json": data, "report.md": markdown, "report.html": html}
        entries = list(snapshot.entries.values())
        for name, raw in files.items():
            entries.append(
                {
                    "id": "bundle:" + name,
                    "role": "report" if name.startswith("report") else "result",
                    "location": name,
                    "location_kind": "bundle",
                    "media_type": {
                        "report.md": "text/markdown",
                        "report.html": "text/html",
                        "campaign-result.json": "application/json",
                    }[name],
                    "size_bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "source_revision": export_id,
                    "availability": "available",
                    "integrity": "verified",
                    "checked_at": result["export"]["generated_at"],
                    "access": "Bundled file",
                }
            )
        files["artifacts.json"] = encode(
            {
                "schema_id": INDEX_ID,
                "schema_version": 1,
                "export_id": export_id,
                "archive_authority_ref": authority_ref,
                "archive_metadata_policy": "Archive metadata is canonical only in the referenced "
                "campaign results/artifacts.json; this index does not duplicate it "
                "or check remote bytes",
                "artifacts": entries,
            }
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".delivery-", dir=output.parent) as temporary:
            staging = Path(temporary)
            for name, raw in files.items():
                archive._write_file(staging / name, raw)
            read_bundle(staging)
            archive._sync_directory(staging)
            archive._sync_directory(output.parent)
            archive._publish_directory(staging, output)
            published = True
            archive._sync_directory(output.parent)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        # In particular a post-rename sync error keeps the same export ID and
        # visible destination so callers can reconcile instead of remeasuring.
        return {
            "status": "uncertain" if published else "error",
            "export_id": export_id,
            "output": str(output),
            "error": str(error)
            if isinstance(error, (SnapshotBusy, SnapshotChanged))
            else archive._publication_message(error, published=published),
            "execution_preserved": True,
            "reconcile": "Read this output with read_bundle before retrying" if published else None,
        }
    return {
        "status": "published",
        "export_id": export_id,
        "output": str(output),
        "conclusion": {
            "completion": result["completion"],
            "outcome": result["outcome"],
            "acceptance": result["acceptance"],
        },
        "report_md": str(output / "report.md"),
        "report_html": {"path": str(output / "report.html"), "label": "Open in a browser"},
        "result": str(output / "campaign-result.json"),
        "artifacts": str(output / "artifacts.json"),
        "selected_code": result["selected_candidate"],
        "benchmark_metrics": result.get("benchmark_metrics"),
    }


def after_final(args, result):
    """Keep execution outcome and report publication outcome independent."""
    if args.session_action != "final":
        return result
    export_id = uuid.uuid4().hex
    # The exporter refuses symlinked ancestors; Harness already resolved this session.
    session = args.session.resolve()
    output = session / "delivery" / export_id
    try:
        delivery = export_bundle(session, output, export_id=export_id)
    except Exception:
        # Presentation failure must never change the already committed execution outcome.
        delivery = {
            "status": "error",
            "export_id": export_id,
            "output": str(output),
            "execution_preserved": True,
            "error": "Report generation failed; export retained records again",
        }
    return {**result, "delivery": delivery}
