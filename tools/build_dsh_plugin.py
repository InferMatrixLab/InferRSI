"""Build a standalone DeepSeek Harness bundle for manual installation."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import tarfile
import tempfile
import textwrap
import zipfile
from pathlib import Path

from tools.plugin_bundle import PROJECT, _io_path, _version, bundle_runtime


def client_bundle() -> str:
    """Wrap the dependency-free browser sources in DSH's shared React loader."""
    template = PROJECT / "plugins" / "inferrsi-dsh"
    form = textwrap.indent((template / "form.cjs").read_text(encoding="utf-8"), "      ")
    client = textwrap.indent((template / "client.cjs").read_text(encoding="utf-8"), "      ")
    return (
        "window.__ModuleLoader__.load({\n"
        "  id: 'inferrsi-dsh',\n"
        "  factory: (hostRequire) => {\n"
        "    const form = (() => {\n"
        "      const module = { exports: {} };\n"
        f"{form}\n"
        "      return module.exports;\n"
        "    })();\n"
        "    return (() => {\n"
        "      const require = name => name === './form.cjs' ? form : hostRequire(name);\n"
        "      const module = { exports: {} };\n"
        f"{client}\n"
        "      return module.exports;\n"
        "    })();\n"
        "  }\n"
        "});\n"
    )


def build_bundle(output: Path) -> dict:
    """Package the DSH adapter and the same skill and runtime used by Codex."""
    output = output.resolve()
    if output.suffix != ".tgz":
        raise ValueError("Output must have a .tgz extension")
    if output.exists():
        raise ValueError("Output already exists; select a fresh .tgz path")
    for protected in ("src", "plugins", "docs", "tests", "tools"):
        if output.is_relative_to(PROJECT / protected):
            raise ValueError("Output must be outside the source directories")

    source = _io_path(PROJECT / "src" / "inferrsi")
    generated = source / "_version.py"
    runtime_version = _version(generated if generated.is_file() else source / "__init__.py")

    temp_root = _io_path(Path(tempfile.gettempdir()))
    with tempfile.TemporaryDirectory(prefix="irsi-dsh-", dir=temp_root) as temp:
        staging = Path(temp)
        package = staging / "package"
        package.mkdir()
        for name in (
            "package.json", "cordis.patch.yml", "index.js", "remote.cjs", "remote-host.cjs",
        ):
            shutil.copyfile(PROJECT / "plugins" / "inferrsi-dsh" / name, package / name)
        (package / "client.js").write_text(client_bundle(), encoding="utf-8")
        vendor = package / "vendor"
        vendor.mkdir()
        for name in ("ssh2.cjs", "THIRD_PARTY_NOTICES.md", "README.md"):
            shutil.copyfile(PROJECT / "plugins" / "inferrsi-dsh" / "vendor" / name,
                            vendor / name)
        skill = Path("skills/inferrsi")
        asset = package / "assets" / "inferrsi"
        (asset / "scripts").mkdir(parents=True)
        for relative in ("SKILL.md", "scripts/inferrsi.py"):
            shutil.copyfile(PROJECT / "plugins" / "inferrsi" / skill / relative, asset / relative)
        (asset / "docs").mkdir()
        shutil.copyfile(PROJECT / "docs" / "dashboard.md", asset / "docs" / "dashboard.md")
        shutil.copyfile(PROJECT / "LICENSE", package / "LICENSE")
        shutil.copyfile(PROJECT / "docs" / "dsh-plugin.md", package / "README.md")
        manifest = json.loads((package / "package.json").read_text(encoding="utf-8"))
        count = bundle_runtime(
            source, package / "runtime", plugin_version=manifest["version"],
            runtime_version=runtime_version,
        )
        with zipfile.ZipFile(package / "remote-runtime.zip", "x",
                             compression=zipfile.ZIP_DEFLATED) as remote_runtime:
            for path in sorted((package / "runtime").rglob("*")):
                if path.is_file():
                    info = zipfile.ZipInfo(path.relative_to(package / "runtime").as_posix(),
                                           date_time=(1980, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o100644 << 16
                    remote_runtime.writestr(info, path.read_bytes())
        archive = staging / "bundle.tgz"
        with (
            archive.open("wb") as raw,
            gzip.GzipFile(fileobj=raw, filename="", mode="wb", mtime=0) as zipped,
            tarfile.open(fileobj=zipped, mode="w") as bundle,
        ):
            for path in sorted(package.rglob("*")):
                if not path.is_file():
                    continue
                name = (Path("package") / path.relative_to(package)).as_posix()
                entry = tarfile.TarInfo(name)
                entry.size = path.stat().st_size
                with path.open("rb") as data:
                    bundle.addfile(entry, data)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        _io_path(output.parent).mkdir(parents=True, exist_ok=True)
        destination = _io_path(output)
        with archive.open("rb") as data:
            writer = destination.open("xb")
            try:
                with writer:
                    shutil.copyfileobj(data, writer)
            except BaseException:
                destination.unlink(missing_ok=True)
                raise
    return {"archive": str(output), "sha256": digest, "runtime_files": count}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=PROJECT / "dist" / "inferrsi-dsh.tgz")
    args = parser.parse_args()
    try:
        result = build_bundle(args.output)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
