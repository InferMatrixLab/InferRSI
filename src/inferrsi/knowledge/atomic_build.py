"""Build the candidate Knowledge and host skill trees from the same authored inputs."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from .atomic_composition import AtomPin, applies, select_routes
from .atomic_generation import FORMAT, PUBLIC_TASKS, SEAL, InstalledGeneration, digest, owned_path
from .atomic_reader import atom_material, permits_operations
from .decision_cards import DecisionSource
from .knowledge_operations import IDENTITY, Bundle, _json, safe_path

_PUBLISH = {"read", "retain", "redistribute"}


def _complete_original(body: bytes, origin: dict) -> bool:
    return (origin["layer"] == "L3" and origin["source_byte_range"] == [0, len(body)]
            and origin["sha256"] == origin["source"].get("sha256"))


def _record_content(metadata: dict, node: str, material: dict) -> bytes:
    nodes = metadata["composition"]["nodes"]
    if not isinstance(node, str) or node not in nodes:
        raise ValueError("Record entrypoint must name a declared source node")
    pin = nodes[node]
    target = AtomPin(pin["ref"], pin["revision"])
    if target not in material:
        raise ValueError(f"Missing pinned Record source: {target.ref}")
    body, origin = material[target]
    if not _complete_original(body, origin):
        raise ValueError("Record entrypoint requires the complete L3 original")
    record = json.loads(body)
    if (not isinstance(record, dict) or record.get("id") != metadata["id"]
            or record.get("skill_documents")):
        raise ValueError("Record source must match its identity and be self-contained")
    return _json(record)


def _authored(directory, path, field, descriptor, material) -> tuple[AtomPin, Bundle]:
    metadata = descriptor["metadata"]
    if field not in metadata or ("atom" in metadata and "composition" in metadata):
        raise ValueError(f"{path.name} must declare one {field}")
    content = {}
    for name, value in descriptor.get("content", {}).items():
        safe_path(name)
        if isinstance(value, dict) and value.keys() == {"path"}:
            content[name] = owned_path(directory, value["path"]).read_bytes()
        elif (field == "composition" and metadata["kind"] == "knowledge"
              and name == metadata.get("entrypoint") == "record.json"
              and isinstance(value, dict) and value.keys() == {"record_node"}):
            content[name] = _record_content(metadata, value["record_node"], material)
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
    links = re.findall(r"\]\(<?(?:\./)?((?:references|assets|scripts)/[^\s)>#?]+)", markdown)
    if any(link not in resources for link in links):
        raise ValueError(f"Undeclared resource linked from host skill {name}")
    return name, output


def _verify_source(body: bytes, record: dict, roots: Mapping[str, Path]) -> bool:
    source, path = record["source"], record["source_path"]
    snapshot = source.get("sha256")
    if not isinstance(snapshot, str) or not re.fullmatch(r"[0-9a-f]{64}", snapshot):
        raise ValueError(f"Missing complete source file digest for {path}")
    if source.get("path", path) != path:
        raise ValueError(f"Atom path differs from its pinned source path: {path}")
    start, end = record["source_byte_range"]
    key = source.get("commit", snapshot)
    if key not in roots:
        if "commit" not in source and start == 0 and snapshot == record["sha256"]:
            return False
        raise ValueError(f"Missing pinned source root for {key} at {path}")
    original = owned_path(roots[key], path).read_bytes()
    if digest(original) != snapshot:
        raise ValueError(f"Complete pinned source file differs at {path}")
    if end > len(original) or original[start:end] != body:
        raise ValueError(f"Atom bytes differ from pinned source range at {path} [{start}, {end})")
    return True


def _authored_inputs(directory: Path, field: str, material: dict):
    for path in sorted(directory.glob("*.json")):
        if not re.fullmatch(IDENTITY, path.stem):
            raise ValueError(f"Invalid descriptor filename: {path.name}")
        descriptor = json.loads(owned_path(directory, path.name).read_bytes())
        pin, bundle = _authored(directory, path, field, descriptor, material)
        yield path.stem, pin, bundle
        if "parts" not in descriptor:
            continue
        if field != "atom" or len(bundle.content) != 1 or bundle.dependencies:
            raise ValueError("Atom parts require a single, self-contained original")
        body, origin = material[pin]
        if not _complete_original(body, origin):
            raise ValueError("Atom parts require a complete L3 source")
        parts = descriptor["parts"]
        if not isinstance(parts, dict) or not parts:
            raise ValueError("Atom parts must declare named source spans")
        for name, part in parts.items():
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
                raise ValueError(f"Invalid atom part name: {name}")
            start, end = part["byte_range"]
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(body):
                raise ValueError(f"Invalid source range for atom part {name}")
            pointers = part["pointers"]
            if (not isinstance(pointers, list) or not pointers
                    or not all(isinstance(ptr, str) and ptr.startswith("/") for ptr in pointers)):
                raise ValueError(f"Expected source JSON pointers for atom part {name}")
            atom = bundle.metadata["atom"]
            span = {**atom["source_span"], "byte_range": [start, end], "sha256": part["sha256"]}
            title = bundle.metadata.get("title", bundle.metadata["id"])
            fields = ", ".join(ptr.removeprefix("/") for ptr in pointers)
            child = Bundle({
                **bundle.metadata, "id": bundle.metadata["id"] + "." + name,
                "title": part.get("title", f"{title} — {fields}"),
                "summary": part.get("summary", bundle.metadata.get("summary", "")),
                "entrypoint": "excerpt",
                "atom": {**atom, "resource": "excerpt", "layer": part["layer"],
                         "source_span": span, "source_pointers": pointers},
            }, {"excerpt": body[start:end]}, {})
            child_pin = AtomPin(pin.ref + "." + name, child.revision)
            yield path.stem + "." + name, child_pin, child


def _prepare(source: Path, permits: Callable[[AtomPin, str], bool], roots: Mapping[str, Path]):
    files, entries, material, compositions = {}, {}, {}, {}
    skills = {}
    for family, field in (("atoms", "atom"), ("compositions", "composition")):
        directory = owned_path(source, family)
        if not directory.is_dir():
            raise ValueError(f"Missing authored {family} directory")
        for stem, pin, bundle in _authored_inputs(directory, field, material):
            if pin.ref in entries:
                raise ValueError(f"Duplicate qualified reference: {pin.ref}")
            view = bundle.view()
            declaration = view[field]
            if (not all(permits(pin, operation) for operation in _PUBLISH)
                    or not permits_operations(declaration, _PUBLISH)):
                raise PermissionError(f"Publication denied for {pin.ref}")
            applies(declaration["when"], {})
            prefix = f"knowledge/{family}/{stem}"
            if prefix + ".json" in files:
                raise ValueError(f"Duplicate generated manifest: {prefix}")
            files[prefix + ".json"] = _json(bundle.manifest())
            files.update({prefix + "/" + name: data for name, data in bundle.content.items()})
            entry = {"revision": pin.revision, "manifest": prefix + ".json", "kind": view["kind"]}
            for key in ("title", "summary"):
                if isinstance(view.get(key), str):
                    entry[key] = view[key]
            if field == "atom":
                material[pin] = atom_material(bundle, view)
                entry["source_range_verified"] = _verify_source(*material[pin], roots)
                entry["layer"] = declaration["layer"]
            else:
                compositions[pin] = bundle
            entries[pin.ref] = entry

    for pin, bundle in compositions.items():
        view = bundle.view()
        declaration = view["composition"]
        case = DecisionSource.from_bundle(pin.ref, bundle, view) if view["kind"] == "case" else None
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
    portable = {name.casefold() for name in files}
    parents = (p.as_posix().casefold() for name in files for p in PurePosixPath(name).parents)
    if len(portable) != len(files) or any(p in portable for p in parents):
        raise ValueError("Generation contains colliding resource paths")
    seal = {"format": FORMAT, "entries": entries, "skills": skills,
            "files": {name: digest(data) for name, data in files.items()}}
    generation = "sha256:" + digest(_json(seal))
    files[SEAL] = _json({**seal, "generation": generation})
    return generation, files


def build_generation(source: Path, target: Path, *, permits: Callable[[AtomPin, str], bool],
                     source_roots: Mapping[str, Path] | None = None) -> str:
    """Stage and verify a complete new generation; repeat installs must have identical bytes."""
    source = Path(source).resolve(strict=True)
    target = Path(target).absolute()
    if target.is_symlink() or target.resolve() != target:
        raise ValueError("Generation target must be a physical directory")
    if target.is_relative_to(source) or source.is_relative_to(target):
        raise ValueError("Separate the authored and installed generation roots")
    roots = {key: Path(path).resolve(strict=True) for key, path in (source_roots or {}).items()}
    generation, files = _prepare(source, permits, roots)
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
            return InstalledGeneration(target, expected=generation).generation
    return generation
