"""Build the pinned sections, relative resources and host export of a self-contained Skill."""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import PurePosixPath

from ._skill_selection import skill_procedure
from .atomic_composition import AtomPin, select_routes
from .atomic_generation import directory_skill_path, owned_path
from .knowledge_operations import Bundle, _checkout_skill_resources, safe_path
from .skill_catalog import _effective, _frontmatter_parts


def skill_spans(body: bytes) -> dict:
    _, procedure = skill_procedure("SKILL.md", body)
    header = re.match(rb"\A---[ \t]*\r?\n.*?^---[ \t]*(?:\r?\n|\Z)", body, re.M | re.S)
    if not procedure or not header:
        raise ValueError("Skill sections require a complete guide with embedded decision metadata")
    navigation_end = procedure["source_byte_ranges"][0][1]
    public, _ = _frontmatter_parts(BytesIO(body[:navigation_end] + b"---\n"))
    if not all(isinstance(public.get(key), str) and public[key].strip()
               for key in ("name", "description")):
        raise ValueError("Skill navigation must include its original name and description")
    return {"navigation": ("L0", 0, navigation_end), "decision": ("L1", 0, header.end()),
            "procedure": ("L2", header.end(), len(body))}


def _verify_directory_routes(declaration, bindings, guide, source, material, dependencies):
    sections = skill_spans(guide)
    if any(any(route.get(key) for key in ("when", "optional", "supersedes", "conflicts"))
           for route in declaration["routes"].values()):
        raise ValueError("Directory routes must preserve their unconditional delivery")
    nodes = declaration["nodes"]
    file_pins = {path: AtomPin(nodes[name]["ref"], nodes[name]["revision"])
                 for path, name in bindings.items()}
    for layer, names in (("L0", ["navigation"]), ("L1", ["decision"]),
                         ("L2", ["decision", "procedure"]), ("L3", [])):
        selected = select_routes(declaration, layer=layer, context={}, case=None, finding=None)
        pins = list(dict.fromkeys(use.pin for use in selected.required))
        if layer == "L3":
            if set(pins) != set(file_pins.values()):
                raise ValueError("Skill L3 must deliver the complete original directory")
            continue
        if layer == "L2":
            if pins[len(names):] != [file_pins[path] for path in dependencies]:
                raise ValueError("Skill L2 must deliver its declared original references")
            pins = pins[:len(names)]
        actual = []
        for pin in pins:
            if pin not in material:
                raise ValueError(f"Missing pinned Skill section: {pin.ref}")
            origin = material[pin][1]
            if origin["source"] != source:
                raise ValueError(f"Skill {layer} must deliver its own pinned guide sections")
            actual.append((origin["layer"], *origin["source_byte_range"]))
        if actual != [sections[name] for name in names]:
            raise ValueError(f"Skill {layer} must deliver its own pinned guide sections")


def directory_dependencies(metadata, bindings, content, origins, material, roots) -> dict[str, str]:
    """Verify the original Skill directory and derive the explicitly declared file revisions."""
    entry = PurePosixPath(safe_path(metadata["entrypoint"]))
    if (not isinstance(bindings, dict) or entry.as_posix() not in bindings
            or entry.name != "SKILL.md" or entry.parent.name != metadata["id"]):
        raise ValueError("Skill directory must bind its original SKILL.md and identity")
    source = origins[entry.as_posix()]
    original = PurePosixPath(source["path"])
    if (source != metadata["sources"][0] or original.parts[-len(entry.parts):] != entry.parts
            or not roots or source.get("commit") not in roots):
        raise ValueError("Skill directory requires its pinned source root")
    library_prefix = PurePosixPath(*original.parts[:-len(entry.parts)])
    for name, origin in origins.items():
        if (source.get("repo") != origin.get("repo") or source["commit"] != origin.get("commit")
                or library_prefix / name != PurePosixPath(origin["path"])):
            raise ValueError(f"Skill resource differs from its original relative source: {name}")
    root = roots[source["commit"]]
    directory = owned_path(root, original.parent.as_posix())
    library = root / library_prefix
    released, dependencies = _checkout_skill_resources(
        library, directory, _effective(directory).get("references", []),
    )
    if content != released or metadata["required_resources"] != sorted(released):
        raise ValueError("Skill directory bindings must cover the complete original directory")
    _verify_directory_routes(metadata["composition"], bindings, content[entry.as_posix()],
                             source, material, dependencies)
    return dependencies


def export_directory_skill(bundle: Bundle) -> tuple[str, dict[str, bytes]]:
    name = bundle.metadata["id"]
    entry = PurePosixPath(bundle.metadata["entrypoint"])
    header, _ = _frontmatter_parts(BytesIO(bundle.content[entry.as_posix()]))
    description = header.get("description")
    if (len(name) > 64 or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name)
            or header.get("name") != name or not isinstance(description, str)
            or not 1 <= len(description.strip()) <= 1024):
        raise ValueError("Directory Skill must have a valid matching host name and description")
    return name, {directory_skill_path(bundle.metadata, path): raw
                  for path, raw in bundle.content.items()}
