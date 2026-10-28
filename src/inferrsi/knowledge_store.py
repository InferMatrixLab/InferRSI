from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from importlib.resources import files
from pathlib import Path

from .knowledge_operations import (
    AUTHORITIES,
    IDENTITY,
    Bundle,
    IdentityError,
    KnowledgeReader,
    RevisionConflict,
    _json,
    safe_path,
)


def _protected(skill_root: Path | None) -> list[Path]:
    package = Path(str(files("inferrsi"))).resolve()
    roots = [package]
    # A source, editable or exported tree (git archive, sdist) surrounds the package
    # and holds evidence and both matrices; protect it even without a .git entry,
    # because review snapshots carry no repository metadata.
    for parent in package.parents:
        if (parent / "pyproject.toml").is_file() or (parent / ".git").exists():
            roots.append(parent)
            break
    if skill_root is not None:
        roots.append(Path(skill_root).resolve().parent)
    return roots


class KnowledgeStore:
    """One authorized writable store for store-owned candidate bundles.

    Package and checkout content stay read-only; their IDs are reserved here so a
    store candidate cannot shadow them. Repository-owned amendments use PRs.
    """

    def __init__(self, workspace: Path, *, skill_root: Path | None, read_only: bool = False):
        # The caller authorizes an existing dedicated directory; none is created or guessed.
        workspace = Path(workspace)
        if workspace.is_symlink() or not workspace.is_dir():
            raise ValueError("Store requires an existing authorized workspace directory")
        self.workspace = workspace.resolve()
        for root in _protected(skill_root):
            if self.workspace.is_relative_to(root):
                raise ValueError(f"Store workspace must be outside read-only sources: {root}")
        self.skill_root = Path(skill_root).resolve() if skill_root is not None else None
        self.adapters = KnowledgeReader(skill_root=self.skill_root)
        self.read_only = read_only
        self.database = self.workspace / "knowledge.sqlite3"
        if self.database.is_symlink():
            raise ValueError("Store database cannot be a symlink")
        if read_only:
            # Reading an existing store must not create or migrate anything.
            if not self.database.is_file():
                raise ValueError(f"Read-only store requires an existing database: {self.database}")
            self._verify_reserved_skill_root()
            return
        with closing(self._connect()) as connection, connection:
            connection.executescript(
                "CREATE TABLE IF NOT EXISTS revisions ("
                "id TEXT NOT NULL, revision TEXT NOT NULL, metadata TEXT NOT NULL, "
                "dependencies TEXT NOT NULL, parent TEXT, reason TEXT NOT NULL, "
                "evidence TEXT NOT NULL, PRIMARY KEY (id, revision));"
                "CREATE TABLE IF NOT EXISTS resources ("
                "id TEXT NOT NULL, revision TEXT NOT NULL, path TEXT NOT NULL, data BLOB NOT NULL, "
                "PRIMARY KEY (id, revision, path), "
                "FOREIGN KEY (id, revision) REFERENCES revisions(id, revision));"
                "CREATE TABLE IF NOT EXISTS current (id TEXT PRIMARY KEY, revision TEXT NOT NULL, "
                "FOREIGN KEY (id, revision) REFERENCES revisions(id, revision));"
                "CREATE TABLE IF NOT EXISTS meta ("
                "key TEXT PRIMARY KEY, value TEXT NOT NULL);"
            )
            reserved = connection.execute(
                "SELECT value FROM meta WHERE key='skill_root'"
            ).fetchone()
            if reserved is None:
                connection.execute(
                    "INSERT INTO meta VALUES ('skill_root', ?)", (self._reserved_skill_root(),)
                )
            elif reserved[0] != self._reserved_skill_root():
                raise ValueError(
                    f"Store reserves the skills checkout {reserved[0] or 'package-only'}; "
                    "reopen it with the same skill_root"
                )

    def _reserved_skill_root(self) -> str:
        # The reserved checkout is recorded so later opens cannot silently drop it;
        # an empty value records a package-only store.
        return str(self.skill_root) if self.skill_root is not None else ""

    def _verify_reserved_skill_root(self) -> None:
        # Stores created before reservation recording have no meta row and stay usable.
        with closing(self._connect()) as connection:
            present = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'"
            ).fetchone()
            reserved = (
                connection.execute("SELECT value FROM meta WHERE key='skill_root'").fetchone()
                if present
                else None
            )
        if reserved is not None and reserved[0] != self._reserved_skill_root():
            raise ValueError(
                f"Store reserves the skills checkout {reserved[0] or 'package-only'}; "
                "open it with the same --skill-root, or without one for a package-only store"
            )

    def _connect(self):
        if self.database.is_symlink() or self.database.resolve().parent != self.workspace:
            raise ValueError("Store database escapes the authorized workspace")
        if self.read_only:
            # mode=ro fails every write at the SQLite level; as_uri() percent-encodes
            # spaces and non-ASCII so the file: URI stays valid on Windows too.
            connection = sqlite3.connect(self.database.as_uri() + "?mode=ro", uri=True, timeout=5)
        else:
            connection = sqlite3.connect(self.database, timeout=5)
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def identities(self) -> list[str]:
        with closing(self._connect()) as connection:
            return [row[0] for row in connection.execute("SELECT id FROM current ORDER BY id")]

    def reader(self) -> KnowledgeReader:
        return KnowledgeReader(skill_root=self.skill_root, store=self)

    def collect(self, query: str = "", **options) -> dict:
        return self.reader().collect(query, **options)

    def create(self, bundle: Bundle) -> str:
        if self.read_only:
            raise ValueError("Store is read-only; create requires a writable store")
        return self._publish(bundle, expected=None, reason="create", evidence=[])

    def update(self, bundle: Bundle, *, expected: str, reason: str, evidence: list[dict]) -> str:
        if self.read_only:
            raise ValueError("Store is read-only; update requires a writable store")
        if not expected or not reason.strip():
            raise ValueError("Update requires expected old revision and reason")
        if not isinstance(evidence, list):
            raise ValueError("Update evidence must be a list; an empty list means none supplied")
        return self._publish(bundle, expected=expected, reason=reason, evidence=evidence)

    def _lineage(self, metadata: dict) -> None:
        lineage = metadata.get("derived_from", [])
        if not isinstance(lineage, list):
            raise ValueError("derived_from must be a list of qualified source revisions")
        for source in lineage:
            if not isinstance(source, dict) or not isinstance(source.get("ref"), str):
                raise ValueError("derived_from entries require a qualified ref")
            authority, _, identity = source["ref"].partition(":")
            if authority not in AUTHORITIES or not re.fullmatch(IDENTITY, identity):
                raise ValueError(f"derived_from ref must be <authority>:<id>: {source['ref']}")
            revision = source.get("revision")
            if revision is not None and (
                not isinstance(revision, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", revision)
            ):
                raise ValueError("derived_from revision must be a content revision or null")
            if identity == metadata["id"]:
                raise IdentityError(
                    "collision", "An adaptation needs a distinct identity from its source"
                )

    def _publish(self, bundle: Bundle, *, expected: str | None, reason: str, evidence: list) -> str:
        # Copy caller data, validate it, then store the whole bundle and current
        # pointer in one transaction.
        bundle = Bundle(
            json.loads(_json(bundle.metadata)), dict(bundle.content), dict(bundle.dependencies)
        )
        revision = bundle.revision
        identity = bundle.metadata["id"]
        try:
            bundle.content[bundle.metadata["entrypoint"]].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Bundle entrypoint must be UTF-8 text") from exc
        self._lineage(bundle.metadata)
        owners = self.adapters.owners().get(identity)
        if owners:
            raise IdentityError(
                "collision",
                f"Identity {identity} is owned by read-only {', '.join(owners)} content; "
                "amend it through a repository PR or create an adaptation with a distinct ID",
            )
        if expected is None and bundle.metadata["state"] != "candidate":
            raise ValueError(
                "Create registers a candidate; imported or active content is not promoted"
            )
        try:
            with closing(self._connect()) as connection, connection:
                connection.execute("BEGIN IMMEDIATE")
                current = connection.execute(
                    "SELECT revision FROM current WHERE id=?", (identity,)
                ).fetchone()
                if expected is None:
                    if current is not None:
                        raise RevisionConflict(f"Duplicate identity: {identity}")
                elif current is None or current[0] != expected:
                    raise RevisionConflict(f"Stale or missing revision for {identity}")
                if expected is not None:
                    previous = connection.execute(
                        "SELECT metadata FROM revisions WHERE id=? AND revision=?",
                        (identity, expected),
                    ).fetchone()
                    old = json.loads(previous[0])
                    if bundle.metadata["state"] != old["state"]:
                        raise ValueError("Update cannot promote content state")
                if revision == expected:
                    raise ValueError("Update must change the bundle")
                if connection.execute(
                    "SELECT 1 FROM revisions WHERE id=? AND revision=?", (identity, revision)
                ).fetchone():
                    raise RevisionConflict(
                        f"Update reproduces retained revision {revision}; "
                        "change the bundle so the successor has its own revision"
                    )
                connection.execute(
                    "INSERT INTO revisions VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        identity,
                        revision,
                        _json(bundle.metadata).decode(),
                        _json(bundle.dependencies).decode(),
                        expected,
                        reason,
                        _json(evidence).decode(),
                    ),
                )
                connection.executemany(
                    "INSERT INTO resources VALUES (?, ?, ?, ?)",
                    [(identity, revision, path, data) for path, data in bundle.content.items()],
                )
                connection.execute(
                    "INSERT INTO current VALUES (?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET revision=excluded.revision",
                    (identity, revision),
                )
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc) and "busy" not in str(exc):
                raise
            raise RevisionConflict(
                f"Store is locked by another writer; retry {identity} once it is released"
            ) from exc
        return revision

    def read(self, identity: str, *, revision: str | None = None) -> Bundle:
        with closing(self._connect()) as connection:
            if revision is None:
                row = connection.execute(
                    "SELECT revision FROM current WHERE id=?", (identity,)
                ).fetchone()
                if row is None:
                    raise IdentityError("unknown_identity", f"Unknown identity: store:{identity}")
                revision = row[0]
            row = connection.execute(
                "SELECT metadata, dependencies FROM revisions WHERE id=? AND revision=?",
                (identity, revision),
            ).fetchone()
            if row is None:
                raise RevisionConflict(f"Unknown revision: store:{identity} at {revision}")
            resources = connection.execute(
                "SELECT path, data FROM resources WHERE id=? AND revision=?", (identity, revision)
            ).fetchall()
        bundle = Bundle(json.loads(row[0]), dict(resources), json.loads(row[1]))
        if bundle.revision != revision:
            raise RevisionConflict("Stored bundle integrity mismatch")
        return bundle

    def resource(self, identity: str, path: str, *, revision: str) -> bytes:
        safe_path(path)
        bundle = self.read(identity, revision=revision)
        if path not in bundle.content:
            raise ValueError(f"Unknown resource: {path}")
        return bundle.content[path]

    def history(self, identity: str) -> list[dict]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT revision, parent, reason, evidence FROM revisions "
                "WHERE id=? ORDER BY rowid",
                (identity,),
            ).fetchall()
        return [
            {
                "revision": revision,
                "parent": parent,
                "reason": reason,
                "evidence": json.loads(evidence),
            }
            for revision, parent, reason, evidence in rows
        ]
