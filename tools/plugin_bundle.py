"""Shared standalone host-plugin packaging from canonical runtime bytes."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


def _io_path(path: Path) -> Path:
    # Deep knowledge resource names must also work when Windows long-path
    # support is disabled. Keep normal paths in user-facing output.
    path = path.resolve()
    if os.name == "nt" and not str(path).startswith("\\\\?\\"):
        return Path("\\\\?\\UNC\\" + str(path)[2:] if str(path).startswith("\\\\")
                    else "\\\\?\\" + str(path))
    return path


def _json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _version(path: Path) -> str:
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            if isinstance(value, str):
                return value
    raise ValueError("Runtime __version__ is missing")


def _zip_tree(root: Path, destination: Path, prefix: str = "") -> None:
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                info = zipfile.ZipInfo(
                    prefix + path.relative_to(root).as_posix(),
                    date_time=(1980, 1, 1, 0, 0, 0),
                )
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                bundle.writestr(info, path.read_bytes())


def build_bundle(
    output: Path, *, template_path: str, metadata_file: str, readme: str,
    project: Path = PROJECT, release_version: str | None = None, nested: bool = False,
    compact_runtime: bool = False,
) -> dict:
    """Create a fresh distribution; never replace user configuration or earlier builds."""
    output = output.resolve()
    package = output / "inferrsi" if nested else output
    archive = output.with_name(output.name + ".zip")
    if output.exists() or archive.exists():
        raise ValueError("Output or archive already exists; select a fresh --output directory")
    project = project.resolve()
    for protected in ("src", "plugins", "docs", "tests", "tools"):
        if output.is_relative_to(project / protected) or output == project:
            raise ValueError("Output must be outside the source directories")

    source = _io_path(project / "src" / "inferrsi")
    template = _io_path(project / template_path)
    generated = source / "_version.py"
    runtime_version = _version(generated if generated.is_file() else source / "__init__.py")
    if release_version is not None:
        number = r"(?:0|[1-9][0-9]*)"
        if not re.fullmatch(rf"{number}\.{number}\.{number}", release_version):
            raise ValueError("Release version must have the numeric form MAJOR.MINOR.PATCH")
        if release_version != runtime_version:
            raise ValueError(
                "Release version must match the built runtime; build the runtime first"
            )
    _io_path(output.parent).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="irsi-", dir=_io_path(output.parent)) as staging:
        plugin = Path(staging) / "inferrsi"
        shutil.copytree(template, plugin, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        shutil.copyfile(project / "LICENSE", plugin / "LICENSE")
        shutil.copyfile(project / readme, plugin / "README.md")
        launcher = plugin / "skills/inferrsi/scripts/inferrsi.py"
        launcher.parent.mkdir(parents=True, exist_ok=True)
        shared_launcher = project / "plugins/inferrsi/skills/inferrsi/scripts/inferrsi.py"
        if not compact_runtime:
            shutil.copyfile(shared_launcher, launcher)
        runtime = plugin / "runtime"
        hashes = {}
        for path in sorted(source.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(source)
            package_data = relative.parts[0] == "data" and (
                path.suffix in (".md", ".json") or path.name in ("LICENSE", "THIRD_PARTY_NOTICES")
                or (
                    path.suffix == ".txt"
                    and relative.parts[-3:-1] == ("references", "licenses")
                )
                or (path.suffix == ".html" and relative.parent.parts == ("data", "dashboard"))
                or (path.name == "upstream-NOTICE" and relative.parent.name == "references")
            )
            if path.suffix != ".py" and not package_data:
                continue
            if path.is_symlink():
                raise ValueError(f"Package input must not be a symlink: {relative}")
            destination = runtime / "inferrsi" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            data = path.read_bytes()
            destination.write_bytes(data)
            hashes[(Path("inferrsi") / relative).as_posix()] = (
                hashlib.sha256(data).hexdigest()
            )
        identity = "\n".join(f"{name}\0{digest}" for name, digest in sorted(hashes.items()))
        metadata = json.loads((plugin / metadata_file).read_text(encoding="utf-8"))
        if metadata.get("id", metadata.get("name")) != "inferrsi":
            raise ValueError("Plugin identity must match its inferrsi package directory")
        if release_version is not None:
            metadata["version"] = release_version
            _json(plugin / metadata_file, metadata)
        manifest = {
            "schema_version": 1,
            "plugin_version": metadata["version"],
            "runtime_version": runtime_version,
            "content_sha256": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
            "files": hashes,
        }
        if compact_runtime:
            # The host must never copy the deep canonical tree during import/install.
            # Only the bootstrap expands it, using extended paths on Windows.
            payload = runtime / "payload.zip"
            _zip_tree(runtime / "inferrsi", payload, "inferrsi/")
            manifest["payload_sha256"] = hashlib.sha256(payload.read_bytes()).hexdigest()
            manifest["launcher_sha256"] = hashlib.sha256(shared_launcher.read_bytes()).hexdigest()
            shutil.copyfile(shared_launcher, runtime / "launcher.py")
            assert (runtime / "inferrsi").resolve().is_relative_to(Path(staging).resolve())
            shutil.rmtree(runtime / "inferrsi")
        _json(runtime / "manifest.json", manifest)
        # Stable ZIP metadata makes repeated builds of identical bytes comparable.
        _zip_tree(plugin, archive, "inferrsi/")
        shutil.copytree(plugin, _io_path(package))
    return {
        "plugin": str(package),
        "archive": str(archive),
        "runtime_files": len(hashes),
    }
