"""One ranked lookup across packaged skills, records and checkout cases.

This is the discovery half of the knowledge interface. It answers "what is
already known about this problem" and returns corpus-relative paths, so the
caller can read, grep around, or stop. The audit half lives in ``read`` /
``resource``: exact identities, pinned revisions and content hashes.

Three properties separate this from the existing ``collect`` selection path:

* Cases participate. A rejected direction is the material a retrieval system
  can supply that re-reading the current source cannot, so it is ranked beside
  skills rather than excluded until its owner is already chosen.
* Nothing is filtered on the query. Requiring every token to appear is a hard
  cut on short queries; ranking degrades instead, and ``limit`` truncates.
* Scoring reads the entries directly. Bundle closures may contain unrelated
  files. The reader checks material only for results offered to the caller.

Ranking is lexical, with query-side aliases. The caller assesses applicability.
"""

from __future__ import annotations

import json
import math
import os
import re
import shlex
import sys
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from statistics import median
from typing import Any

# Author-written intent outranks bulk prose: a term in a title is evidence the
# document is about it, the same term in a long body often is not.
FIELD_WEIGHTS = {
    "title": 5.0,
    "summary": 4.0,
    "tags": 4.0,
    "findings": 4.0,
    "applicability": 2.0,
    "body": 1.0,
}

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
_MAX_SNIPPET = 400
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
    limitations: tuple[str, ...] = ()
    findings: tuple[Finding, ...] = ()
    owner: str = ""
    qualified: str = ""
    root: Path | None = None
    source_url: str = ""    # where the observation was originally recorded

    def unverified(self) -> bool:
        return any("locally_verified=false" in _flatten(item) for item in self.limitations)

    def cohort(self) -> str:
        """The hardware and configuration this entry's observations belong to."""
        declared = self.applicability
        if isinstance(declared, list):
            return " · ".join(str(item) for item in declared)
        if isinstance(declared, dict):
            parts = [declared.get(key) for key in ("hardware", "scope")]
            return " · ".join(str(part) for part in parts if part)
        return str(declared) if declared else ""

    def relevant_findings(self, query_tokens: list[str]) -> tuple[list[Finding], int]:
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
            return [], 0
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
            ranked.append((-overlap, position, self.findings[position]))
        ranked.sort(key=lambda row: (row[0], row[1]))
        shown = [finding for _, _, finding in ranked[:_MAX_SHOWN_FINDINGS]]
        return shown, max(0, len(self.findings) - len(shown))

    def view(
        self, *, score: float, query_tokens: list[str] = (), unreadable: str | None = None
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
            if unreadable is None:
                read_args = _read_args(self.qualified, self.root)
                argv = [*launcher(), *read_args]
                record["read_args"] = list(read_args)
                record["open_argv"] = argv
                record["ref"] = shell_command(argv)
            else:
                record["unreadable"] = unreadable
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
            record["limitations"] = list(self.limitations)
        if self.unverified():
            record["locally_verified"] = False
        return record


def _read_args(identity: str, root: Path | None = None) -> tuple[str, ...]:
    """CLI arguments that return the entry's text, not just its metadata.

    Without `--material`, `read` reports the entrypoint's filename in `content`
    rather than the file; a caller following the reference lands on a name.
    Kept as an argument list so a program can run it without re-parsing, and
    so quoting is decided once, for the shell the command will be shown in.
    """
    parts = ["read", identity, "--material", "--omit-resources"]
    if root is not None:
        parts += ["--skill-root", str(root)]
    return tuple(parts)


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


def _case_documents(root: Path) -> list[Document]:
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
        record = json.loads(path.read_text(encoding="utf-8"))
        try:
            body_path = case_resource_path(root, path, record.get("content"))
        except (ValueError, OSError):
            body_path = None
        findings = _findings(record, identity)
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
            fields={
                "title": identity.removeprefix("case.").replace("-", " "),
                "summary": _flatten(record.get("attribution")),
                "tags": " ".join(record.get("tags", [])),
                "findings": " ".join(finding.search_text() for finding in findings),
                "applicability": _flatten(record.get("applicability")),
                "body": _body_text(body_path) if body_path is not None else "",
            },
            applicability=record.get("applicability"),
            limitations=tuple(record.get("limitations", [])),
            findings=findings,
        ))
    return documents


def _body_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        # Metadata can still match; read reports why the material is unavailable.
        return ""


def _skill_documents(root: Path) -> list[Document]:
    """Skills registered by this root, resolved the way `skills` and `read` do.

    Reading skill-index.json directly assumed every root is a generated library.
    A flat checkout registers its skills by having them directly under the root
    and carries no index, so the default search raised on a library whose cases
    `find` could already rank and `read` could already open.
    """
    from .skill_catalog import _sidecar, skill_directories

    documents = []
    for name, directory in sorted(skill_directories(root).items()):
        core = directory / "SKILL.md"
        body = _body_text(core)
        description = ""
        frontmatter = body.split("\n---", 1)[0] if body.startswith("---\n") else ""
        match = re.search(r"^description:[ \t]*(.+)$", frontmatter, re.MULTILINE)
        if match:
            description = match.group(1).strip().strip("'\"")
        try:
            metadata = _sidecar(directory) or {}
        except (ValueError, OSError):
            metadata = {}
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
        ))
    return documents


def _record_documents() -> list[Document]:
    """Imported engine records. Skill projections are skipped: the checkout
    documents above already cover them, and counting both double-ranks one
    owner under two identities."""
    from .catalog import knowledge_records

    documents = []
    for record in knowledge_records():
        if record.get("index_type") == "packaged-skill":
            continue
        identity = record["id"]
        body = _flatten({
            key: value for key, value in record.items()
            if key not in ("sources", "source_files", "skill_documents", "id")
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
        ))
    return documents


class Corpus:
    """Documents plus their inverse document frequencies, read once."""

    def __init__(self, documents: list[Document]):
        self.documents = documents
        total = len(documents)
        appearances = Counter()
        self._counts = [
            {name: _term_counts(text) for name, text in document.fields.items()}
            for document in documents
        ]
        lengths = [fields["body"].total() if "body" in fields else 0 for fields in self._counts]
        nonempty_lengths = [length for length in lengths if length]
        typical_length = median(nonempty_lengths) if nonempty_lengths else 1
        self._body_weights = [
            FIELD_WEIGHTS["body"] / math.sqrt(max(1, length / typical_length))
            for length in lengths
        ]
        for fields in self._counts:
            appearances.update({token for counts in fields.values() for token in counts})
        self._idf = {
            token: math.log((total + 1) / (count + 1)) + 1.0
            for token, count in appearances.items()
        }
        self._unseen = math.log(total + 1) + 1.0

    def idf(self, token: str) -> float:
        return self._idf.get(token, self._unseen)

    def score(self, index: int, query_tokens: list[str]) -> tuple[float, dict]:
        """Sum of idf x field weight x sqrt(occurrences).

        The square root damps repetition. Bodies longer than the corpus median
        get a lower weight so broad manuals compete with much shorter cases
        through their specific matches. Every matched term contributes.
        """
        total = 0.0
        detail: dict[str, float] = {}
        body_weight = self._body_weights[index]
        for token in query_tokens:
            weight = self.idf(token)
            for name, counts in self._counts[index].items():
                hits = counts[token]
                if hits:
                    field_weight = body_weight if name == "body" else FIELD_WEIGHTS[name]
                    gain = weight * field_weight * math.sqrt(hits)
                    total += gain
                    detail[token] = round(detail.get(token, 0.0) + gain, 2)
        return total, detail


def load_corpus(
    skill_root: Path, *, kinds: tuple[str, ...] = ("case", "skill", "record")
) -> Corpus:
    root = Path(skill_root).resolve()
    if not root.is_dir():
        raise ValueError(f"Skill root is not a directory: {root}")
    documents: list[Document] = []
    if "case" in kinds:
        documents.extend(_case_documents(root))
    if "skill" in kinds:
        documents.extend(_skill_documents(root))
    if "record" in kinds:
        documents.extend(_record_documents())
    identities = [document.qualified for document in documents]
    if len(set(identities)) != len(identities):
        duplicate = next(i for i, c in Counter(identities).items() if c > 1)
        raise ValueError(f"Duplicate identity in corpus: {duplicate}")
    return Corpus(documents)


@lru_cache(maxsize=1)
def _aliases() -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Query-side term map, longest key first so 前缀缓存 wins over 缓存.

    Two blocks, same rule. `aliases` routes a Chinese term to the English the
    corpus uses; `synonyms` covers English the corpus and its readers spell
    differently -- a caller asking about "startup" should reach a finding that
    says "initialization". Both expand one way, at query time only.
    """
    path = files("inferrsi").joinpath("knowledge", "data", "query_aliases.json")
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
    return found, applied


def _why_unreadable(document: Document, readers: dict) -> str | None:
    """Open the entry the way `read` would; return why not, or None if it opens.

    Ranking reads files directly, which is what lets it skip Bundle closures,
    but it means a hit can be indexed and still refused by `read`: a source
    record missing the version `read` requires, or a case whose body file was
    never copied. Offering a command known to fail is worse than offering
    none, so only the hits actually returned are checked -- a handful of
    reads, not the corpus -- and a failing one reports why instead.

    A missing optional dependency is reported against the hit like any other
    reason it cannot be opened here. Ranking itself needs no parser, so the
    search must not fail for it; the caller learns which hits need PyYAML
    to open, and can still open every case, which does not.
    """
    from .knowledge_operations import KnowledgeReader

    if not document.qualified:
        return None
    reader = readers.get(document.root)
    if reader is None:
        reader = readers[document.root] = KnowledgeReader(skill_root=document.root)
    try:
        reader.read(document.qualified).view(material=True)
    except (ValueError, KeyError, OSError, TypeError) as exc:
        return str(exc) or type(exc).__name__
    return None


def find(query: str, corpus: Corpus, *, limit: int = 5, explain: bool = False) -> dict:
    if type(limit) is not int or limit < 1:
        raise ValueError("limit must be a positive integer")
    query_tokens, applied = expand(query)
    scored = []
    for index, document in enumerate(corpus.documents):
        value, detail = corpus.score(index, query_tokens)
        if value > 0:
            scored.append((value, STATE_RANK.get(document.state, 0), index, detail))
    scored.sort(key=lambda row: (
        -row[0], -row[1], corpus.documents[row[2]].identity, corpus.documents[row[2]].qualified,
    ))
    items = []
    readers: dict = {}
    for value, _, index, detail in scored[:limit]:
        document = corpus.documents[index]
        view = document.view(
            score=value, query_tokens=query_tokens, unreadable=_why_unreadable(document, readers)
        )
        if explain:
            view["matched"] = detail
        items.append(view)
    result = {
        "query": query,
        "tokens": query_tokens,
        "corpus_size": len(corpus.documents),
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
    return result
