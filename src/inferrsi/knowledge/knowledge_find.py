"""One ranked lookup across packaged skills, records and checkout cases.

This is the discovery half of the knowledge interface. It answers "what is
already known about this problem" and returns corpus-relative paths, so the
caller can read, grep around, or stop. The audit half lives in ``read`` /
``resource``: exact identities, pinned revisions and content hashes.

Catalog search, model research and Collect reuse these documents and ranking
over the corpus eligible for their operation.

* Standalone Find ranks cases beside skills, including rejected directions
  and the conditions behind them.
* Each distinct matching term contributes to the score. One match is enough
  to be eligible, and ``limit`` caps the ranked results.
* Scoring reads the entries directly. Bundle closures may contain unrelated
  files. The reader checks material only for results offered to the caller.

Ranking is lexical, with query-side aliases. The caller assesses applicability.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shlex
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from importlib.resources import files
from io import BytesIO
from pathlib import Path, PurePosixPath
from statistics import median
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .channels import ChannelRegistry
    from .knowledge_operations import Bundle
    from .searchspace_index import SearchspaceCoordinate, SearchspaceEntry, SearchspaceIndex

from ._knowledge_errors import MissingSkillsExtra
from ._skill_selection import TASK_STOP_WORDS, indexed_skill, named_backends
from .catalog import BACKENDS, packaged_skill_id
from .ranking_policy import DEFAULT_RANKING_POLICY, RankingPolicy

# Ties break towards stronger evidence rather than alphabetical identity.
STATE_RANK = {
    "validated": 3,
    "author_reported": 2,
    "historical_observation": 2,
    "candidate": 1,
    "imported": 1,
    "unspecified": 0,
}

FINDING_OUTCOMES = (
    "rejected", "no_gain", "inconclusive", "adopted",
    "tradeoff", "caveat", "failure_signal",
)

# How far an observation is being claimed to reach. The distinction a reader
# most needs is whether a result is bound to the cohort it was seen on, and
# that cannot be read off the outcome: a rejection can be local or general.
# Absent means not assessed, which is not the same as `general`.
FINDING_SCOPES = ("local", "regime_bound", "general")

_CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
_CJK_RUN = re.compile(_CJK.pattern + "+")
_WORD = re.compile(r"[a-z0-9]+")
_QUERY_STOP_WORDS = TASK_STOP_WORDS | {
    "how", "what", "why", "which", "where", "who", "can", "could", "should", "would",
    "i", "you", "we", "do", "does", "did", "is", "are", "was", "were",
}
_BACKEND_NAME_ALIASES = {"昇腾": "ascend"}
_MAX_SNIPPET = 400
_MAX_LIMITATION_BYTES = 400
_MAX_SHOWN_LIMITATIONS = 3
# A case can record a dozen directions; listing all of them buries the one the
# caller asked about. The rest stay available through the cited file.
_MAX_SHOWN_FINDINGS = 3


def tokens(text: str) -> list[str]:
    """Split on separators as well as whitespace; cut CJK into overlapping bigrams.

    Underscores, hyphens and dots separate rather than bind. Tags in this corpus
    are written four ways for the same concept -- ``kv_cache``, ``kv-cache``,
    ``KV cache``, ``CUDA-Graph`` -- and treating a separator as a word character
    makes each spelling its own unsplittable token, so a query phrased in plain
    words never reaches the punctuated ones. Splitting normalises all four to the
    same terms. A compound still ranks above its parts because every part has to
    match for the whole to score.

    There is no CJK segmenter here, so a run is cut every two characters. Two
    characters carry a term -- 质量, 调度, 状态 -- while single characters mostly
    carry grammar; this corpus holds so few CJK characters that idf treats every
    one as rare, and a particle such as 和 would otherwise outscore the subject
    of the query. Punctuation isolates such particles into runs of their own
    ("任务、工具和输入"), so a one-character run is kept only when the whole
    query is that character: a lone term the caller typed deliberately still
    reaches the corpus, while a stranded conjunction does not score.
    """
    folded = text.casefold()
    found = _WORD.findall(folded)
    runs = _CJK_RUN.findall(folded)
    for run in runs:
        if len(run) == 1:
            if len(runs) == 1 and not found:
                found.append(run)
            continue
        found.extend(run[index:index + 2] for index in range(len(run) - 1))
    return found


def _term_counts(text: str) -> Counter[str]:
    folded = text.casefold()
    counts = Counter(_WORD.findall(folded))
    for run in _CJK_RUN.findall(folded):
        # Single characters are indexed for callers who deliberately query one.
        counts.update(run)
        counts.update(run[index:index + 2] for index in range(len(run) - 1))
    return counts


def _flatten(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


@dataclass(frozen=True)
class Finding:
    direction: str
    outcome: str
    reason: str
    revisit_when: str = ""
    keywords: tuple[str, ...] = ()
    scope: str = ""
    bounds: str = ""

    def search_text(self) -> str:
        return " ".join((
            *self.keywords, self.direction, self.reason, self.bounds, self.revisit_when,
        ))

    def view(self, *, inherited_bounds: str = "") -> dict:
        """Carry the cohort alongside the result, not only on the parent entry.

        A reader who reaches one finding through search sees it on its own. If
        the bounds stay at entry level, the most consequential qualifier -- the
        hardware and configuration this was observed on -- is exactly what gets
        dropped in transit.
        """
        record = {"direction": self.direction, "outcome": self.outcome, "reason": self.reason}
        if self.scope:
            record["scope"] = self.scope
        bounds = self.bounds or inherited_bounds
        if bounds:
            record["bounds"] = bounds
            # An inherited bound describes the whole entry; saying so keeps a
            # reader from reading it as measured for this direction alone.
            record["bounds_source"] = "finding" if self.bounds else "entry"
        if self.revisit_when:
            record["revisit_when"] = self.revisit_when
        return record


@dataclass
class Document:
    """One retrievable unit with the fields scoring and display both read."""

    identity: str
    kind: str          # case | skill | record
    state: str
    path: str | None   # corpus-relative when an entry has a file
    title: str
    summary: str
    fields: dict[str, str]
    applicability: Any = None
    limitations: tuple[str | dict[str, Any], ...] = ()
    findings: tuple[Finding, ...] = ()
    owner: str = ""
    qualified: str = ""
    root: Path | None = None
    source_url: str = ""    # where the observation was originally recorded
    source_location: str = ""
    locally_verified: bool | None = None
    backend: str | None = None
    ranked_sources: dict[str, bytes | None] = field(default_factory=dict)

    def unverified(self) -> bool:
        return self.locally_verified is False or any(
            item.get("locally_verified") is False if isinstance(item, dict)
            else isinstance(item, str) and "locally_verified=false" in item
            for item in self.limitations
        )

    def cohort(self) -> str:
        """The hardware and configuration this entry's observations belong to."""
        declared = self.applicability
        if isinstance(declared, list):
            return " · ".join(str(item) for item in declared)
        if isinstance(declared, dict):
            parts = [declared.get(key) for key in ("hardware", "scope")]
            return " · ".join(str(part) for part in parts if part)
        return str(declared) if declared else ""

    def relevant_finding_indices(self, query_tokens: list[str]) -> list[int]:
        """Rank this entry's findings by query overlap, then by recorded order.

        Scoring the whole entry says it is relevant; it does not say which of a
        dozen recorded directions the caller asked about. Ranking per finding
        keeps the answer first and reports how many were withheld.

        Weighting is computed over this entry's own findings, not the corpus. A
        term shared by every direction in the entry cannot separate them however
        rare it is elsewhere -- every direction in a Qwen case says Qwen -- while
        a term in one direction identifies it even if the corpus sees it often.
        Corpus-level idf gets this backwards at both ends, and collapses
        entirely when the library holds a single entry, where it rates every
        term identically and leaves the recorded order untouched.

        Findings that tie, including every finding when the query matches none,
        keep their recorded order. That order is the author's, and for a case it
        follows the sequence the directions were tried in.
        """
        if not self.findings:
            return []
        terms = [_term_counts(finding.search_text()) for finding in self.findings]
        appearances = Counter(token for counts in terms for token in counts)
        total = len(terms)
        ranked = []
        for position, counts in enumerate(terms):
            overlap = 0.0
            for token in query_tokens:
                hits = counts[token]
                if not hits:
                    continue
                carrying = appearances[token]
                # A term in most of the entry's directions cannot pick one out,
                # and in one-line findings its repetition would otherwise
                # outweigh a single hit on the term actually asked about.
                if total > 1 and carrying * 2 > total:
                    continue
                # Rarer within the entry means more distinguishing.
                overlap += math.log(total / carrying + 1.0) * math.sqrt(hits)
            ranked.append((-overlap, position))
        ranked.sort()
        return [position for _, position in ranked[:_MAX_SHOWN_FINDINGS]]

    def relevant_findings(self, query_tokens: list[str]) -> tuple[list[Finding], int]:
        shown = [self.findings[i] for i in self.relevant_finding_indices(query_tokens)]
        return shown, max(0, len(self.findings) - len(shown))

    def view(
        self, *, score: float, query_tokens: list[str] = (),
        read_args: tuple[str, ...] = (), unreadable: str | None = None,
    ) -> dict:
        record = {
            "id": self.identity,
            "kind": self.kind,
            "state": self.state,
            "score": round(score, 2),
            "title": self.title,
            "path": self.path,
        }
        if self.qualified:
            record["authority"] = self.qualified.partition(":")[0]
            if read_args:
                argv = [*launcher(), *read_args]
                record["read_args"] = list(read_args)
                record["open_argv"] = argv
                record["ref"] = shell_command(argv)
            elif unreadable is not None:
                record["unreadable"] = unreadable
        if self.source_location:
            record["source_location"] = self.source_location
        if self.source_url:
            record["source"] = self.source_url
        if self.summary:
            record["summary"] = self.summary.strip()[:_MAX_SNIPPET]
        if self.findings:
            shown, withheld = self.relevant_findings(list(query_tokens))
            record["findings"] = [
                finding.view(inherited_bounds=self.cohort()) for finding in shown
            ]
            record["findings_total"] = len(self.findings)
            if withheld:
                record["findings_withheld"] = withheld
        scope = self.applicability
        if isinstance(scope, dict):
            scope = scope.get("scope") or _flatten(scope)
        elif isinstance(scope, list):
            scope = " · ".join(str(item) for item in scope)
        if scope:
            record["applicability"] = str(scope).strip()[:_MAX_SNIPPET]
        if self.limitations:
            shown = []
            for limitation in self.limitations[:_MAX_SHOWN_LIMITATIONS]:
                preview = [*shown, limitation]
                preview_bytes = json.dumps(preview, ensure_ascii=False).encode("utf-8")
                if len(preview_bytes) > _MAX_LIMITATION_BYTES:
                    break
                shown = preview
            record["limitations"] = shown
            if len(shown) < len(self.limitations):
                record["limitations_withheld"] = len(self.limitations) - len(shown)
        if self.unverified():
            record["locally_verified"] = False
        return record


def launcher() -> list[str]:
    """How to start this CLI from where the caller is.

    The plugin records its own launcher. Package invocations use the current
    Python interpreter, including when the caller started with `python -m inferrsi`.
    """
    declared = os.environ.get("INFERRSI_LAUNCHER")
    if declared:
        try:
            argv = json.loads(declared)
        except ValueError:
            argv = None
        if isinstance(argv, list) and argv and all(isinstance(a, str) for a in argv):
            return argv
    return [sys.executable, "-X", "utf8", "-m", "inferrsi"]


def shell_command(argv: list[str]) -> str:
    """Render argv for a POSIX shell or, on Windows, PowerShell."""
    if os.name == "nt":
        return "& " + " ".join("'" + arg.replace("'", "''") + "'" for arg in argv)
    return shlex.join(argv)


def _source_url(record: dict) -> str:
    """The recorded location of the original observation, if the entry cites one.

    A case carries the report it was extracted from. Handing that back lets a
    reader check the finding against its source instead of taking the summary
    on trust.
    """
    for source in record.get("sources", []) or []:
        if isinstance(source, dict):
            for key in ("url", "evidence_url", "entry_url"):
                value = source.get(key)
                if isinstance(value, str) and value.startswith("https://"):
                    return value
    return ""


def _findings(record: dict, identity: str) -> tuple[Finding, ...]:
    declared = record.get("findings", [])
    if not isinstance(declared, list):
        raise ValueError(f"Case findings must be a list: {identity}")
    result = []
    for item in declared:
        if not isinstance(item, dict):
            raise ValueError(f"Case finding must be a mapping: {identity}")
        for key in ("direction", "outcome", "reason"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ValueError(f"Case finding requires {key}: {identity}")
        if item["outcome"] not in FINDING_OUTCOMES:
            raise ValueError(
                f"Unknown finding outcome {item['outcome']!r} in {identity}; "
                f"expected one of {', '.join(FINDING_OUTCOMES)}"
            )
        keywords = item.get("keywords", [])
        if not isinstance(keywords, list) or any(not isinstance(k, str) for k in keywords):
            raise ValueError(f"Case finding keywords must be a string list: {identity}")
        scope = item.get("scope", "")
        if scope and scope not in FINDING_SCOPES:
            raise ValueError(
                f"Unknown finding scope {scope!r} in {identity}; "
                f"expected one of {', '.join(FINDING_SCOPES)}"
            )
        bounds = item.get("bounds", "")
        if not isinstance(bounds, str):
            raise ValueError(f"Case finding bounds must be a string: {identity}")
        revisit_when = item.get("revisit_when", "")
        if not isinstance(revisit_when, str):
            raise ValueError(f"Case finding revisit_when must be a string: {identity}")
        result.append(Finding(
            direction=item["direction"], outcome=item["outcome"], reason=item["reason"],
            revisit_when=revisit_when, keywords=tuple(keywords),
            scope=scope, bounds=bounds,
        ))
    return tuple(result)


def _case_documents(root: Path, *, source_location: str) -> list[Document]:
    """Cases owned by the registered skills of this root.

    Discovery is delegated to the reader that `read` uses, rather than globbing
    for `cases/*.json` at a guessed depth. Two layouts diverged under the glob:
    a flat root, where each skill sits directly under it, put cases one level
    too shallow to be found at all; and a directory nested at the right depth
    but absent from skill-index.json was found here while `read` refused it,
    so a reported reference could not be opened. The owning reader decides
    which skills are registered, so both commands now agree by construction.
    """
    from .knowledge_operations import KnowledgeReader, case_resource_path

    documents = []
    for identity, path in sorted(KnowledgeReader(skill_root=root).cases().items()):
        declaration = path.read_bytes()
        record = json.loads(declaration.decode("utf-8"))
        try:
            body_path = case_resource_path(root, path, record.get("content"))
        except (ValueError, OSError):
            body_path = None
        body, raw_body = _body_source(body_path) if body_path is not None else ("", None)
        ranked_sources = {"case.json": _source_digest(declaration)}
        if body_path is not None:
            ranked_sources[record["content"]] = _source_digest(raw_body)
        findings = _findings(record, identity)
        backend = record.get("backend")
        documents.append(Document(
            identity=identity,
            kind="case",
            state=record.get("state", "unspecified"),
            path=body_path.relative_to(root).as_posix() if body_path is not None else None,
            title=identity.removeprefix("case."),
            summary=_flatten(record.get("attribution")),
            owner=path.parent.parent.name,
            qualified=f"checkout:{identity}",
            root=root,
            source_url=_source_url(record),
            source_location=source_location,
            fields={
                "title": identity.removeprefix("case.").replace("-", " "),
                "summary": _flatten(record.get("attribution")),
                "tags": " ".join(record.get("tags", [])),
                "findings": " ".join(finding.search_text() for finding in findings),
                "applicability": _flatten(record.get("applicability")),
                "body": body,
            },
            applicability=record.get("applicability"),
            limitations=tuple(record.get("limitations", [])),
            findings=findings,
            ranked_sources=ranked_sources,
            backend=backend if backend in (*BACKENDS, "common") else None,
        ))
    return documents


def _source_digest(raw: bytes | None) -> bytes | None:
    return hashlib.sha256(raw).digest() if raw is not None else None


def _body_source(path: Path, *, captured: bytes | None = None) -> tuple[str, bytes | None]:
    try:
        raw = path.read_bytes() if captured is None else captured
        return raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n"), raw
    except (OSError, UnicodeError):
        # Metadata can still match; read reports why the material is unavailable.
        return "", None


def _skill_description(body: str) -> str:
    from .skill_catalog import _frontmatter

    try:
        description = _frontmatter(BytesIO(body.encode("utf-8"))).get("description")
    except ValueError:
        # Keep simple descriptions searchable in base installs. The reader
        # reports missing PyYAML or invalid frontmatter for a returned hit.
        frontmatter = body.split("\n---", 1)[0] if body.startswith("---\n") else ""
        match = re.search(r"^description:[ \t]*(.+)$", frontmatter, re.MULTILINE)
        return match.group(1).strip().strip("'\"") if match else ""
    return description.strip() if isinstance(description, str) else ""


def _skill_documents(
    root: Path, *, source_location: str, searchspace_index: SearchspaceIndex | None = None,
) -> list[Document]:
    """Skills registered by this root, resolved the way `skills` and `read` do.

    Reading skill-index.json directly assumed every root is a generated library.
    A flat checkout registers its skills by having them directly under the root
    and carries no index, so the default search raised on a library whose cases
    `find` could already rank and `read` could already open.
    """
    from .skill_catalog import _sidecar_source, _skill_search_source, skill_registrations

    documents = []
    if searchspace_index is None:
        inputs = (
            (name, directory, backend, None)
            for name, (directory, backend) in sorted(skill_registrations(root).items())
        )
    else:
        inputs = (
            (name, source.directory, source.backend, source)
            for name, source in searchspace_index.ranking_skills()
        )
    for name, directory, backend, source in inputs:
        core = directory / "SKILL.md"
        body, raw_body = _body_source(core, captured=source.body if source is not None else None)
        try:
            body, metadata = _skill_search_source(body)
        except ValueError:
            # Malformed structured data is neither evidence nor instruction text.
            continue
        has_sidecar = (
            (directory / "metadata.json").exists() if source is None else source.sidecar_present
        )
        if metadata is not None and has_sidecar:
            continue
        raw_sidecar = None
        try:
            if metadata is None:
                if source is None:
                    metadata, raw_sidecar = _sidecar_source(directory)
                else:
                    raw_sidecar = source.sidecar
                    metadata = json.loads(raw_sidecar) if raw_sidecar is not None else None
                metadata = metadata or {}
        except (ValueError, OSError):
            metadata = {}
        # Task entrypoints remain addressable through the registry. Counting
        # an orientation page as evidence also changes IDF for every owner.
        if metadata.get("discovery_role") == "task-entry":
            continue
        description = _skill_description(body)
        applicability = metadata.get("applicability", {})
        scope = applicability.get("scope") if isinstance(applicability, dict) else applicability
        documents.append(Document(
            identity=name,
            kind="skill",
            state=metadata.get("status", "unspecified"),
            path=core.relative_to(root).as_posix(),
            title=name,
            summary=description or _flatten(scope),
            owner=metadata.get("backend", ""),
            qualified=f"checkout:{name}",
            root=root,
            source_url=_source_url(metadata),
            source_location=source_location,
            backend=backend,
            fields={
                "title": name.replace("-", " "),
                "summary": description,
                "tags": " ".join(metadata.get("tags", [])),
                "findings": "",
                "applicability": _flatten(applicability),
                "body": body,
            },
            applicability=applicability,
            limitations=tuple(metadata.get("limitations", [])),
            ranked_sources={"SKILL.md": _source_digest(raw_body),
                            "metadata.json": _source_digest(raw_sidecar)},
        ))
    return documents


def _record_documents(records: Iterable[dict]) -> list[Document]:
    """Imported engine records. Skill projections are skipped: the checkout
    documents above already cover them, and counting both double-ranks one
    owner under two identities."""
    from .knowledge_operations import _json

    documents = []
    for record in records:
        if record.get("index_type") == "packaged-skill":
            continue
        identity = record["id"]
        body = _flatten({
            key: value for key, value in record.items()
            if key not in (
                "id", "title", "summary", "tags", "applicability",
                "sources", "source_files", "skill_documents",
            )
        })
        documents.append(Document(
            identity=identity,
            kind="record",
            state=record.get("status", "unspecified"),
            path=None,
            title=record.get("title", identity),
            summary=record.get("summary", ""),
            owner=record.get("repo", ""),
            qualified=f"package:{identity}",
            source_url=_source_url(record),
            source_location="installed",
            locally_verified=record["verification"]["locally_verified"],
            backend=record["backend"],
            fields={
                "title": f"{record.get('title', '')} {identity.replace('.', ' ')}",
                "summary": record.get("summary", ""),
                "tags": " ".join(record.get("tags", [])),
                "findings": "",
                "applicability": _flatten(record.get("applicability")),
                "body": body,
            },
            applicability=record.get("applicability"),
            limitations=tuple(record.get("limitations", [])),
            ranked_sources={"record.json": _source_digest(_json(record))},
        ))
    return documents


class Corpus:
    """Documents plus their inverse document frequencies, read once."""

    def __init__(
        self, documents: list[Document], *, _searchspace_index: SearchspaceIndex | None = None,
    ):
        self.documents = documents
        self._searchspace_index = _searchspace_index
        total = len(documents)
        appearances = Counter()
        self._counts = [
            {name: _term_counts(text) for name, text in document.fields.items()}
            for document in documents
        ]
        lengths = [fields["body"].total() if "body" in fields else 0 for fields in self._counts]
        nonempty_lengths = [length for length in lengths if length]
        typical_length = median(nonempty_lengths) if nonempty_lengths else 1
        self._body_normalizers = [math.sqrt(max(1, length / typical_length)) for length in lengths]
        for fields in self._counts:
            appearances.update({token for counts in fields.values() for token in counts})
        self._idf = {
            token: math.log((total + 1) / (count + 1)) + 1.0
            for token, count in appearances.items()
        }
        self._unseen = math.log(total + 1) + 1.0

    def idf(self, token: str) -> float:
        return self._idf.get(token, self._unseen)

    def score(
        self, index: int, query_tokens: list[str], *, query_backend: str | None = None,
        ranking_policy: RankingPolicy = DEFAULT_RANKING_POLICY,
    ) -> tuple[float, dict]:
        """Sum of idf x field weight x sqrt(occurrences).

        The square root damps repetition. Bodies longer than the corpus median
        get a lower weight so broad manuals compete with much shorter cases
        through their specific matches. With one named backend, an entry
        registered for a different backend receives half its lexical score.
        """
        total = 0.0
        detail: dict[str, float] = {}
        weights = ranking_policy.weights
        body_weight = weights["body"] / self._body_normalizers[index]
        backend_weight = _backend_weight(self.documents[index].backend, query_backend)
        for token in query_tokens:
            weight = self.idf(token) * backend_weight
            for name, counts in self._counts[index].items():
                hits = counts[token]
                if hits:
                    field_weight = body_weight if name == "body" else weights[name]
                    gain = weight * field_weight * math.sqrt(hits)
                    total += gain
                    detail[token] = round(detail.get(token, 0.0) + gain, 2)
        return total, detail


def installed_skill_root() -> Path:
    """Resolve the library from the current installation."""
    return Path(files("inferrsi").joinpath("knowledge", "data", "skill_library")).resolve()


def installed_skill_projection(
    document: Document, records: Mapping[str, dict] | Callable[[str], dict | None],
) -> dict | None:
    """Find the generated record for this registered installed Skill identity."""
    if (
        document.kind != "skill" or document.source_location != "installed"
        or document.backend is None or document.root != installed_skill_root()
    ):
        return None
    lookup = records.get if isinstance(records, Mapping) else records
    record = lookup(packaged_skill_id(document.identity, document.backend))
    if record is None or record.get("index_type") != "packaged-skill":
        return None
    return record


def load_documents(
    skill_root: Path | None = None,
    *,
    kinds: tuple[str, ...] = ("case", "skill", "record"),
    records: Iterable[dict] | None = None,
    _searchspace_index: SearchspaceIndex | None = None,
) -> list[Document]:
    documents: list[Document] = []
    if "case" in kinds or "skill" in kinds:
        installed = installed_skill_root()
        root = installed if skill_root is None else Path(skill_root).resolve()
        if not root.is_dir():
            raise ValueError(f"Skill root is not a directory: {root}")
        source_location = "installed" if root == installed else "checkout"
        if "case" in kinds:
            documents.extend(_case_documents(root, source_location=source_location))
        if "skill" in kinds:
            documents.extend(_skill_documents(
                root, source_location=source_location, searchspace_index=_searchspace_index,
            ))
    if "record" in kinds:
        from .catalog import knowledge_records

        if records is None:
            records = knowledge_records(include_skill_views=False)
        documents.extend(_record_documents(records))
    identities = [document.qualified for document in documents]
    if len(set(identities)) != len(identities):
        duplicate = next(i for i, c in Counter(identities).items() if c > 1)
        raise ValueError(f"Duplicate identity in corpus: {duplicate}")
    return documents


def load_corpus(
    skill_root: Path | None = None, *, kinds: tuple[str, ...] = ("case", "skill", "record"),
    searchspace_index: SearchspaceIndex | None = None,
) -> Corpus:
    """Build a rankable corpus, using the verified Skill inputs if explicitly supplied."""
    if searchspace_index is None:
        return Corpus(load_documents(skill_root, kinds=kinds))
    if skill_root is not None and Path(skill_root).resolve() != searchspace_index.skill_root:
        raise ValueError("SearchSpace coordinate and Find corpus require the same Skill root")
    documents = load_documents(
        searchspace_index.skill_root, kinds=kinds, _searchspace_index=searchspace_index,
    )
    return Corpus(documents, _searchspace_index=searchspace_index)


@lru_cache(maxsize=1)
def _aliases() -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Query-side term map, longest key first so 前缀缓存 wins over 缓存.

    Two blocks, same rule. `aliases` routes a Chinese term to the English the
    corpus uses; `synonyms` covers English the corpus and its readers spell
    differently -- a caller asking about "startup" should reach a finding that
    says "initialization". Both expand one way, at query time only.
    """
    config = files("inferrsi").joinpath("knowledge", "data", "skill_library", "config")
    path = config.joinpath("query_aliases.json")
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("schema_version") != 1:
        raise ValueError("Query alias map requires schema_version 1")
    entries = []
    for block in ("aliases", "synonyms"):
        declared = record.get(block, {})
        if not isinstance(declared, dict):
            raise ValueError(f"Query alias map requires a {block} mapping")
        for term, expansions in declared.items():
            if not isinstance(expansions, list) or any(
                not isinstance(value, str) or not value.strip() for value in expansions
            ):
                raise ValueError(f"Query alias expansions must be nonempty strings: {term}")
            entries.append((term.casefold(), tuple(expansions)))
    if len({term for term, _ in entries}) != len(entries):
        raise ValueError("A term appears in both alias blocks")
    return tuple(sorted(entries, key=lambda entry: -len(entry[0])))


def expand(query: str) -> tuple[list[str], dict[str, tuple[str, ...]]]:
    """Return query tokens plus the corpus terms its aliased terms stand for.

    Expansion is query-side and one-way. Longest match wins and consumes its
    span, so 前缀缓存 does not also expand as 缓存 and score the narrower
    concept twice. A matched term keeps its own tokens as well: dropping them
    would lose a query that mixes a Chinese term with the English identifier
    beside it, which is how these queries are actually written.
    """
    folded = query.casefold()
    found = tokens(query)
    applied: dict[str, tuple[str, ...]] = {}
    for term, expansions in _aliases():
        # A latin term must match as a word: "nvram" is not "vram" and
        # "startups" is not "startup". CJK has no such boundaries, so a
        # substring is the match there.
        if _CJK.match(term):
            pattern = re.escape(term)
        else:
            pattern = rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])"
        match = re.search(pattern, folded)
        if match is None:
            continue
        applied[term] = expansions
        # Blank every occurrence so a shorter alias cannot match inside one.
        folded = re.sub(pattern, lambda hit: " " * len(hit.group()), folded)
        for expansion in expansions:
            found.extend(tokens(expansion))
    return [token for token in dict.fromkeys(found) if token not in _QUERY_STOP_WORDS], applied


def _query_backend(query: str) -> str | None:
    # A topic alias can add backend terms for matching, as 图模式 adds cuda graph.
    explicit_terms = {_BACKEND_NAME_ALIASES.get(term, term) for term in tokens(query)}
    backends = named_backends(explicit_terms)
    return next(iter(backends)) if len(backends) == 1 else None


def _backend_weight(backend: str | None, query_backend: str | None) -> float:
    return 0.5 if query_backend and backend in BACKENDS and backend != query_backend else 1.0


@dataclass
class _ReadPreview:
    args: tuple[str, ...]
    size: int
    bundle: Bundle
    view: dict
    source_args: tuple[str, ...]


def _read_preview(document: Document, readers: dict) -> _ReadPreview | None:
    """Validate a hit once and keep the exact material used for its preview."""
    from .knowledge_operations import KnowledgeReader

    if not document.qualified:
        return None
    reader = readers.get(document.root)
    if reader is None:
        reader = readers[document.root] = KnowledgeReader(skill_root=document.root)
    try:
        bundle = reader.read(document.qualified)
        material = bundle.view(material=True)
    except MissingSkillsExtra:
        if document.source_location != "installed":
            raise
        record = installed_skill_projection(document, reader.record)
        if record is None:
            raise
        package_reader = readers.get(None)
        if package_reader is None:
            package_reader = readers[None] = KnowledgeReader()
        ref = f"package:{record['id']}"
        bundle = package_reader.read(ref)
        view = bundle.view()
        core, _, _ = indexed_skill(record, {**view, "authority": "package"}, bundle.content)
        bundle.content[core].decode("utf-8")
        args = (
            "read", ref, "--omit-resources", "--resource", core, "--revision", view["revision"],
        )
        return _ReadPreview(args, len(bundle.content[core]), bundle, view, ())

    source_args = ()
    if document.root is not None:
        if document.source_location == "installed":
            source_args = ("--installed-library",)
        else:
            source_args = ("--skill-root", str(document.root))
    args = ("read", document.qualified, "--material", "--omit-resources", *source_args)
    size = len(material["content"].encode("utf-8"))
    return _ReadPreview(args, size, bundle, material, source_args)


_DECISION_SOURCE_UNAVAILABLE = "Source unavailable; repeat Find"


def _decision_links(
    hit: dict, document: Document, preview: _ReadPreview | None, tokens: list[str],
    query_backend: str | None,
) -> str | None:
    """Attach verified links, or return a public reason for withholding them."""
    from .decision_cards import DecisionSource
    from .skill_catalog import skill_registrations

    if preview is None:
        return _DECISION_SOURCE_UNAVAILABLE if document.qualified else "missing qualified reference"
    source = DecisionSource.from_bundle(preview.args[1], preview.bundle, preview.view)
    directory = PurePosixPath(source.body).parent if source.kind == "skill" else PurePosixPath()
    if source.kind == "skill":
        prefix = "data/skill_library/" if source.ref.startswith("package:") else ""
        if source.body != f"{prefix}{document.path}":
            return "Skill location changed after ranking; repeat Find"
        # Checkout bundles cover the Skill directory. Its registration lives in the root.
        if query_backend and source.ref.startswith("checkout:"):
            registration = skill_registrations(document.root).get(document.identity)
            if registration is None or (
                registration[0] / "SKILL.md" != document.root / document.path
                or _backend_weight(registration[1], query_backend)
                != _backend_weight(document.backend, query_backend)
            ):
                return "Skill registration changed after ranking; repeat Find"
    if not document.ranked_sources or any(
        _source_digest(preview.bundle.content.get(str(directory / name))) != expected
        for name, expected in document.ranked_sources.items()
    ):
        return "Source changed after ranking; repeat Find"

    def link(selector: str | None = None) -> dict:
        projection = source.project(finding=selector)
        args = ["read", source.ref, "--revision", source.revision, "--layer", "L1",
                *preview.source_args]
        if selector is not None:
            args += ["--finding", selector]
        return {"ref": source.ref, "revision": source.revision, "status": projection["status"],
                "card_bytes": projection["card_bytes"], "read_args": args,
                "open_argv": [*launcher(), *args]}

    if source.kind != "case":
        hit["decision_card"] = link()
        return None
    if not document.findings:
        return "no_findings"
    for row, index in zip(hit.get("findings", []), document.relevant_finding_indices(tokens)):
        row["decision_card"] = link(source.finding_locator(index))
    return None


def rank(
    query: str, corpus: Corpus, ranking_policy: RankingPolicy = DEFAULT_RANKING_POLICY,
) -> tuple[
    list[str], dict[str, tuple[str, ...]], list[tuple[float, int, int, dict]]
]:
    """Score matches without opening a Bundle or formatting a delivery."""
    query_backend = _query_backend(query)
    query_tokens, applied = expand(query)
    scored = []
    for index, document in enumerate(corpus.documents):
        value, detail = corpus.score(
            index, query_tokens, query_backend=query_backend, ranking_policy=ranking_policy,
        )
        if value > 0:
            scored.append((value, STATE_RANK.get(document.state, 0), index, detail))
    scored.sort(key=lambda row: (
        -row[0], -row[1], corpus.documents[row[2]].identity, corpus.documents[row[2]].qualified,
    ))
    return query_tokens, applied, scored


def _searchspace_entry(document: Document, index: SearchspaceIndex) -> SearchspaceEntry | None:
    from .searchspace_index import SearchspaceSourceMismatch

    if document.kind != "skill" or document.root is None or document.path is None:
        return None
    try:
        return index.entry(skill_root=document.root, skill_id=document.identity, path=document.path)
    except SearchspaceSourceMismatch:
        return None


def find(
    query: str,
    corpus: Corpus,
    *,
    limit: int = 5,
    explain: bool = False,
    decision_cards: bool = False,
    ranking_policy: RankingPolicy = DEFAULT_RANKING_POLICY,
    registry: "ChannelRegistry | None" = None,
    backend: str | None = None,
    platform: str | None = None,
    external_limit: int | None = None,
    external_timeout: float = 8.0,
    searchspace_coordinate: SearchspaceCoordinate | None = None,
    show_searchspace_coordinates: bool = False,
) -> dict:
    """Find local matches, optionally annotating them from the verified ranking source."""
    if type(limit) is not int or limit < 1:
        raise ValueError("limit must be a positive integer")
    query_tokens, applied, scored = rank(query, corpus, ranking_policy)
    query_backend = _query_backend(query) if decision_cards else None
    index = None
    if searchspace_coordinate is not None:
        index = searchspace_coordinate.index
        if corpus._searchspace_index is None or not index.same_source(corpus._searchspace_index):
            raise ValueError(
                "Load the Find corpus with a SearchSpace index from the same verified source"
            )
    elif show_searchspace_coordinates:
        index = corpus._searchspace_index
        if index is None:
            raise ValueError(
                "Load the Find corpus with a verified SearchSpace index to show coordinates"
            )
    if index is not None:
        index.require_current()
    if searchspace_coordinate is not None:
        resource, stage = searchspace_coordinate.resource, searchspace_coordinate.stage
        scored = [
            row for row in scored
            if (entry := _searchspace_entry(corpus.documents[row[2]], searchspace_coordinate.index))
            is not None and entry.matches(resource, stage)
        ]
    items = []
    readers: dict = {}
    for value, _, position, detail in scored[:limit]:
        document = corpus.documents[position]
        try:
            preview = _read_preview(document, readers)
            unreadable = None
        except (ValueError, KeyError, OSError, TypeError) as exc:
            preview, unreadable = None, str(exc) or type(exc).__name__
        view = document.view(
            score=value, query_tokens=query_tokens, read_args=preview.args if preview else (),
            unreadable=unreadable,
        )
        if preview:
            view["next_read_content_bytes"] = preview.size
        if decision_cards:
            try:
                reason = _decision_links(view, document, preview, query_tokens, query_backend)
            except (ValueError, KeyError, OSError, TypeError):
                reason = _DECISION_SOURCE_UNAVAILABLE
            if reason is not None:
                view["decision_card"] = {"status": "unavailable", "reason": reason}
        if explain:
            view["matched"] = detail
        if show_searchspace_coordinates and index is not None:
            entry = _searchspace_entry(document, index)
            if entry is not None:
                coverage = {
                    "state": entry.state,
                    "coordinates": [list(pair) for pair in sorted(entry.coordinates)],
                }
                if entry.exclusion_reason is not None:
                    coverage["exclusion_reason"] = entry.exclusion_reason
                view["searchspace_coordinates"] = coverage
        items.append(view)
    result = {
        "query": query,
        "tokens": query_tokens,
        "corpus_size": len(corpus.documents),
        "ranking_policy": ranking_policy.receipt(),
        "matched": len(scored),
        "items": items,
        "no_match": not scored,
        "limitations": [
            "Deterministic lexical ranking over titles, summaries, tags, findings "
            "and bodies; not a learned ranking or a claim that material applies.",
            "A match is textual. Read the cited state, applicability and "
            "limitations before relying on an entry.",
            "Paths are corpus-relative. Use read/resource for a pinned revision.",
        ],
    }
    if applied:
        # Report what a query term was taken to mean, so a wrong expansion is
        # visible in the result rather than only in the ranking.
        result["expanded"] = {term: list(values) for term, values in applied.items()}
    if index is not None:
        if items:
            index.require_current()
        if show_searchspace_coordinates:
            result["searchspace_source"] = index.source
    if searchspace_coordinate is not None:
        result["searchspace_filter"] = searchspace_coordinate.view()
    return _with_channels(
        result, query, registry=registry, backend=backend, platform=platform,
        external_limit=external_limit, external_timeout=external_timeout,
    )


def _with_channels(
    result: dict,
    query: str,
    *,
    registry: "ChannelRegistry | None",
    backend: str | None,
    platform: str | None,
    external_limit: int | None,
    external_timeout: float,
) -> dict:
    """Add the external column, or leave the result untouched when there is none.

    External hits stay out of `items`. They were not ranked on this corpus and
    are not locally verified, so putting them in the same list would let any
    caller that only reads `items` treat them as validated knowledge. The list
    is also absent rather than empty when no channel exists, so callers that
    predate channels see the output they always got.
    """
    if registry is None or not registry.channels:
        return result
    from .channels import explain_gate, search_channels

    declared = backend if backend is not None else registry.declared_backend
    results = search_channels(
        registry, query, backend=declared, platform=platform,
        limit=external_limit, timeout=external_timeout,
    )
    if declared is not None:
        result["backend"] = declared
    if results:
        result["external"] = [item.view() for item in results]
    gated = explain_gate(registry, declared)
    if gated:
        result.setdefault("external", []).extend(gated)
    if (results or gated) and all(
        getattr(channel, "navigation_only", False) for channel in registry.channels
    ):
        result["external_notes"] = [
            "External navigation follows source order and provides references only.",
        ]
    elif results or gated:
        result["external_notes"] = [
            "External results are not locally verified; scores are not "
            "comparable across channels.",
            "Pin the reported revision when citing an external locator.",
            "Open external cards with the channel's read command, not `read`.",
        ]
    return result
