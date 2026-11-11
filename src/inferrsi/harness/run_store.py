from __future__ import annotations

import copy
import errno
import hashlib
import io
import os
import re
import sqlite3
import uuid
from collections.abc import Iterable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from inferrsi import _json_v1
from inferrsi.harness.errors import PartialExecutionFacts, PublicError

if os.name == "nt":
    import msvcrt
else:
    import fcntl

# H-owned local SQLite RunStore v1 (D012-r2). One root is one independent idempotent
# namespace; nothing here claims exactly-once across roots or for external side effects.
STORE_FORMAT = "inferrsi-harness-run-store@1"
INDEX_NAME = "index.sqlite3"
RECORD_MEDIA_TYPE = "application/json"
CONTROLLER_SOURCE = "harness-run-store"
PHASES = (
    "registered", "preparing", "running", "stopping", "finalizing", "finished",
    "recovery_required",
)
# Exact ExecutionRecordPayload fields; record_ref/observed_at/controller_observation stay
# outside the payload (V15).
PAYLOAD_FIELDS = frozenset(
    {
        "schema_version", "request_id", "run_id", "attempt_id", "request_digest", "owner",
        "target_request", "target_binding", "retry_of", "retry_reason", "generation_record_ref",
        "prepared_ref", "protocol_digest", "operation", "validation_scope", "candidate",
        "record_version", "recorded_at", "bound_inputs", "phase", "started",
        "side_effect_unknown", "process_outcome", "exit_code", "elapsed_seconds", "steps",
        "cancellation", "cleanup", "artifacts", "checks", "budget_admission", "usage",
        "resource_leases", "errors",
    }
)
_TARGET_FIELDS = frozenset({"target_id", "executor_kind", "config_revision"})
_RESOURCE_FIELDS = frozenset({"cpu_count", "memory_bytes", "required_capabilities"})
_BUDGET_FIELDS = frozenset(
    {"policy_ref", "scope_id", "declared_by", "dimensions", "required_enforcement"}
)
_ARTIFACT_REF_FIELDS = frozenset({"location", "sha256", "size_bytes", "media_type"})
_MOUNT_FIELDS = frozenset({"prefix", "kind", "root", "namespace"})
_NAMESPACE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", re.ASCII)
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}", re.ASCII)
_TIMESTAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,9})?Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}", re.ASCII)
_RECORD_REST = re.compile(r"attempts/([0-9a-f]{64})/records/([1-9][0-9]{0,15})\.json", re.ASCII)
_OBJECT_REST = re.compile(r"objects/([0-9a-f]{2})/([0-9a-f]{64})", re.ASCII)
# Errno values meaning "another handle holds the lock" for msvcrt.locking and flock.
_CONTENDED = frozenset({errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK, errno.EDEADLK})
_CHUNK = 1024 * 1024

_STATES = ", ".join(f"'{phase}'" for phase in PHASES)
_SCHEMA = (
    "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    "CREATE TABLE attempts ("
    "request_id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL UNIQUE, "
    "attempt_hash TEXT NOT NULL UNIQUE, request_digest TEXT NOT NULL, run_id TEXT NOT NULL, "
    f"owner_session TEXT NOT NULL, state TEXT NOT NULL CHECK (state IN ({_STATES})), "
    "latest_record_version INTEGER, CHECK (request_id = attempt_id), "
    "FOREIGN KEY (attempt_id, latest_record_version) "
    "REFERENCES records (attempt_id, record_version))",
    "CREATE TABLE records ("
    "attempt_id TEXT NOT NULL REFERENCES attempts (attempt_id), "
    "record_version INTEGER NOT NULL CHECK (record_version >= 1), "
    "payload BLOB NOT NULL, sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL, "
    "PRIMARY KEY (attempt_id, record_version))",
    # Payloads are append-only, registrations are retained, identity and owner are fixed
    # (no takeover), and the latest pointer only moves forward.
    "CREATE TRIGGER records_no_update BEFORE UPDATE ON records "
    "BEGIN SELECT RAISE(ABORT, 'records are append-only'); END",
    "CREATE TRIGGER records_no_delete BEFORE DELETE ON records "
    "BEGIN SELECT RAISE(ABORT, 'records are append-only'); END",
    "CREATE TRIGGER attempts_no_delete BEFORE DELETE ON attempts "
    "BEGIN SELECT RAISE(ABORT, 'registrations are retained'); END",
    "CREATE TRIGGER attempts_identity_fixed BEFORE UPDATE OF request_id, attempt_id, "
    "attempt_hash, request_digest, run_id, owner_session ON attempts "
    "BEGIN SELECT RAISE(ABORT, 'registered identity is immutable'); END",
    "CREATE TRIGGER attempts_version_forward BEFORE UPDATE OF latest_record_version ON attempts "
    "WHEN NEW.latest_record_version IS NULL OR (OLD.latest_record_version IS NOT NULL "
    "AND NEW.latest_record_version <= OLD.latest_record_version) "
    "BEGIN SELECT RAISE(ABORT, 'record versions only move forward'); END",
)


class _StorageFault(Exception):
    """Store state prevents a write from being verified or committed."""


class _IntegrityFault(Exception):
    """Persisted index rows or payload bytes do not verify."""


@dataclass(frozen=True)
class CommittedRecord:
    """One verified committed version: its RecordRef, raw canonical bytes and payload."""

    record_ref: dict
    payload_bytes: bytes
    payload: dict


def attempt_hash(attempt_id: str) -> str:
    return hashlib.sha256(attempt_id.encode("utf-8")).hexdigest()


def record_location(namespace: str, attempt_id: str, record_version: int) -> str:
    return f"stores/{namespace}/attempts/{attempt_hash(attempt_id)}/records/{record_version}.json"


def object_location(namespace: str, sha256: str) -> str:
    return f"stores/{namespace}/objects/{sha256[:2]}/{sha256}"


def request_digest(spec: Mapping) -> str:
    # D017: sha256 of the complete canonical ExecutionSpec bytes, with prefix.
    return "sha256:" + hashlib.sha256(_json_v1.encode(spec)).hexdigest()


def artifact_ref(namespace: str, data: bytes, media_type: str) -> dict:
    """The ArtifactRef a store object will have; valid only once a record commits it."""
    sha = hashlib.sha256(data).hexdigest()
    return {
        "location": object_location(namespace, sha),
        "sha256": sha,
        "size_bytes": len(data),
        "media_type": media_type,
    }


def flatten(committed: CommittedRecord, observed_at: str) -> dict:
    """The flat ExecutionRecord: the fixed payload plus the three outer items only (V15)."""
    return {
        **copy.deepcopy(committed.payload),
        "record_ref": copy.deepcopy(committed.record_ref),
        "observed_at": observed_at,
        # The store observes no controller; it never infers live state from metadata.
        "controller_observation": {
            "status": "unavailable",
            "source": CONTROLLER_SOURCE,
            "observed_at": observed_at,
            "facts": {},
        },
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _is_id(value: object) -> bool:
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def _is_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not _TIMESTAMP.fullmatch(value):
        return False
    try:
        # V27: a regex match is not enough; the date must exist.
        datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return False
    return True


def _has_fields(value: object, names: frozenset[str]) -> bool:
    return isinstance(value, dict) and set(value) == names


def _describe(exc: BaseException) -> str:
    # OSError text would carry local absolute paths; keep only the error kind.
    if isinstance(exc, OSError):
        return f"{type(exc).__name__}: {exc.strerror or exc.errno}"
    return f"{type(exc).__name__}: {exc}"


def _try_lock(fd: int) -> bool:
    """Take the exclusive owner lock without waiting; False when another handle holds it."""
    try:
        if os.name == "nt":
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in _CONTENDED:
            return False
        raise
    return True


def _unlock(fd: int) -> None:
    if os.name == "nt":
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)


def _lock_held(path: Path) -> bool | None:
    """True: an owner holds the lock. False: free. None: the state cannot be confirmed."""
    try:
        fd = os.open(path, os.O_RDWR)
    except OSError:
        return None
    try:
        if _try_lock(fd):
            _unlock(fd)
            return False
        return True
    except OSError:
        return None
    finally:
        os.close(fd)


def _chunks(source: bytes | Path) -> Iterator[bytes]:
    if isinstance(source, (bytes, bytearray)):
        yield bytes(source)
        return
    with open(source, "rb") as stream:
        yield from iter(lambda: stream.read(_CHUNK), b"")


def _write_temp(directory: Path, source: bytes | Path) -> tuple[Path, str, int]:
    """Copy one known artifact into a flushed temporary file; return its hash and size."""
    temp = directory / f"{uuid.uuid4().hex}.tmp"
    hasher = hashlib.sha256()
    size = 0
    try:
        with open(temp, "xb") as out:
            for chunk in _chunks(source):
                out.write(chunk)
                hasher.update(chunk)
                size += len(chunk)
            out.flush()
            os.fsync(out.fileno())
    except BaseException:
        with suppress(OSError):
            temp.unlink(missing_ok=True)
        raise
    return temp, hasher.hexdigest(), size


def _fsync_directory(path: Path) -> None:
    # Windows offers no directory handle to fsync; POSIX makes the rename durable here.
    if os.name == "nt":
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _publish(temp: Path, final: Path) -> None:
    """Atomically move a temporary file to its content address; never overwrite."""
    final.parent.mkdir(exist_ok=True)
    if not final.exists():
        try:
            os.replace(temp, final)
        except OSError:
            # A concurrent writer may have published the same content first.
            if not final.exists():
                raise
        else:
            _fsync_directory(final.parent)
            return
    temp.unlink()


def _file_digest(path: Path) -> tuple[str, int]:
    hasher = hashlib.sha256()
    size = 0
    for chunk in _chunks(path):
        hasher.update(chunk)
        size += len(chunk)
    return hasher.hexdigest(), size


def _release(fd: int) -> None:
    """Drop the owner lock and close its handle."""
    try:
        _unlock(fd)
    finally:
        os.close(fd)


def _open_lock(path: Path) -> int:
    return os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o600)


@contextmanager
def _connect(
    index: Path, timeout: float, *, read_only: bool = False
) -> Iterator[sqlite3.Connection]:
    if read_only:
        target = f"{index.as_uri()}?mode=ro"
        conn = sqlite3.connect(target, uri=True, timeout=timeout, isolation_level=None)
    else:
        conn = sqlite3.connect(index, timeout=timeout, isolation_level=None)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        if not read_only:
            conn.execute("PRAGMA synchronous = FULL")
        yield conn
    finally:
        conn.close()


@contextmanager
def _transaction(conn: sqlite3.Connection, begin: str = "BEGIN IMMEDIATE") -> Iterator[None]:
    conn.execute(begin)
    try:
        yield
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


_BUSY_TIMEOUT = 30.0
_ATTEMPT_FIELDS = frozenset(
    {
        "request_id", "run_id", "attempt_id", "owner", "target_request", "deadline_utc",
        "resources", "budget", "retry_of", "retry_reason",
    }
)
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)


def _validated_root(root: str | os.PathLike, namespace: str) -> Path:
    """Check the explicit store configuration; one root is exactly one namespace."""
    errors = []
    if not isinstance(namespace, str) or not _NAMESPACE.fullmatch(namespace):
        errors.append("namespace: must match [A-Za-z0-9][A-Za-z0-9._-]{0,127}")
    path = Path(root)
    if not path.is_absolute():
        errors.append("root: must be an explicit absolute local path")
    if errors:
        raise PublicError(
            "InvalidRequest", stage="open", message="illegal RunStore configuration",
            field_errors=errors,
        )
    return path


def _attempt_errors(attempt: object) -> list[str]:
    """Field problems in an AttemptContext; an empty list means the identity is legal."""
    if not _has_fields(attempt, _ATTEMPT_FIELDS):
        return ["attempt: fields must be exactly the AttemptContext fields"]
    errors = [
        f"{name}: not an Id"
        for name in ("request_id", "run_id", "attempt_id", "owner")
        if not _is_id(attempt[name])
    ]
    if attempt["request_id"] != attempt["attempt_id"]:
        errors.append("request_id: must equal attempt_id")
    if not _is_timestamp(attempt["deadline_utc"]):
        errors.append("deadline_utc: not a Timestamp")
    if not _has_fields(attempt["target_request"], _TARGET_FIELDS):
        errors.append("target_request: fields must be exactly the TargetRequest fields")
    elif attempt["target_request"]["executor_kind"] != "local_cpu":
        errors.append("target_request.executor_kind: only local_cpu is supported")
    if not _has_fields(attempt["resources"], _RESOURCE_FIELDS):
        errors.append("resources: fields must be exactly the ResourceRequest fields")
    if not _has_fields(attempt["budget"], _BUDGET_FIELDS):
        errors.append("budget: fields must be exactly the BudgetRequest fields")
    if (attempt["retry_of"] is None) != (attempt["retry_reason"] is None):
        errors.append("retry_of: retry_of and retry_reason must both be null or both set")
    if attempt["retry_of"] is not None and not _is_id(attempt["retry_of"]):
        errors.append("retry_of: not an Id")
    return errors


def allocate_attempt(
    *,
    run_id: str,
    owner: str,
    target_request: dict,
    deadline_utc: str,
    resources: dict,
    budget: dict,
    retry_of: str | None = None,
    retry_reason: str | None = None,
) -> dict:
    """Allocate a new AttemptContext; it takes no budget, reserves nothing and starts nothing."""
    attempt_id = f"att-{uuid.uuid4().hex}"
    attempt = {
        "request_id": attempt_id,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "owner": owner,
        "target_request": copy.deepcopy(target_request),
        "deadline_utc": deadline_utc,
        "resources": copy.deepcopy(resources),
        "budget": copy.deepcopy(budget),
        "retry_of": retry_of,
        "retry_reason": retry_reason,
    }
    errors = _attempt_errors(attempt)
    if errors:
        raise PublicError(
            "InvalidRequest", stage="allocate", message="attempt identity is illegal",
            field_errors=errors,
        )
    return attempt


def _payload_errors(
    payload: object, attempt: Mapping, request_digest: str, version: int
) -> list[str]:
    """Problems in a proposed payload for the next version of a claimed attempt."""
    if not _has_fields(payload, PAYLOAD_FIELDS):
        return ["payload: fields must be exactly the ExecutionRecordPayload fields"]
    expected = {
        "schema_version": 1,
        "request_id": attempt["request_id"],
        "attempt_id": attempt["attempt_id"],
        "run_id": attempt["run_id"],
        "owner": attempt["owner"],
        "request_digest": request_digest,
        "target_request": attempt["target_request"],
        "retry_of": attempt["retry_of"],
        "retry_reason": attempt["retry_reason"],
        "record_version": version,
    }
    # The type check keeps True from passing as 1.
    errors = [
        f"{name}: does not match the claim"
        for name, value in expected.items()
        if type(payload[name]) is not type(value) or payload[name] != value
    ]
    if payload["phase"] not in PHASES:
        errors.append("phase: not an execution phase")
    if not _is_timestamp(payload["recorded_at"]):
        errors.append("recorded_at: not a Timestamp")
    if payload["started"] is not None and not isinstance(payload["started"], bool):
        errors.append("started: must be a boolean or null")
    if not isinstance(payload["side_effect_unknown"], bool):
        errors.append("side_effect_unknown: must be a boolean")
    elif payload["phase"] == "finished" and payload["side_effect_unknown"]:
        errors.append("phase: finished requires side_effect_unknown=false (V18)")
    return errors


def _object_ref_errors(ref: object, namespace: str) -> list[str]:
    """Problems in an ArtifactRef that a commit is asked to retain as a store object."""
    if not _has_fields(ref, _ARTIFACT_REF_FIELDS) or not (
        isinstance(ref["sha256"], str) and _SHA256.fullmatch(ref["sha256"])
    ):
        return ["artifact: not an ArtifactRef with a sha256"]
    errors = []
    if ref["location"] != object_location(namespace, ref["sha256"]):
        errors.append("artifact.location: not this store's content address")
    if type(ref["size_bytes"]) is not int or ref["size_bytes"] < 0:
        errors.append("artifact.size_bytes: not a byte count")
    if not isinstance(ref["media_type"], str) or not ref["media_type"]:
        errors.append("artifact.media_type: must be a non-empty string")
    return errors


def _load_record(
    conn: sqlite3.Connection, namespace: str, attempt_id: str, version: int
) -> CommittedRecord | None:
    """Read and verify one committed version; None when no such row exists."""
    row = conn.execute(
        "SELECT payload, sha256, size_bytes FROM records "
        "WHERE attempt_id = ? AND record_version = ?",
        (attempt_id, version),
    ).fetchone()
    if row is None:
        return None
    data = bytes(row["payload"])
    digest = hashlib.sha256(data).hexdigest()
    if digest != row["sha256"] or len(data) != row["size_bytes"]:
        raise _IntegrityFault(f"record version {version} bytes do not match their index row")
    try:
        payload = _json_v1.decode(data)
    except _json_v1.CanonicalError as exc:
        raise _IntegrityFault(f"record version {version} is not canonical: {exc.stage}") from exc
    if (
        not _has_fields(payload, PAYLOAD_FIELDS)
        or payload["attempt_id"] != attempt_id
        or payload["record_version"] != version
    ):
        raise _IntegrityFault(f"record version {version} payload does not match its index row")
    ref = {
        "attempt_id": attempt_id,
        "record_version": version,
        "artifact": {
            "location": record_location(namespace, attempt_id, version),
            "sha256": digest,
            "size_bytes": len(data),
            "media_type": RECORD_MEDIA_TYPE,
        },
    }
    return CommittedRecord(ref, data, payload)


def _latest_record(
    conn: sqlite3.Connection, namespace: str, row: sqlite3.Row
) -> CommittedRecord | None:
    """The verified latest record of one registration, checked against its state."""
    version = row["latest_record_version"]
    if version is None:
        # State only moves with a committed record.
        if row["state"] != "registered":
            raise _IntegrityFault(f"state {row['state']} has no committed record")
        return None
    committed = _load_record(conn, namespace, row["attempt_id"], version)
    if committed is None:
        raise _IntegrityFault(f"latest record version {version} is missing")
    if (
        committed.payload["phase"] != row["state"]
        or committed.payload["request_digest"] != row["request_digest"]
    ):
        raise _IntegrityFault("latest record does not match its registration")
    return committed


def _acquire(path: Path) -> int | None:
    """Open and take the owner lock without waiting; None when another handle holds it."""
    fd = _open_lock(path)
    try:
        if _try_lock(fd):
            return fd
    except BaseException:
        os.close(fd)
        raise
    os.close(fd)
    return None


class RunStoreReader:
    """Read-only access to one RunStore root: committed versions and store locations."""

    _read_only = True

    def __init__(
        self, root: str | os.PathLike, namespace: str, *, busy_timeout: float = _BUSY_TIMEOUT
    ):
        self.root = _validated_root(root, namespace)
        self.namespace = namespace
        self._index = self.root / INDEX_NAME
        self._timeout = busy_timeout
        if not self._index.is_file():
            raise PublicError(
                "InvalidRequest", stage="open", message="root holds no RunStore index"
            )
        try:
            with self._connection() as conn:
                rows = conn.execute("SELECT key, value FROM meta").fetchall()
            meta = {row["key"]: row["value"] for row in rows}
        except sqlite3.Error as exc:
            raise PublicError(
                "ExecutionPersistenceError", stage="open",
                message=f"cannot read the RunStore index: {_describe(exc)}",
            ) from exc
        if meta != {"format": STORE_FORMAT, "namespace": namespace}:
            raise PublicError(
                "InvalidRequest", stage="open",
                message="root belongs to another RunStore namespace or format",
            )

    @classmethod
    def from_mount(cls, mount: Mapping) -> RunStoreReader:
        """Open the reader of one trusted ``harness_sqlite`` StorageMount (D021 section 4)."""
        errors = []
        if not _has_fields(mount, _MOUNT_FIELDS):
            errors.append("mount: fields must be exactly the StorageMount fields")
        else:
            if mount["kind"] != "harness_sqlite":
                errors.append("kind: must be harness_sqlite")
            if mount["prefix"] != f"stores/{mount['namespace']}":
                errors.append("prefix: last segment must be the store namespace under stores/")
        if errors:
            raise PublicError(
                "InvalidRequest", stage="open", message="illegal harness_sqlite mount",
                field_errors=errors,
            )
        return cls(mount["root"], mount["namespace"])

    def _connection(self) -> AbstractContextManager[sqlite3.Connection]:
        return _connect(self._index, self._timeout, read_only=self._read_only)

    def committed(self, attempt_id: str, record_version: int | None = None) -> CommittedRecord:
        """One verified committed version; the latest one when ``record_version`` is None."""
        errors = [] if _is_id(attempt_id) else ["attempt_id: not an Id"]
        if record_version is not None and (
            type(record_version) is not int
            or not 1 <= record_version <= _json_v1.MAX_SAFE_INTEGER
        ):
            errors.append("record_version: must be null or a positive integer")
        if errors:
            raise PublicError(
                "InvalidRequest", stage="read", message="illegal read", field_errors=errors
            )
        try:
            with self._connection() as conn:
                if record_version is None:
                    row = conn.execute(
                        "SELECT * FROM attempts WHERE attempt_id = ?", (attempt_id,)
                    ).fetchone()
                    committed = None if row is None else _latest_record(conn, self.namespace, row)
                    if committed is None:
                        # Never assemble a snapshot from registration metadata.
                        raise PublicError(
                            "NoCommittedRecord", stage="read", attempt_id=attempt_id,
                            message="the attempt has no committed record",
                        )
                    return committed
                committed = _load_record(conn, self.namespace, attempt_id, record_version)
        except _IntegrityFault as exc:
            raise PublicError(
                "RecordIntegrityError", stage="read", attempt_id=attempt_id, message=str(exc)
            ) from exc
        except sqlite3.Error as exc:
            raise PublicError(
                "ExecutionPersistenceError", stage="read", attempt_id=attempt_id,
                message=f"cannot read the RunStore index: {_describe(exc)}",
            ) from exc
        if committed is None:
            raise PublicError(
                "RecordNotFound", stage="read", attempt_id=attempt_id,
                message=f"record version {record_version} does not exist",
            )
        return committed

    def read(self, attempt_id: str, record_version: int | None = None) -> dict:
        """H ``read``: the flat ExecutionRecord of the latest or of a fixed committed version."""
        return flatten(self.committed(attempt_id, record_version), utc_now())

    def open(self, ref: Mapping) -> io.BytesIO:
        """Resolve an ArtifactRef in this store to its verified original bytes."""
        if not _has_fields(ref, _ARTIFACT_REF_FIELDS):
            raise PublicError("InvalidRequest", stage="open", message="not an ArtifactRef")
        location = ref["location"]
        prefix = f"stores/{self.namespace}/"
        inside = isinstance(location, str) and location.startswith(prefix)
        rest = location[len(prefix):] if inside else ""
        record = _RECORD_REST.fullmatch(rest)
        stored = _OBJECT_REST.fullmatch(rest)
        if stored is not None and stored[2][:2] != stored[1]:
            stored = None
        if record is None and stored is None:
            raise PublicError(
                "UnsafeArtifactPath", stage="open",
                message="location is not a record or object location of this store",
            )
        try:
            if record is not None:
                data = self._record_bytes(record[1], int(record[2]))
            else:
                data = self._object_bytes(stored[2])
        except (sqlite3.Error, OSError) as exc:
            raise PublicError(
                "ArtifactUnavailable", stage="open",
                message=f"bytes are not accessible: {_describe(exc)}",
            ) from exc
        if data is None:
            raise PublicError(
                "ArtifactUnavailable", stage="open", message="no bytes at this location"
            )
        if hashlib.sha256(data).hexdigest() != ref["sha256"] or len(data) != ref["size_bytes"]:
            raise PublicError(
                "ArtifactIntegrityError", stage="open",
                message="bytes do not match the declared sha256 or size",
            )
        return io.BytesIO(data)

    def _record_bytes(self, hashed_attempt: str, version: int) -> bytes | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT r.payload FROM attempts a JOIN records r ON r.attempt_id = a.attempt_id "
                "WHERE a.attempt_hash = ? AND r.record_version = ?",
                (hashed_attempt, version),
            ).fetchone()
        return None if row is None else bytes(row["payload"])

    def _object_bytes(self, sha256: str) -> bytes | None:
        path = self.root / "objects" / sha256[:2] / sha256
        if path.is_symlink():
            raise PublicError(
                "UnsafeArtifactPath", stage="open", message="store objects are never links"
            )
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return None


class RunStore(RunStoreReader):
    """The writable H RunStore of one root: atomic claim, owner lock and append-only records."""

    _read_only = False

    def __init__(
        self, root: str | os.PathLike, namespace: str, *, busy_timeout: float = _BUSY_TIMEOUT
    ):
        path = _validated_root(root, namespace)
        try:
            for directory in (path, path / "objects", path / "tmp", path / "locks"):
                directory.mkdir(parents=True, exist_ok=True)
            # Concurrent first opens serialize on the write lock; only one creates the schema.
            with _connect(path / INDEX_NAME, busy_timeout) as conn, _transaction(conn):
                created = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'meta'"
                ).fetchone()
                if created is None:
                    for statement in _SCHEMA:
                        conn.execute(statement)
                    conn.executemany(
                        "INSERT INTO meta (key, value) VALUES (?, ?)",
                        (("format", STORE_FORMAT), ("namespace", namespace)),
                    )
        except (sqlite3.Error, OSError) as exc:
            raise PublicError(
                "ExecutionPersistenceError", stage="open", started=False,
                message=f"cannot initialize the RunStore: {_describe(exc)}",
            ) from exc
        super().__init__(path, namespace, busy_timeout=busy_timeout)

    def claim(self, attempt: Mapping, request_digest: str) -> Claim | CommittedRecord:
        """Register an attempt atomically, or apply the D021 re-entry table to its registration.

        Returns a ``Claim`` holding the owner lock for a new registration, or the original
        committed record of a finished one. Every other re-entry raises its PublicError and
        starts nothing.
        """
        errors = _attempt_errors(attempt)
        if not isinstance(request_digest, str) or not _DIGEST.fullmatch(request_digest):
            errors.append("request_digest: not a SemanticId")
        if errors:
            raise PublicError(
                "InvalidRequest", stage="claim", message="illegal claim", field_errors=errors
            )
        attempt_id = attempt["attempt_id"]
        lock_path = self.root / "locks" / f"{attempt_hash(attempt_id)}.lock"
        session = uuid.uuid4().hex
        fd = None
        try:
            with self._connection() as conn, _transaction(conn):
                row = conn.execute(
                    "SELECT * FROM attempts WHERE request_id = ?", (attempt_id,)
                ).fetchone()
                if row is not None:
                    return self._reenter(conn, row, request_digest, lock_path)
                # Take the owner lock before the registration commits, so no reader can
                # observe a registered attempt whose live owner is not yet locked.
                fd = _acquire(lock_path)
                if fd is None:
                    raise _StorageFault("the owner lock is held but no registration exists")
                conn.execute(
                    "INSERT INTO attempts (request_id, attempt_id, attempt_hash, request_digest, "
                    "run_id, owner_session, state) VALUES (?, ?, ?, ?, ?, ?, 'registered')",
                    (
                        attempt_id, attempt_id, attempt_hash(attempt_id), request_digest,
                        attempt["run_id"], session,
                    ),
                )
        except _IntegrityFault as exc:
            raise PublicError(
                "RecordIntegrityError", stage="claim", attempt_id=attempt_id, message=str(exc)
            ) from exc
        except (sqlite3.Error, OSError, _StorageFault) as exc:
            if fd is not None:
                _release(fd)
            raise PublicError(
                "ExecutionPersistenceError", stage="claim", attempt_id=attempt_id, started=False,
                message=f"registration failed: {_describe(exc)}",
            ) from exc
        return Claim(self, attempt, request_digest, session, fd)

    def _reenter(
        self, conn: sqlite3.Connection, row: sqlite3.Row, request_digest: str, lock_path: Path
    ) -> CommittedRecord:
        """Digest first, then state; inside the claim transaction so no commit interleaves."""
        attempt_id = row["attempt_id"]
        if row["request_digest"] != request_digest:
            raise PublicError(
                "RequestConflict", stage="claim", attempt_id=attempt_id,
                message="the attempt is registered with a different request digest",
            )
        latest = _latest_record(conn, self.namespace, row)
        if row["state"] == "finished":
            return latest
        ref = None if latest is None else latest.record_ref
        started = None if latest is None else latest.payload["started"]
        if row["state"] == "recovery_required":
            raise PublicError(
                "RecoveryRequired", stage="claim", attempt_id=attempt_id, started=started,
                latest_record_ref=ref, message="the attempt requires recovery and is never rerun",
            )
        # A free or unconfirmable lock never means not started (D021 section 3).
        if _lock_held(lock_path):
            raise PublicError(
                "AttemptInProgress", stage="claim", attempt_id=attempt_id, started=started,
                latest_record_ref=ref, message="the registered owner still holds the attempt",
            )
        raise PublicError(
            "RecoveryRequired", stage="claim", attempt_id=attempt_id, started=started,
            latest_record_ref=ref, message="the attempt is unfinished and its owner is gone",
        )

    def _retain(self, ref: Mapping, source: bytes | Path) -> None:
        """Copy one known artifact to its content address and verify the published bytes."""
        temp, digest, size = _write_temp(self.root / "tmp", source)
        if (digest, size) != (ref["sha256"], ref["size_bytes"]):
            temp.unlink()
            raise _IntegrityFault("artifact bytes differ from their declared ArtifactRef")
        final = self.root / "objects" / digest[:2] / digest
        _publish(temp, final)
        if _file_digest(final) != (digest, size):
            raise _IntegrityFault("a published object does not verify")

    def _append(self, attempt_id: str, session: str, version: int, phase: str, data: bytes) -> None:
        """One transaction: append the payload BLOB and move the latest pointer forward."""
        with self._connection() as conn, _transaction(conn):
            row = conn.execute(
                "SELECT owner_session, latest_record_version FROM attempts WHERE attempt_id = ?",
                (attempt_id,),
            ).fetchone()
            if (
                row is None
                or row["owner_session"] != session
                or (row["latest_record_version"] or 0) != version - 1
            ):
                raise _StorageFault("the registration no longer matches this owner")
            conn.execute(
                "INSERT INTO records (attempt_id, record_version, payload, sha256, size_bytes) "
                "VALUES (?, ?, ?, ?, ?)",
                (attempt_id, version, data, hashlib.sha256(data).hexdigest(), len(data)),
            )
            conn.execute(
                "UPDATE attempts SET latest_record_version = ?, state = ? WHERE attempt_id = ?",
                (version, phase, attempt_id),
            )


class Claim:
    """The live owner of one registered attempt: it holds the OS lock and commits records."""

    def __init__(
        self, store: RunStore, attempt: Mapping, request_digest: str, session: str, fd: int
    ):
        self._store = store
        self.attempt = copy.deepcopy(dict(attempt))
        self.request_digest = request_digest
        self._session = session
        self._fd: int | None = fd
        self._version = 0
        self._phase = "registered"
        self.latest_record_ref: dict | None = None

    @property
    def attempt_id(self) -> str:
        return self.attempt["attempt_id"]

    @property
    def next_record_version(self) -> int:
        return self._version + 1

    def __enter__(self) -> Claim:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.release()

    def release(self) -> None:
        """Drop the owner lock; an unfinished attempt then re-enters only as RecoveryRequired."""
        if self._fd is not None:
            fd, self._fd = self._fd, None
            _release(fd)

    def commit(
        self, payload: Mapping, artifacts: Iterable[tuple[Mapping, bytes | Path]] = ()
    ) -> CommittedRecord:
        """Retain known artifacts, then append the next version; the Ref exists only after both.

        ``artifacts`` pairs each store ArtifactRef in the payload with its source bytes or file.
        """
        if self._fd is None:
            raise ValueError("the claim was released; only a live owner commits")
        if self._phase == "finished":
            raise ValueError("a finished attempt is terminal")
        version = self._version + 1
        artifacts = [(dict(ref), source) for ref, source in artifacts]
        errors = _payload_errors(payload, self.attempt, self.request_digest, version)
        for ref, _ in artifacts:
            errors.extend(_object_ref_errors(ref, self._store.namespace))
        if errors:
            raise ValueError(f"illegal record commit: {errors}")
        data = _json_v1.encode(payload)
        try:
            for ref, source in artifacts:
                self._store._retain(ref, source)
            self._store._append(self.attempt_id, self._session, version, payload["phase"], data)
        except (sqlite3.Error, OSError, _StorageFault, _IntegrityFault) as exc:
            raise self._commit_error(
                payload, f"record commit failed: {_describe(exc)}", self.latest_record_ref
            ) from exc
        # The append is durable from here on, so the claim tracks the new version even if
        # the readback below fails.
        self._version, self._phase = version, payload["phase"]
        try:
            committed = self._store.committed(self.attempt_id, version)
        except PublicError as exc:
            # No Ref is issued for an unreadable row; the previous verified Ref stays retained.
            raise self._commit_error(
                payload, f"record committed but not readable: {exc.code}", None
            ) from exc
        self.latest_record_ref = committed.record_ref
        return committed

    def _commit_error(
        self, payload: Mapping, message: str, latest: dict | None
    ) -> PublicError:
        retained = [] if self.latest_record_ref is None else [self.latest_record_ref["artifact"]]
        return PublicError(
            "ExecutionPersistenceError", stage="commit", message=message,
            attempt_id=self.attempt_id, started=payload["started"], latest_record_ref=latest,
            partial_record=PartialExecutionFacts.from_payload(payload),
            retained_refs=retained,
        )
