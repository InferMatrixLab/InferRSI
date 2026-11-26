"""Build the candidate Knowledge and host skill trees from the same authored inputs."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from .atomic_composition import AtomPin, applies, select_routes
from .atomic_generation import PUBLIC_TASKS, SEAL, InstalledGeneration, digest, owned_path
from .atomic_reader import atom_material, permits_operations
from .decision_cards import DecisionSource
from .knowledge_operations import IDENTITY, Bundle, _json, safe_path

_PUBLISH = {"read", "retain", "redistribute"}


def _authored(directory: Path, path: Path, field: str) -> tuple[AtomPin, Bundle]:
    descriptor = json.loads(owned_path(directory, path.name).read_bytes())
    metadata = descriptor["metadata"]
    if field not in metadata or ("atom" in metadata and "composition" in metadata):
        raise ValueError(f"{path.name} must declare one {field}")
    content = {}
    for name, value in descriptor.get("content", {}).items():
        safe_path(name)
        if isinstance(value, dict) and value.keys() == {"path"}:
            content[name] = owned_path(directory, value["path"]).read_bytes()
        elif (isinstance(value, dict) and value.keys() == {"text"}
              and isinstance(value["text"], str)):
            content[name] = value["text"].encode()
        else:
            raise ValueError(f"Expected one text or relative path for {name} in {path.name}")
    if field == "composition" and "entrypoint" not in metadata and metadata["kind"] != "case":
        metadata["entrypoint"] = "navigation.json"
        if "navigation.json" in content:
            raise ValueError("Explicit navigation content must declare its entrypoint")
        content["navigation.json"] = _json(metadata[field])
    bundle = Bundle(metadata, content, descriptor.get("dependencies", {}))
    ref = descriptor.get("authority", "package") + ":" + metadata["id"]
    return AtomPin(ref, bundle.revision), bundle


def _host_skill(declaration: dict, nodes: dict, material: dict) -> tuple[str, dict[str, bytes]]:
    name, description = declaration["name"], declaration["description"]
    if (not isinstance(name, str) or len(name) > 64
            or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name)):
        raise ValueError(f"Invalid host skill name: {name}")
    if not isinstance(description, str) or not 1 <= len(description.strip()) <= 1024:
        raise ValueError(f"Invalid host skill description: {name}")
    if declaration["body"] not in nodes:
        raise ValueError(f"Undeclared navigation node for host skill {name}")
    sections = declaration.get("sections", [])
    if not isinstance(sections, list) or not all(isinstance(key, str) and key in nodes
                                                  for key in sections):
        raise ValueError(f"Host skill {name} must declare each procedure section as a node")
    pins = [nodes[key] for key in (declaration["body"], *sections)]
    if material[pins[0]][1]["layer"] != "L0":
        raise ValueError(f"Host skill {name} must start at an L0 navigation atom")
    if len(set(pins)) != len(pins):
        raise ValueError(f"Repeated host skill section in {name}")
    # Authored spans own their whitespace. Preserve the exact procedure in declared order.
    body = b"".join(material[pin][0] for pin in pins)
    markdown = body.decode("utf-8")
    quoted = json.dumps(description, ensure_ascii=False)
    header = f"---\nname: {json.dumps(name)}\ndescription: {quoted}\n---\n\n".encode()
    output = {f"skills/{name}/SKILL.md": header + body}
    resources = declaration.get("resources", {})
    for relative, node in resources.items():
        if safe_path(relative).partition("/")[0] not in {"references", "assets", "scripts"}:
            raise ValueError(f"Unsupported host skill resource: {relative}")
        if "/" not in relative:
            raise ValueError(f"Expected a file inside a host resource directory: {relative}")
        if node not in nodes:
            raise ValueError(f"Undeclared resource node {node} for host skill {name}")
        output[f"skills/{name}/{relative}"] = material[nodes[node]][0]
    # Check direct Markdown resource links throughout the generated skill, including fragments.
    links = re.findall(r"\]\(<?(?:\./)?((?:references|assets|scripts)/[^\s)>#?]+)", markdown)
    if any(link not in resources for link in links):
        raise ValueError(f"Undeclared resource linked from host skill {name}")
    return name, output


def _prepare(source: Path, permits: Callable[[AtomPin, str], bool]):
    files, entries, material, compositions = {}, {}, {}, {}
    skills = {}
    for family, field in (("atoms", "atom"), ("compositions", "composition")):
        directory = owned_path(source, family)
        if not directory.is_dir():
            raise ValueError(f"Missing authored {family} directory")
        for path in sorted(directory.glob("*.json")):
            if not re.fullmatch(IDENTITY, path.stem):
                raise ValueError(f"Invalid descriptor filename: {path.name}")
            pin, bundle = _authored(directory, path, field)
            if pin.ref in entries:
                raise ValueError(f"Duplicate qualified reference: {pin.ref}")
            view = bundle.view()
            declaration = view[field]
            if (not all(permits(pin, operation) for operation in _PUBLISH)
                    or not permits_operations(declaration, _PUBLISH)):
                raise PermissionError(f"Publication denied for {pin.ref}")
            applies(declaration["when"], {})
            prefix = f"knowledge/{family}/{path.stem}"
            files[prefix + ".json"] = _json(bundle.manifest())
            files.update({prefix + "/" + name: data for name, data in bundle.content.items()})
            entry = {"revision": pin.revision, "manifest": prefix + ".json", "kind": view["kind"]}
            for key in ("title", "summary"):
                if isinstance(view.get(key), str):
                    entry[key] = view[key]
            if field == "atom":
                material[pin] = atom_material(bundle, view)
                entry["layer"] = declaration["layer"]
            else:
                compositions[pin] = bundle
            entries[pin.ref] = entry

    for pin, bundle in compositions.items():
        view = bundle.view()
        declaration = view["composition"]
        case = DecisionSource.from_bundle(pin.ref, bundle, view) if view["kind"] == "case" else None
        # Validates every route, edge, condition and original finding, including inactive routes.
        select_routes(declaration, layer="L0", context={}, case=case, finding=None)
        nodes = {key: AtomPin(node["ref"], node["revision"])
                 for key, node in declaration["nodes"].items()}
        for node in nodes.values():
            if node not in material:
                raise ValueError(f"Missing pinned atom {node.ref} at {node.revision} for {pin.ref}")
        for route in declaration["routes"].values():
            layers = {material[nodes[name]][1]["layer"] for name in route["required"]}
            if route["layer"] not in layers:
                raise ValueError(f"No required root supplies {route['layer']} for {pin.ref}")
        if "skill" in declaration:
            name, output = _host_skill(declaration["skill"], nodes, material)
            if name in skills:
                raise ValueError(f"Multiple compositions export host skill {name}")
            skills[name] = pin.ref
            files.update(output)
    missing = PUBLIC_TASKS - skills.keys()
    if missing:
        raise ValueError(f"Missing public task compositions: {', '.join(sorted(missing))}")
    # Collisions on case-insensitive filesystems must fail on all build hosts.
    portable = {name.casefold() for name in files}
    parents = (p.as_posix().casefold() for name in files for p in PurePosixPath(name).parents)
    if len(portable) != len(files) or any(p in portable for p in parents):
        raise ValueError("Generation contains colliding resource paths")
    seal = {"format": 1, "entries": entries, "skills": skills,
            "files": {name: digest(data) for name, data in files.items()}}
    generation = "sha256:" + digest(_json(seal))
    files[SEAL] = _json({**seal, "generation": generation})
    return generation, files


def build_generation(source: Path, target: Path, *, permits: Callable[[AtomPin, str], bool]) -> str:
    """Stage and verify a complete new generation; repeat installs must have identical bytes."""
    source = Path(source).resolve(strict=True)
    target = Path(target).absolute()
    if target.is_symlink() or target.resolve() != target:
        raise ValueError("Generation target must be a physical directory")
    if target.is_relative_to(source) or source.is_relative_to(target):
        raise ValueError("Separate the authored and installed generation roots")
    generation, files = _prepare(source, permits)
    if target.exists():
        return InstalledGeneration(target, expected=generation).generation
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".atomic-build-", dir=target.parent) as staging:
        root = Path(staging) / "generation"
        for name, data in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        InstalledGeneration(root, expected=generation)
        try:
            root.rename(target)
        except OSError:
            if not target.is_dir():
                raise
            # Another builder may have published the same immutable destination first.
            return InstalledGeneration(target, expected=generation).generation
    return generation
