"""Compose the standalone Apps knowledge operations through Knowledge ports."""

import json
from hashlib import sha256
from pathlib import Path

from inferrsi.knowledge._skill_selection import INLINE_PAGE_BYTES, skill_procedure, text_page
from inferrsi.knowledge.knowledge_find import installed_skill_root
from inferrsi.knowledge.knowledge_operations import KnowledgeReader, resolve_resource_key
from inferrsi.knowledge.knowledge_store import KnowledgeStore


def _character_bytes(raw, start):
    end = start + 1
    while end < len(raw) and raw[end] & 0xc0 == 0x80:
        end += 1
    return end - start


def read_page(view, requested, *, source_hash=None, source_ranges=None):
    """Slice the UTF-8 material view; offsets always refer to the same pinned view."""
    if "content" not in view:
        if requested is not None:
            raise ValueError("--byte-range requires --material or --resource")
        return
    content = view["content"]
    raw = content.encode("utf-8")
    if requested is None:
        if len(raw) <= INLINE_PAGE_BYTES:
            serialized = json.dumps(content, ensure_ascii=False).encode("utf-8")
            if len(serialized) <= INLINE_PAGE_BYTES:
                return
        requested = (0, INLINE_PAGE_BYTES)
    start, length = requested
    if start < 0 or length < 1 or start > len(raw) or (start == len(raw) and start != 0):
        raise ValueError("--byte-range requires a valid start byte and a positive length")
    if start < len(raw) and raw[start] & 0xc0 == 0x80:
        raise ValueError("--byte-range must start at a UTF-8 character boundary")
    text, stop = text_page(raw, start, length)
    if stop == start and start < len(raw):
        raise ValueError(f"--byte-range needs at least {_character_bytes(raw, start)} bytes "
                         "for the next UTF-8 character")
    # Put the continuation coordinates before a potentially long stdout body.
    del view["content"]
    view["content_range"] = {
        "start": start, "end": stop, "total_bytes": len(raw),
        "first_line": raw.count(b"\n", 0, start) + 1,
    }
    if stop < len(raw):
        view["next_byte_range"] = [stop, max(length, _character_bytes(raw, stop))]
    if source_hash is not None or source_ranges is not None:
        # A Skill procedure omits frontmatter. Map the selected view bytes back
        # onto the already pinned source ranges, including pages crossing a gap.
        original = view.get("content_view", {})
        ranges, offset = [], 0
        for lo, hi in original.get("source_byte_ranges", source_ranges or [(0, len(raw))]):
            begin, end = max(start - offset, 0), min(stop - offset, hi - lo)
            if begin < end:
                ranges.append([lo + begin, lo + end])
            offset += hi - lo
        view["content_view"] = {"locator": "byte-range", "source_byte_ranges": ranges}
        if source_hash is not None:
            view["content_view"].update(source_sha256=source_hash,
                                        sha256=sha256(raw[start:stop]).hexdigest())
    view["content"] = text


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


def read_selected_hit(hit: dict, *, resource: str | None = None) -> tuple[dict, dict]:
    """Open a Find pin once. The tool response and the round receipt use the same bytes."""
    argv = hit["material_read_args"]
    root = installed_skill_root() if "--installed-library" in argv else None
    if "--skill-root" in argv:
        root = Path(argv[argv.index("--skill-root") + 1])
    store = Path(argv[argv.index("--store") + 1]) if "--store" in argv else None
    reader = knowledge_reader(skill_root=root, store_root=store)
    ref, bundle = reader.read_resolved(hit["material_ref"], revision=hit["revision"])
    view = bundle.view()
    body = hit["body_resource"]
    path = resolve_resource_key(body if resource is None else resource, body, bundle.content)
    if resource is not None and path != resource:
        view["body_resource"] = body
    raw = bundle.content[path]
    data, locator = skill_procedure(path, raw) if resource is None else (raw, {})
    content = data.decode("utf-8")
    digest = view["resources"][path]
    role = "reference" if path != hit["body_resource"] else (
        "record" if path == "record.json" else "core"
    )
    delivered = {"path": path, "role": role, "sha256": digest, "content": content}
    if locator:
        location = {**locator, "source_sha256": digest, "sha256": sha256(data).hexdigest()}
        delivered.update(location)
        view["content_view"] = location
    context = {"ref": ref, "revision": view["revision"], "resources": [delivered],
               "sources": view["sources"], "content_bytes": len(data), "omissions": []}
    view.pop("resources")
    view.pop("required_resources", None)
    view.update(ref=ref, content=content, content_resource=path)
    return view, context
