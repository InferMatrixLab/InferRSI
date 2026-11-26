"""Compose the standalone Apps knowledge operations through Knowledge ports."""

from pathlib import Path

from inferrsi.knowledge.atomic_reader import AtomicReader, GroupDelivery, PinnedSource
from inferrsi.knowledge.knowledge_operations import KnowledgeReader, safe_path
from inferrsi.knowledge.knowledge_store import KnowledgeStore


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
    material: bool = False, resource: str | None = None,
) -> tuple[str, str, dict]:
    """Return the qualified reference, actual revision, and public Bundle view."""
    qualified, bundle = reader.read_resolved(reference, revision=revision)
    view = bundle.view(material=material and resource is None)
    if resource is not None:
        path = safe_path(resource)
        if path not in bundle.content:
            raise ValueError(f"Unknown resource: {path}")
        view.update(content=bundle.content[path].decode("utf-8"), content_resource=path)
    return qualified, view["revision"], view


def read_selection(source: PinnedSource, reference: str, *, permits, **request) -> GroupDelivery:
    """Ordinary Apps read of a fixed composition using this project's grants."""
    return AtomicReader(source, permits=permits).read_selection(reference, **request)
