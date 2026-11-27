"""Snapshot-bound evidence selection; no model calls or external fetching here."""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
from collections import Counter, deque
from copy import deepcopy
from pathlib import Path
from time import perf_counter
from urllib.parse import unquote, urlsplit

from ._skill_selection import (
    context_view,
    declared_skill_references,
    indexed_skill,
    is_license_or_notice,
    record_context,
    skill_procedure,
)
from .knowledge_find import installed_skill_projection, installed_skill_root, load_documents
from .knowledge_operations import KnowledgeReader, RevisionConflict, _store_document
from .retrieval import observation

CONDITION_FIELDS = (
    "backend",
    "hardware",
    "os",
    "model",
    "phase",
    "engine",
    "engine_version",
    "dependency_version",
    "dtype",
    "workload",
    "quality",
    "measurement",
)
METHOD = "full-catalog-v1"


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def digest(value):
    return "sha256:" + hashlib.sha256(encoded(value)).hexdigest()


class SelectionError(ValueError):
    def __init__(self, code, detail):
        super().__init__(detail)
        self.code = code


def _preview(value, size=400):
    text = value if isinstance(value, str) else encoded(value).decode()
    raw = text.encode()
    return raw[:size].decode("utf-8", errors="ignore"), len(raw) > size


def short_catalog(snapshot):
    """Project the entire pinned snapshot for selection; keep the full view addressable."""
    cards = []
    for full in snapshot["cards"]:
        card = {key: full[key] for key in ("ref", "kind", "conditions", "missing_conditions")}
        for key in ("summary", "limitations"):
            value = full[key]
            if not value or (key == "limitations" and value == "[]"):
                card[key] = None
                continue
            card[key], clipped = _preview(value, 200)
            if clipped or full["preview_truncated"][key]:
                card.setdefault("preview_truncated", []).append(key)
        if "unreadable" in full:
            card["unreadable"] = full["unreadable"]
        cards.append(card)
    return {**snapshot, "cards": cards, "card_bytes": len(encoded(cards)), "projection": "short"}


def validate_priority_questions(priority_questions):
    if not isinstance(priority_questions, (list, tuple)) or any(
        not isinstance(q, str) or not q.strip() for q in priority_questions
    ):
        raise ValueError("priority_questions must be a sequence of nonempty question strings")
    if len(set(priority_questions)) != len(priority_questions):
        raise ValueError("priority_questions must be unique")
    return list(priority_questions)


def _comparable_value(field, value):
    if not isinstance(value, str) or value.casefold() in {
        "unknown", "unspecified", "common", "any", "none"
    }:
        return False
    if field in ("engine_version", "dependency_version"):
        # Compare literal releases only. Wildcards, ranges and floating labels
        # require interpretation that an equality comparison cannot supply.
        return bool(re.fullmatch(
            r"v?\d+(?:\.\d+)*(?:[.-]?(?:a|b|alpha|beta|rc|post|dev)\.?\d+)?"
            r"(?:\+[a-z0-9]+(?:[.-][a-z0-9]+)*)?", value, re.IGNORECASE
        ))
    return bool(re.fullmatch(r"[\w.+:/-]+", value))


def compare_conditions(declared, task, *, purpose="conclusion", locators=None):
    """Exact scalar/list membership only. Prose, ranges and missing values stay unknown.

    A method can transfer as an analogy, but a mismatched bounded conclusion
    cannot. This verdict never modifies the source's validation state.
    """
    if purpose not in ("conclusion", "method"):
        raise ValueError("purpose must be conclusion or method")
    if not isinstance(task, dict) or set(task) - set(CONDITION_FIELDS):
        raise ValueError("conditions must use the documented condition fields")
    source = declared if isinstance(declared, dict) else {}
    comparisons = []
    for field, actual in task.items():
        expected = source.get(field)
        values = expected if isinstance(expected, list) else [expected]
        # Whitespace prose is not an enumerated condition. Versions must be exact;
        # source commits are deliberately not interpreted as engine versions.
        comparable = bool(values) and all(_comparable_value(field, v) for v in [actual, *values])
        result = (
            ("match" if actual.casefold() in [v.casefold() for v in values] else "conflict")
            if comparable
            else "unknown"
        )
        comparisons.append(
            {
                "field": field,
                "task": actual,
                "source": expected,
                "result": result,
                "locator": (locators or {}).get(field, f"applicability.{field}"),
            }
        )
    states = {c["result"] for c in comparisons}
    verdict = (
        ("analogue" if purpose == "method" else "conflict")
        if "conflict" in states
        else ("match" if states == {"match"} else "unknown")
    )
    return {
        "verdict": verdict,
        "purpose": purpose,
        "comparisons": comparisons,
        "missing": [c["field"] for c in comparisons if c["result"] == "unknown"],
        "scope": "declared fields only; prose and unrequested conditions require source review",
        "next_step": (
            "Validate the method on a minimal target workload before transfer."
            if verdict == "analogue"
            else "Check original bounds and task-required validation before using a claim."
        ),
    }


class _CatalogReader(KnowledgeReader):
    """Discovery cache confined to a content-checked catalog snapshot."""

    def __init__(self, **options):
        super().__init__(**options)
        self._case_paths = None
        self._checkout_ids = None

    def _cases(self, directories=None):
        if self._case_paths is None:
            self._case_paths = super()._cases(directories)
        return self._case_paths

    def _checkout_identities(self):
        if self._checkout_ids is None:
            self._checkout_ids = super()._checkout_identities()
        return self._checkout_ids

    def _skill(self, identity):
        return super()._skill(identity, complete_resources=True)


def _tree_version(root):
    """Hash current bytes and membership, without following directory symlinks.

    Stat/mtime shortcuts cannot detect same-size edits with restored timestamps.
    Links/redirects disable reuse: some record loaders can read their targets.
    Leave target access and validation to the existing readers, not this scan.
    """
    entries = []
    reusable = True

    def visit(directory, prefix="", ancestors=frozenset()):
        nonlocal reusable
        resolved = Path(directory).resolve()
        if resolved != Path(directory):
            reusable = False
        if not resolved.is_relative_to(root) or resolved in ancestors:
            reusable = False
            entries.append((prefix, "redirect", str(resolved)))
            return
        ancestors = ancestors | {resolved}
        with os.scandir(directory) as children:
            for child in sorted(children, key=lambda item: item.name):
                path = prefix + child.name
                if child.is_symlink():
                    reusable = False
                    entries.append((path, "symlink", os.readlink(child.path)))
                elif child.is_dir(follow_symlinks=False):
                    entries.append((path, "directory"))
                    visit(child.path, path + "/", ancestors)
                elif child.is_file(follow_symlinks=False):
                    entries.append((path, "file", hashlib.sha256(
                        Path(child.path).read_bytes()).hexdigest()))
                else:
                    entries.append((path, "other"))

    try:
        visit(root)
    except OSError:
        # The cache scans a superset of the files that the reader needs.
        # Let normal discovery/read report errors only for effective inputs.
        return None, False
    return digest(entries), reusable


class CatalogSelection:
    """A declared library plus package records and, optionally, a read-only store.

    Reuse a prepared view only while all source bytes and membership agree.
    Readers are discarded after completion or when any source changes.
    """

    def __init__(self, *, skill_root: Path | None = None, store=None):
        self.skill_root = Path(skill_root).resolve() if skill_root is not None else None
        self.store = store
        self._prepared = None

    def _reader(self):
        # Cases have checkout identities even in an installed library.
        return _CatalogReader(skill_root=self.skill_root or installed_skill_root())

    def _source_version(self):
        roots = {installed_skill_root(), self.skill_root or installed_skill_root()}
        libraries = [(str(root), *_tree_version(root)) for root in sorted(roots)]
        if any(version is None for _, version, _ in libraries):
            return None, False
        stored = ([] if self.store is None else [
            (identity, self.store.read(identity).revision)
            for identity in sorted(self.store.identities())
        ])
        return (digest({"libraries": libraries, "declared_root": str(self.skill_root),
                        "store": stored, "store_reader": id(self.store)}),
                all(reusable for _, _, reusable in libraries))

    def documents(self):
        documents = load_documents(self.skill_root)
        if self.store is not None:
            for identity in self.store.identities():
                bundle = self.store.read(identity)
                doc = _store_document(f"store:{identity}", bundle)
                doc.stored_bundle = bundle
                source_args = ("--skill-root", str(self.skill_root)) if self.skill_root else ()
                doc.store_args = (*source_args, "--store", str(self.store.workspace))
                doc.applicability = bundle.metadata["applicability"]
                doc.limitations = tuple(bundle.metadata["limitations"])
                documents.append(doc)
        return documents

    @staticmethod
    def _namespace(doc):
        # Store entrypoints are bundle-local, never paths in a checkout library.
        return (
            ("store", doc.qualified)
            if doc.qualified.startswith("store:")
            else (doc.source_location, str(doc.root))
        )

    def _load(self, *, kinds=("case", "skill", "record"), backend=None):
        if not kinds or set(kinds) - {"case", "skill", "record"}:
            raise ValueError("kinds must be a nonempty subset of case,skill,record")
        scope = (tuple(sorted(kinds)), backend)
        version, reusable = self._source_version()
        if reusable and self._prepared is not None and self._prepared[:2] == (scope, version):
            return self._prepared[2]
        self._prepared = None
        result = self._build(kinds=kinds, backend=backend)
        checked_version, checked_reusable = self._source_version()
        if version is not None and checked_version is not None and checked_version != version:
            raise SelectionError("stale_snapshot", "Sources changed while building the catalog")
        if reusable and checked_reusable:
            self._prepared = (scope, version, result)
        return result

    def _build(self, *, kinds, backend):
        reader = self._reader()
        documents = self.documents()
        cards, bundles, readers, docs = [], {}, {}, {}
        excluded = Counter()
        for doc in sorted(documents, key=lambda d: d.qualified):
            if doc.kind not in kinds:
                excluded["kind"] += 1
                continue
            if backend is not None and doc.backend not in (backend, "common"):
                excluded["backend_or_missing_backend"] += 1
                continue
            projection = installed_skill_projection(doc, reader.record)
            ref = f"package:{projection['id']}" if projection is not None else doc.qualified
            if ref in docs:
                raise SelectionError("ambiguous_identity", f"Duplicate catalog reference: {ref}")
            docs[ref] = doc
            summary, clipped = _preview(doc.summary)
            keywords, keywords_clipped = _preview(doc.fields.get("tags", ""))
            applicability, app_clipped = _preview(doc.applicability)
            limitations, lim_clipped = _preview(list(doc.limitations))
            card = {
                "ref": ref,
                "id": doc.identity,
                "kind": doc.kind,
                "title": doc.title,
                "summary": summary,
                "keywords": keywords,
                "applicability": applicability,
                "state": doc.state,
                "locally_verified": doc.locally_verified,
                "limitations": limitations,
                "preview_truncated": {
                    "summary": clipped,
                    "keywords": keywords_clipped,
                    "applicability": app_clipped,
                    "limitations": lim_clipped,
                },
                "source": {
                    "path": doc.path,
                    "location": doc.source_location,
                    "content_digest": digest(doc.fields),
                },
                "revision": None,
                "read_bytes": None,
                "references": [],
            }
            try:
                if ref.startswith("store:"):
                    bundle = self.store.read(ref.partition(":")[2])
                    selected_reader = KnowledgeReader(skill_root=self.skill_root, store=self.store)
                else:
                    selected_reader = reader
                    bundle = reader.read(ref)
                card.update(
                    revision=bundle.revision,
                    read_bytes=sum(map(len, bundle.content.values())),
                    entrypoint=bundle.metadata["entrypoint"],
                )
                bundles[ref], readers[ref] = bundle, selected_reader
            except (ValueError, OSError, KeyError) as exc:
                card["unreadable"] = {
                    "reason": getattr(exc, "code", type(exc).__name__),
                    "error_type": type(exc).__name__,
                }
            # Use the same normalized conditions for selection and post-read
            # judgment. Legacy checkout frontmatter is resolved by the reader.
            declared = (bundles[ref].metadata["applicability"] if ref in bundles
                        else doc.applicability)
            conditions = ({k: v for k, v in declared.items() if k in CONDITION_FIELDS}
                          if isinstance(declared, dict) else {})
            locators = {}
            if not conditions.get("backend") and doc.backend:
                conditions["backend"] = doc.backend
                locators["backend"] = doc.backend_locator
            card.update(conditions=conditions, condition_locators=locators,
                        missing_conditions=[k for k in CONDITION_FIELDS if not conditions.get(k)])
            cards.append(card)
        paths = {}
        for ref, doc in docs.items():
            if doc.path:
                paths.setdefault((self._namespace(doc), doc.path), []).append(ref)
        references = {}
        for card in cards:
            doc = docs[card["ref"]]
            refs = []
            for match in re.finditer(
                r"\[[^\]]*\]\(([^\s)]+)(?:\s+[^)]*)?\)", doc.fields.get("body", "")
            ):
                target = match.group(1)
                edge = {"source_path": doc.path, "reference": target}
                try:
                    parsed = urlsplit(target)
                except ValueError:
                    edge.update(kind="unresolved", reason="invalid_url")
                    if edge not in refs:
                        refs.append(edge)
                    continue
                if parsed.query:
                    edge["kind"] = "unsupported_version_or_query"
                elif parsed.scheme or parsed.netloc:
                    edge["kind"] = "external_pointer"
                elif not parsed.path:
                    continue
                else:
                    path = posixpath.normpath(
                        posixpath.join(posixpath.dirname(doc.path or ""), unquote(parsed.path))
                    )
                    key = (self._namespace(doc), path)
                    if key in paths:
                        if len(paths[key]) == 1:
                            edge.update(kind="entry", ref=paths[key][0])
                        else:
                            edge.update(kind="ambiguous_reference", refs=paths[key])
                    else:
                        bundle = bundles.get(card["ref"])
                        choices = [path, "data/skill_library/" + path, unquote(parsed.path)]
                        resource = next(
                            (p for p in choices if bundle and p in bundle.content), None
                        )
                        edge.update(kind="resource" if resource else "unresolved", path=resource)
                if edge not in refs:
                    refs.append(edge)
            if doc.kind == "record" and card["ref"].startswith("package:"):
                record = reader.record(doc.identity)
                for edition, path in record.get("skill_documents", {}).items():
                    refs.append(
                        {
                            "kind": "resource",
                            "path": path,
                            "reference": path,
                            "source_path": f"record.json#skill_documents.{edition}",
                        }
                    )
            if doc.source_url:
                refs.append(
                    {
                        "kind": "external_pointer",
                        "reference": doc.source_url,
                        "source_path": doc.path,
                    }
                )
            references[card["ref"]] = refs
            card["references"] = refs[:3]
            card["references_withheld"] = max(0, len(refs) - 3)
        scope = {
            "sources": ["declared-library", "package-records"]
            + (["store"] if self.store is not None else []),
            "library": "installed" if self.skill_root is None else "checkout",
            "kinds": sorted(kinds),
            "backend": backend,
            "excluded": dict(excluded),
            "considered": len(documents),
        }
        identity = digest({"scope": scope, "cards": cards, "references": references})
        counts = dict(Counter(c["kind"] for c in cards))
        return (
            {
                "schema_version": 1,
                "method": METHOD,
                "snapshot_id": identity,
                "scope": scope,
                "counts": counts,
                "cards": cards,
                "references": references,
                "card_bytes": len(encoded(cards)),
                "condition_coverage": {
                    k: sum(k in c["conditions"] for c in cards) for k in CONDITION_FIELDS
                },
            },
            bundles,
            readers,
        )

    def snapshot(self, **scope):
        # Callers can edit prompt dictionaries without corrupting the retained view.
        return deepcopy(self._load(**scope)[0])

    @staticmethod
    def _context(reader, ref, revision, available, required_only=False):
        bundle = reader.read(ref, revision=revision)
        if bundle.metadata["kind"] != "skill" and not ref.startswith("store:"):
            # Use Collect's projectors on the pinned bundle, including when no bytes remain.
            authority, _, identity = ref.partition(":")
            view = {**bundle.view(), "ref": ref, "authority": authority}
            record = reader.records()[identity] if authority == "package" else {}
            try:
                if record.get("index_type") == "packaged-skill":
                    index = indexed_skill(record, view, bundle.content)
                    if required_only:
                        core, required, optional = index
                        context, omission = context_view(
                            (core, required, []), view, bundle.content, None, available
                        )
                        if context:
                            context["omissions"].extend(
                                {"path": path, "reason": "optional_not_requested"}
                                for path in optional
                            )
                        return context, omission
                    return context_view(index, view, bundle.content, None, available)
                return record_context(record, view, bundle.content, available)
            except (ValueError, KeyError, TypeError) as exc:
                return None, {"ref": ref, "reason": "index_unavailable",
                              "error_type": type(exc).__name__}
        # Direct skills and store bundles need their complete declared closure.
        # Collect's generic record context intentionally only opens an entrypoint.
        resources = []
        for path, raw in sorted(bundle.content.items()):
            content, locator = skill_procedure(path, raw)
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                return None, {"ref": ref, "reason": "required_resource_not_utf8", "path": path}
            resources.append(
                {
                    "path": path,
                    "content": text,
                    "role": "required",
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "source_sha256": hashlib.sha256(raw).hexdigest(),
                    "locator": "whole-resource",
                    **locator,
                }
            )
        size = sum(len(r["content"].encode()) for r in resources)
        if size > available:
            return None, {"ref": ref, "reason": "context_limit",
                          "required_bytes": size, "available_bytes": available}
        return {
            "ref": ref,
            "revision": revision,
            "resources": resources,
            "content_bytes": size,
            "sources": bundle.metadata["sources"],
            "attribution": bundle.metadata["attribution"],
            "limitations": bundle.metadata["limitations"],
            "omissions": [],
        }, None

    @staticmethod
    def _reference_context(reader, ref, path, revision, available, *, delivered_paths=()):
        bundle = reader.read(ref, revision=revision)
        if path not in bundle.content:
            return None, {"ref": ref, "path": path, "reason": "required_resource_unavailable"}
        required = [path]
        if path.endswith("SKILL.md"):
            from .catalog import _skill_search_source

            prefix = posixpath.dirname(path) + "/"
            # Same conservative owner closure as direct reader._skill. Markdown
            # cross-owner navigation is optional and must not become a dependency.
            required = [path, *(p for p in sorted(bundle.content)
                                if p.startswith(prefix) and p != path)]
            _, metadata = _skill_search_source(bundle.content[path].decode("utf-8"))
            sidecar = prefix + "metadata.json"
            if metadata is None and sidecar in bundle.content:
                metadata = json.loads(bundle.content[sidecar])
            metadata = metadata or {}
            for relative in declared_skill_references(metadata):
                target = posixpath.normpath(prefix + relative)
                if target not in bundle.content or "\\" in relative:
                    return None, {"ref": ref, "path": relative,
                                  "reason": "required_resource_unavailable"}
                if target not in required:
                    required.append(target)
            for resource in list(required):
                directory = posixpath.dirname(resource)
                while True:
                    for source in bundle.content:
                        if (posixpath.dirname(source) == directory
                                and is_license_or_notice(posixpath.basename(source))
                                and source not in required):
                            required.append(source)
                    if not directory:
                        break
                    directory = posixpath.dirname(directory)
        view = {**bundle.view(), "ref": ref}
        # All paths belong to this same ref/revision. Validate the full closure
        # above, then charge and deliver only bytes not already in its context.
        required = [resource for resource in required if resource not in delivered_paths]
        return context_view((path, required, []), view, bundle.content, None, available)

    def complete(self, snapshot_id, selections, **options):
        try:
            return self._complete(snapshot_id, selections, **options)
        except RevisionConflict as exc:
            raise SelectionError(
                "stale_snapshot", "Source revision changed; refresh and reselect"
            ) from exc
        finally:
            # Returned source metadata must not become mutable input to a later call.
            self._prepared = None

    def _complete(
        self,
        snapshot_id,
        selections,
        *,
        conditions=None,
        context_bytes=65536,
        expansion_depth=1,
        expansion_items=5,
        expansion_bytes=32768,
        priority_questions=(),
        **scope,
    ):
        started = perf_counter()
        for name, value, minimum in (
            ("context_bytes", context_bytes, 1),
            ("expansion_depth", expansion_depth, 0),
            ("expansion_items", expansion_items, 0),
            ("expansion_bytes", expansion_bytes, 0),
        ):
            if type(value) is not int or value < minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}")
        conditions = {} if conditions is None else conditions
        compare_conditions({}, conditions)
        snapshot, bundles, readers = self._load(**scope)
        if snapshot_id != snapshot["snapshot_id"]:
            raise SelectionError(
                "stale_snapshot", "Sources changed; fetch a new snapshot and reselect"
            )
        cards = {c["ref"]: c for c in snapshot["cards"]}
        if not isinstance(selections, list):
            raise ValueError("selections must be a list")
        selected = {}
        for selection in selections:
            if not isinstance(selection, dict):
                raise ValueError("Each selection must be an object")
            ref = selection.get("ref")
            if not isinstance(ref, str) or ref not in cards:
                raise SelectionError(
                    "outside_snapshot", "Select a qualified ref from this snapshot"
                )
            if ref in selected:
                raise SelectionError("duplicate_identity", f"Repeated selection: {ref}")
            if not isinstance(selection.get("reason"), str) or not selection["reason"].strip():
                raise ValueError("Each selection needs a reason")
            if not isinstance(selection.get("questions"), list) or any(
                not isinstance(q, str) for q in selection["questions"]
            ):
                raise ValueError("Each selection needs a questions list (possibly empty)")
            compare_conditions({}, conditions, purpose=selection.get("purpose", "conclusion"))
            selected[ref] = selection
        priorities = validate_priority_questions(priority_questions)
        queue = deque()
        seen = set()
        contexts, judgments, omissions, paths = [], [], [], []
        used = optional_used = optional_count = 0

        def read_entry(ref, depth, via):
            nonlocal used, optional_used, optional_count
            card = cards[ref]
            identity = (ref, card["revision"])
            if identity in seen:
                paths.append({"ref": ref, "via": via, "stop": "cycle_or_duplicate"})
                return None
            seen.add(identity)
            if depth and optional_count >= expansion_items:
                paths.append({"ref": ref, "via": via, "stop": "item_budget"})
                return None
            if ref not in bundles:
                omissions.append({"ref": ref, "scope": "entry", "reason": "unreadable",
                                  "detail": card["unreadable"]})
                return None
            available = context_bytes - used if not depth else expansion_bytes - optional_used
            context, omission = self._context(
                readers[ref], ref, card["revision"], available, bool(priorities)
            )
            if omission is not None:
                omissions.append({**omission, "scope": "entry", "via": via})
                paths.append({"ref": ref, "via": via, "stop": "context_unavailable"})
                return None
            amount = context["content_bytes"]
            if depth:
                optional_used += amount
                optional_count += 1
            else:
                used += amount
            contexts.append(context)
            selection = selected.get(ref, {})
            judgment = compare_conditions(
                card["conditions"],
                conditions,
                purpose=selection.get("purpose", "conclusion"),
                locators=card["condition_locators"],
            )
            judgment.update(
                ref=ref,
                revision=card["revision"],
                source_state=card["state"],
                verification=bundles[ref].metadata.get("verification"),
                evidence_resources=[r["path"] for r in context["resources"]],
                confirmation="structured_only; Agent must confirm prose bounds",
                questions=selection.get("questions", []),
            )
            judgments.append(judgment)
            paths.append(
                {
                    "ref": ref,
                    "revision": card["revision"],
                    "via": via,
                    "depth": depth,
                    "status": "delivered",
                    "bytes": amount,
                }
            )
            return context, judgment

        linked = deque()

        def expand(ref, depth, context, judgment):
            nonlocal optional_used, optional_count
            card = cards[ref]
            if not snapshot["references"][ref]:
                paths.append({"ref": ref, "stop": "no_explicit_references"})
            for edge in snapshot["references"][ref]:
                trail = {"from": ref, **edge}
                if edge["kind"] == "entry":
                    if depth >= expansion_depth:
                        paths.append({"via": trail, "stop": "depth_budget"})
                    elif priorities:
                        pair = read_entry(edge["ref"], depth + 1, trail)
                        if pair:
                            linked.append((edge["ref"], depth + 1, *pair))
                    else:
                        queue.append((edge["ref"], depth + 1, trail))
                elif edge["kind"] == "resource":
                    path = edge["path"]
                    delivered_paths = {r["path"] for r in context["resources"]}
                    if path in delivered_paths:
                        paths.append({"via": trail, "stop": "reader_resource_delivered"})
                        continue
                    if depth >= expansion_depth or optional_count >= expansion_items:
                        paths.append({"via": trail, "stop": "depth_or_item_budget"})
                        continue
                    try:
                        extra, omission = self._reference_context(
                            readers[ref], ref, path, card["revision"],
                            expansion_bytes - optional_used, delivered_paths=delivered_paths,
                        )
                    except RevisionConflict:
                        raise
                    except (ValueError, KeyError, TypeError, OSError) as exc:
                        omission = {"ref": ref, "reason": "invalid_resource",
                                    "error_type": type(exc).__name__}
                    if omission:
                        paths.append({"via": trail, "stop": omission["reason"]})
                        omissions.append({"path": path, **omission, "scope": "resource",
                                          "via": trail})
                        continue
                    amount = extra["content_bytes"]
                    optional_used += amount
                    optional_count += 1
                    context["resources"].extend(extra["resources"])
                    context["content_bytes"] += amount
                    judgment["evidence_resources"].extend(r["path"] for r in extra["resources"])
                    judgments.append(
                        {
                            "ref": ref,
                            "revision": card["revision"],
                            "resource": path,
                            "verdict": "unknown",
                            "source_state": card["state"],
                            "reason": "Resource prose bounds require Agent confirmation",
                            "evidence_resources": [r["path"] for r in extra["resources"]],
                        }
                    )
                    paths.append({"via": trail, "status": "delivered", "bytes": amount})
                else:
                    paths.append({"via": trail, "stop": edge["kind"]})

        plan = {}
        if priorities:
            pending = set(selected)
            covered = set()
            direct = []
            attempted = []

            def rank(ref):
                new = set(selected[ref]["questions"]) - covered
                first = next((i for i, q in enumerate(priorities) if q in new), len(priorities))
                return first, -len(new), ref

            while pending:
                ref = min(pending, key=rank)
                pending.remove(ref)
                attempted.append(ref)
                pair = read_entry(ref, 0, None)
                if pair:
                    covered.update(selected[ref]["questions"])
                    direct.append((ref, pair))
            plan = {"priority_questions": priorities, "direct_read_order": attempted,
                    "questions_without_delivery": [q for q in priorities if q not in covered]}
            for ref, pair in direct:
                expand(ref, 0, *pair)
            while linked:
                expand(*linked.popleft())
        else:
            queue.extend((ref, 0, None) for ref in selected)
        while queue:
            ref, depth, via = queue.popleft()
            pair = read_entry(ref, depth, via)
            if pair:
                expand(ref, depth, *pair)
        # Detect mutations during assembly as well as before it; return no stale payload.
        if self.snapshot(**scope)["snapshot_id"] != snapshot_id:
            raise SelectionError(
                "stale_snapshot", "Sources changed during read; refresh and reselect"
            )
        trace = observation(
            entrypoint="catalog-select",
            request={"conditions": conditions},
            selection={"method": METHOD, "snapshot_id": snapshot_id,
                       "selections": selections, **plan},
            items=[
                {
                    "ref": c["ref"],
                    "revision": c["revision"],
                    "delivered": True,
                    "agent_read": "unknown",
                    "adopted": "unknown",
                }
                for c in contexts
            ],
            counts={
                "candidates": len(cards),
                "selected": len(selected),
                "delivered": len(contexts),
            },
            assembly={
                "paths": paths,
                "omissions": omissions,
                "content_bytes": used,
                "expansion_bytes": optional_used,
                "elapsed_seconds": perf_counter() - started,
            },
        )
        return {
            "snapshot_id": snapshot_id,
            "contexts": contexts,
            "judgments": judgments,
            "omissions": omissions,
            "retrieval": trace,
        }
