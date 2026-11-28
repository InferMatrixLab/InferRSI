"""Compose Apps knowledge operations through Knowledge and evidence ports."""

from pathlib import Path

from inferrsi import __version__
from inferrsi.harness.records import campaign_records, knowledge_capture
from inferrsi.knowledge.context_projection import assemble_context_text, context_item
from inferrsi.knowledge.knowledge_operations import KnowledgeReader, read_page, resolve_resource_key
from inferrsi.knowledge.knowledge_store import KnowledgeStore


def read_continuation(args, view):
    """Return an executable next-page command for the same selected material."""
    if "next_byte_range" not in view:
        return None
    command = ["read", args.id, "--revision", view["revision"], "--omit-resources"]
    if args.resource is not None:
        command.extend(["--resource", args.resource])
    elif args.material:
        command.append("--material")
    for flag, value in (("--skill-root", args.skill_root), ("--store", args.store),
                        ("--session", args.session), ("--search-ref", args.search_ref)):
        if value is not None:
            command.extend([flag, str(value)])
    if args.installed_library:
        command.append("--installed-library")
    command.extend(["--byte-range", *map(str, view["next_byte_range"])])
    return command


def open_knowledge_store(
    *, store_root: Path, skill_root: Path | None = None, writable: bool = False,
) -> KnowledgeStore:
    """Open one caller-authorized local store for history or an explicit write."""
    if type(writable) is not bool:
        raise ValueError("writable must be a boolean")
    return KnowledgeStore(store_root, skill_root=skill_root, read_only=not writable)


def knowledge_reader(
    *, skill_root: Path | None = None, store_root: Path | None = None,
) -> KnowledgeReader:
    """Select a Knowledge reader without enabling store writes."""
    store = (
        open_knowledge_store(store_root=store_root, skill_root=skill_root)
        if store_root is not None
        else None
    )
    return KnowledgeReader(skill_root=skill_root, store=store)


def read(
    reader: KnowledgeReader, reference: str, *, revision: str | None = None,
    material: bool = False, resource: str | None = None, byte_range=None,
) -> tuple[str, str, dict]:
    """Return the qualified reference, actual revision, and public Bundle view."""
    if byte_range is not None and revision is None:
        raise ValueError("--byte-range requires the exact --revision of the resource")
    qualified, bundle = reader.read_resolved(reference, revision=revision)
    view = bundle.view(material=material and resource is None)
    if resource is not None:
        body = view["entrypoint"]
        if qualified.startswith("package:"):
            body = view.get("skill_documents", {}).get("original", body)
        path = resolve_resource_key(resource, body, bundle.content)
        if path != resource:
            view["body_resource"] = body
        view.update(content=bundle.content[path].decode("utf-8"), content_resource=path)
    path = view.get("content_resource", view["entrypoint"])
    read_page(view, byte_range, source_hash=view["resources"][path])
    return qualified, view["revision"], view


def _captured_resource(resource: dict) -> dict:
    keys = ("path", "role", "sha256", "content")
    if resource.get("locator") == "skill-procedure":
        keys += ("locator", "source_sha256", "source_byte_ranges")
    return {key: resource[key] for key in keys}


def capture_contexts(result: dict) -> list[dict]:
    """Keep the pinned material, resource bytes and provenance used by a capture."""
    return [{
        "ref": context["ref"], "revision": context["revision"],
        "content_bytes": context["content_bytes"],
        "resources": [_captured_resource(resource) for resource in context["resources"]],
        "omissions": context["omissions"],
        "sources": context.get("sources", []),
    } for context in result.get("contexts", [])]


def prepare_retrieval(campaign, context_id, result, request, wrapper, diagnosis_binding):
    """Build a capture from the retrieval that actually ran."""
    retrieval = result.get("retrieval")
    if isinstance(retrieval, dict):
        retrieval = {**retrieval}
        if wrapper:
            retrieval.update(entrypoint=wrapper, calls=[wrapper, *retrieval["calls"]])
    request = request if request is not None else (retrieval or {}).get("request", {})
    observations = {item["ref"]: item for item in (retrieval or {}).get("items", [])}
    items = []
    for view in result.get("items", []):
        ref = view.get("ref") or "package:" + view["id"]
        items.append({**context_item({**view, "ref": ref}, provenance=True),
                      "revision": view.get("revision")
                      or observations.get(ref, {}).get("revision")})
    contexts = capture_contexts(result)
    return knowledge_capture.prepare_capture(
        campaign_id=campaign["campaign_id"], context_id=context_id,
        # Only the source categories are kept; store and checkout paths can be private.
        request=request,
        selection=result.get("selection"),
        items=items,
        omissions=result.get("omissions", []),
        context_omissions=result.get("context_omissions", []),
        context_budget=result.get("context_budget"),
        context_bytes_used=result.get("context_bytes"),
        contexts=contexts,
        assembled_text=assemble_context_text(contexts),
        retrieval=retrieval,
        diagnosis_binding=diagnosis_binding,
        # A result without an observation has no recorded entry point. It is
        # labelled unknown; a plausible current default is not evidence.
        captured_by=f"inferrsi {(retrieval or {}).get('entrypoint', 'unknown')} {__version__}",
    )


def collect_archive(
    root: Path, *, context_id: str, reader: KnowledgeReader, **options,
) -> dict:
    """Run Collect once and retain its result in a caller-selected manual evidence directory."""
    root = root.resolve()
    campaign_records.require_manual_campaign(root)
    manifest = knowledge_capture.capture_campaign(root, context_id)
    result = reader.collect(**options)
    result["retrieval"]["receipt_kind"] = "delivered_context"
    document = prepare_retrieval(manifest, context_id, result, None, None, None)
    path, digest = knowledge_capture.store_capture(root, document)
    return knowledge_capture.collect_envelope(document, path.relative_to(root).as_posix(), digest)
