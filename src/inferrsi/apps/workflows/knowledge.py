"""Compose the standalone Apps knowledge operations through Knowledge ports."""

from pathlib import Path

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
