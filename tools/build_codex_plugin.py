"""Build a standalone Codex plugin archive from the canonical runtime bytes."""

from __future__ import annotations

import argparse
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


def build_plugin(
    output: Path, *, project: Path = PROJECT, release_version: str | None = None,
) -> dict:
    """Create a fresh distribution; never replace user configuration or earlier builds."""
    output = output.resolve()
    archive = output.with_name(output.name + ".zip")
    if output.exists() or archive.exists():
        raise ValueError("Output or archive already exists; select a fresh --output directory")
    project = project.resolve()
    for protected in ("src", "plugins", "docs", "tests", "tools"):
        if output.is_relative_to(project / protected) or output == project:
            raise ValueError("Output must be outside the source directories")

    source = _io_path(project / "src" / "inferrsi")
    template = _io_path(project / "plugins" / "inferrsi")
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
        shutil.copyfile(project / "docs" / "codex-plugin.md", plugin / "README.md")
        runtime = plugin / "runtime"
        hashes = {}
        for path in sorted(source.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(source)
            package_data = relative.parts[0] == "data" and (
                path.suffix in (".md", ".json") or path.name in ("LICENSE", "THIRD_PARTY_NOTICES")
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
        metadata = json.loads((plugin / "plugin.json").read_text(encoding="utf-8"))
        if release_version is not None:
            metadata["version"] = release_version
            _json(plugin / "plugin.json", metadata)
        _json(runtime / "manifest.json", {
            "schema_version": 1,
            "plugin_version": metadata["version"],
            "runtime_version": runtime_version,
            "content_sha256": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
            "files": hashes,
        })
        # Stable ZIP metadata makes repeated builds of identical bytes comparable.
        with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(plugin.rglob("*")):
                if path.is_file():
                    info = zipfile.ZipInfo(
                        (Path("inferrsi") / path.relative_to(plugin)).as_posix(),
                        date_time=(1980, 1, 1, 0, 0, 0),
                    )
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o100644 << 16
                    bundle.writestr(info, path.read_bytes())
        shutil.copytree(plugin, _io_path(output))
    return {
        "plugin": str(output),
        "archive": str(archive),
        "runtime_files": len(hashes),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=PROJECT / "dist" / "codex-plugin")
    parser.add_argument("--release-version",
                        help="Require the built runtime version and stamp the ZIP")
    args = parser.parse_args()
    try:
        result = build_plugin(args.output, release_version=args.release_version)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
