"""Build a local Codex marketplace and archive from the canonical runtime bytes."""

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
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise ValueError("Runtime __version__ is missing")


def build_plugin(
    output: Path, *, project: Path = PROJECT, marketplace_name: str = "inferrsi-local",
) -> dict:
    """Create a fresh distribution; never replace user configuration or earlier builds."""
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", marketplace_name):
        raise ValueError("Marketplace name must contain lowercase words separated by hyphens")
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
    _io_path(output.parent).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="irsi-", dir=_io_path(output.parent)) as staging:
        stage = Path(staging) / output.name
        plugin = stage / "plugins" / "inferrsi"
        shutil.copytree(template, plugin, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        shutil.copyfile(project / "LICENSE", plugin / "LICENSE")
        shutil.copyfile(project / "LICENSE", stage / "LICENSE")
        shutil.copyfile(project / "docs" / "codex-plugin.md", stage / "README.md")
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
        _json(runtime / "manifest.json", {
            "schema_version": 1,
            "plugin_version": metadata["version"],
            "runtime_version": _version(source / "__init__.py"),
            "content_sha256": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
            "files": hashes,
        })
        _json(stage / ".agents" / "plugins" / "marketplace.json", {
            "name": marketplace_name,
            "interface": {"displayName": "InferRSI preview"},
            "plugins": [{
                "name": "inferrsi",
                "source": {"source": "local", "path": "./plugins/inferrsi"},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                "category": "Productivity",
            }],
        })
        # Stable ZIP metadata makes repeated builds of identical bytes comparable.
        with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(stage.rglob("*")):
                if path.is_file():
                    info = zipfile.ZipInfo(
                        (Path(output.name) / path.relative_to(stage)).as_posix(),
                        date_time=(1980, 1, 1, 0, 0, 0),
                    )
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o100644 << 16
                    bundle.writestr(info, path.read_bytes())
        shutil.copytree(stage, _io_path(output))
    return {
        "marketplace_name": marketplace_name,
        "marketplace": str(output),
        "plugin": str(output / "plugins" / "inferrsi"),
        "archive": str(archive),
        "runtime_files": len(hashes),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=PROJECT / "dist" / "codex-plugin")
    parser.add_argument("--marketplace-name", default="inferrsi-local")
    args = parser.parse_args()
    try:
        result = build_plugin(args.output, marketplace_name=args.marketplace_name)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
