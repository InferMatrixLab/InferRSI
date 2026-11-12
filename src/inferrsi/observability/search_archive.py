"""Validate the portable review input and its source-to-decision associations."""

import json
import re
from pathlib import Path

from .campaign_records import _identifier
from .dashboard_data import _relative_location, _text
from .optimization_log import _unique as _unique_pairs

_REVISION = re.compile(r"[A-Fa-f0-9]{40}|[A-Fa-f0-9]{64}")


def read_archive_review(path):
    """Read and validate the caller-reviewed portable attribution input."""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError("archive review is unavailable") from exc
    try:
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("archive review must be valid UTF-8 JSON") from exc
    if not isinstance(document, dict):
        raise ValueError("archive review must be a JSON object")
    required = {"task", "corpus", "decisions"}
    allowed = required | {"capture_returns", "result_note"}
    if required - set(document) or set(document) - allowed:
        raise ValueError("archive review is missing required fields or contains unknown fields")
    task = document["task"]
    if not isinstance(task, str) or not task.strip():
        raise ValueError("archive review task must be nonempty text")
    # The task is caller-reviewed prose, but still redact values forbidden by
    # the repository's existing display sanitizer before making it portable.
    task = _text(task, "Not recorded", limit=len(task))
    corpus = document["corpus"]
    if not isinstance(corpus, dict) or set(corpus) != {"repository", "revision", "root"}:
        raise ValueError("archive review corpus must declare repository, revision and root")
    repository, revision, corpus_root = (corpus.get("repository"), corpus.get("revision"),
                                         corpus.get("root"))
    repo_parts = repository.split("/") if isinstance(repository, str) else []
    if len(repo_parts) != 2:
        raise ValueError("archive review corpus.repository must be owner/repository")
    try:
        _identifier(repo_parts[0], "archive review repository owner")
        _identifier(repo_parts[1], "archive review repository name")
    except ValueError as exc:
        raise ValueError("archive review corpus.repository must be owner/repository") from exc
    if not isinstance(revision, str) or not _REVISION.fullmatch(revision):
        raise ValueError("archive review corpus.revision must be a full commit SHA")
    if (not isinstance(corpus_root, str) or not corpus_root
            or (corpus_root != "." and _relative_location(corpus_root) != corpus_root)):
        raise ValueError("archive review corpus.root must be a portable repository-relative path")
    corpus = {"repository": repository, "revision": revision.lower(), "root": corpus_root}

    raw_decisions = document["decisions"]
    if not isinstance(raw_decisions, list):
        raise ValueError("archive review decisions must be a list")
    decision_fields = {"use", "ref", "event_line", "passage_line", "decision_line",
                       "decision_quote"}
    for index, item in enumerate(raw_decisions):
        if not isinstance(item, dict) or set(item) not in (
                decision_fields, decision_fields | {"passage_path"}):
            raise ValueError(f"archive review decisions[{index}] has unsupported fields")
        if item["use"] not in ("used", "rejected"):
            raise ValueError(f"decisions[{index}].use must be used or rejected")
        ref = item["ref"]
        if not isinstance(ref, str) or _relative_location(ref) != ref:
            raise ValueError(f"decisions[{index}].ref must be a portable source ref")
        for key in ("event_line", "decision_line"):
            if type(item[key]) is not int or item[key] < 1:
                raise ValueError(f"decisions[{index}].{key} must be a positive line")
        passage_line = item["passage_line"]
        if passage_line is not None and (type(passage_line) is not int or passage_line < 1):
            raise ValueError(f"decisions[{index}].passage_line must be positive or null")
        quote = item["decision_quote"]
        if not isinstance(quote, str) or not quote.strip():
            raise ValueError(f"decisions[{index}].decision_quote must be nonempty text")
        # A quote is an exact evidence locator. If the archive sanitizer would
        # alter it, it cannot be presented as an exact quote in a public record.
        if _text(quote, "", limit=len(quote)) != quote:
            raise ValueError(f"decisions[{index}].decision_quote is not portable")
        if "passage_path" in item:
            passage_path = item["passage_path"]
            if (not isinstance(passage_path, str)
                    or _relative_location(passage_path) != passage_path):
                raise ValueError(f"decisions[{index}].passage_path must be portable")

    capture_returns = document.get("capture_returns", {})
    if not isinstance(capture_returns, dict):
        raise ValueError("archive review capture_returns must map context IDs to return lines")
    for context_id, line in capture_returns.items():
        _identifier(context_id, "archive review context ID")
        if type(line) is not int or line < 1:
            raise ValueError("archive review capture return lines must be positive integers")
    result_note = document.get("result_note")
    if result_note is not None:
        if not isinstance(result_note, str) or not result_note.strip():
            raise ValueError("archive review result_note must be nonempty text")
        result_note = _text(result_note, "Not recorded", limit=len(result_note))
    return {"task": task, "corpus": corpus, "decisions": raw_decisions,
            "result_note": result_note,
            "capture_returns": capture_returns}


def reviewed_uses(review, events, decisions):
    """Yield the material, disposition and portable evidence for each reviewed association."""
    by_line = {event.get("trace_line"): event for event in events
               if type(event.get("trace_line")) is int}
    for item in review["decisions"]:
        event = by_line.get(item["event_line"])
        if event is None:
            raise ValueError("event_line must reference an observed event in this round")
        delivery = event.get("delivery")
        if not isinstance(delivery, dict) or delivery.get("state") != "visible":
            raise ValueError("archive review must cite a verified delivered passage")
        return_line = delivery.get("return_line")
        if type(return_line) is not int or item["decision_line"] <= return_line:
            raise ValueError("archive review decision must follow the visible tool return")
        indexer_event = event.get("tool") == "collect"
        if indexer_event and not item.get("passage_path"):
            raise ValueError("Indexer review must name the exact captured resource path")
        if not indexer_event and "passage_path" in item:
            raise ValueError("passage_path is only valid for a verified Indexer return")
        passages = [entry for entry in delivery.get("passages", [])
                    if isinstance(entry, dict) and entry.get("ref") == item["ref"]
                    and entry.get("line") == item["passage_line"]
                    and ("passage_path" not in item
                         or entry.get("path") == item["passage_path"])]
        if item["passage_line"] is None and delivery.get("archive_omitted"):
            raise ValueError("source excerpt has no unique line locator; use a line-numbered read")
        if len(passages) > 1:
            raise ValueError("source excerpt has multiple matches; use a line-numbered read")
        passage = passages[0] if passages else None
        if passage is None or not isinstance(passage.get("text"), str) or not passage["text"]:
            raise ValueError("archive review must cite an exact delivered source passage")
        passage_text = passage["text"]
        if _text(passage_text, "", limit=len(passage_text)) != passage_text:
            raise ValueError("archive review source passage is not safe to publish")
        decision_text = decisions.get(item["decision_line"])
        if not isinstance(decision_text, str) or item["decision_quote"] not in decision_text:
            raise ValueError("decision_quote must match the assistant message exactly")
        event_id = event.get("id")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("archive review event is missing its stable public ID")
        evidence = {
            "use": item["use"], "basis": "archive_reviewed", "event_id": event_id,
            "passage_line": item["passage_line"], "passage_text": passage_text,
            "decision_line": item["decision_line"], "decision_quote": item["decision_quote"],
        }
        # The safety check above does not restore text altered during export.
        # Keep these flags with the adoption evidence, not only with delivery.
        for transformation in ("redacted", "root_normalized", "truncated"):
            if passage.get(transformation):
                evidence[f"passage_{transformation}"] = True
        if "passage_path" in item:
            evidence["passage_path"] = item["passage_path"]
        yield item["ref"], item["use"], evidence
