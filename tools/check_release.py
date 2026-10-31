"""Plan daily versioned releases and validate their packages without publishing."""

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


def release_version(tag: str) -> str:
    number = r"(?:0|[1-9][0-9]*)"
    if not re.fullmatch(rf"v{number}\.{number}\.{number}", tag):
        raise ValueError("Release tags must have the stable form vMAJOR.MINOR.PATCH")
    return tag[1:]


def version_tuple(tag: str) -> tuple[int, ...]:
    return tuple(map(int, release_version(tag).split(".")))


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True, stderr=subprocess.PIPE).strip()


def plan_release(default_branch: str, releases: list[dict], initial_version: str,
                 prerelease: bool = True) -> dict:
    if type(prerelease) is not bool:
        raise ValueError("Release prerelease setting must be a boolean")
    initial = version_tuple(f"v{initial_version}")
    source = git("rev-parse", "--verify", f"refs/remotes/origin/{default_branch}^{{commit}}")
    stable = {}
    for tag in git("tag", "--list").splitlines():
        try:
            stable[tag] = version_tuple(tag)
        except ValueError:
            continue
    published = []
    reserved = []
    for release in releases:
        tag = release["tag_name"]
        try:
            value = version_tuple(tag)
        except ValueError:
            continue
        reserved.append(value)
        if release["draft"] is False:
            published.append((value, tag))
    previous_tag = max(published)[1] if published else ""
    if previous_tag:
        previous = git("rev-parse", "--verify", f"refs/tags/{previous_tag}^{{commit}}")
        subprocess.run(["git", "merge-base", "--is-ancestor", previous, source],
                       check=True, capture_output=True)
        if git("rev-parse", f"{previous}^{{tree}}") == git("rev-parse", f"{source}^{{tree}}"):
            return {"release": "false"}
    used = [*stable.values(), *reserved]
    if used:
        major, minor, patch = max(used)
        version = max(initial, (major, minor, patch + 1))
    else:
        version = initial
    return {"release": "true", "tag": "v" + ".".join(map(str, version)),
            "version": ".".join(map(str, version)),
            "prerelease": str(prerelease).lower(),
            "commit": source, "previous_tag": previous_tag}


def check_versions(tag: str, distribution: str, runtime: str) -> None:
    version = release_version(tag)
    if distribution != version or runtime != version:
        raise ValueError("Tag, installed distribution and runtime versions must agree exactly")


def check_sdist(path: Path) -> None:
    # setuptools-scm's file finder must not expand the release to all tracked files.
    allowed = {"src", "pyproject.toml", "README.md", "LICENSE", "MANIFEST.in",
               "PKG-INFO", "setup.cfg"}
    with tarfile.open(path) as archive:
        for member in archive.getmembers():
            parts = Path(member.name).parts
            if ".." in parts or Path(member.name).is_absolute():
                raise ValueError("Unsafe source-distribution path")
            if len(parts) > 1 and parts[1] not in allowed:
                raise ValueError("Source distribution includes repository-only material")


def check_plugin(path: Path, tag: str) -> None:
    version = release_version(tag)
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Plugin ZIP must contain one standalone inferrsi plugin")
        roots = set()
        destinations = set()
        spellings = {}
        for member in archive.infolist():
            name = PurePosixPath(member.filename)
            canonical = name.as_posix() + ("/" if member.is_dir() else "")
            if (not name.parts or name.is_absolute() or ".." in name.parts
                    or "\\" in member.filename or ":" in member.filename
                    or member.filename != canonical
                    or name.as_posix().casefold() in destinations
                    or any(part.endswith((".", " ")) or re.search(r'[<>"|?*]', part)
                           or re.fullmatch(r"con|prn|aux|nul|com[1-9]|lpt[1-9]",
                                           part.split(".")[0], re.IGNORECASE)
                           for part in name.parts)
                    or stat.S_ISLNK(member.external_attr >> 16)):
                raise ValueError("Unsafe plugin ZIP entry")
            destinations.add(name.as_posix().casefold())
            for depth in range(1, len(name.parts) + 1):
                prefix = "/".join(name.parts[:depth])
                if spellings.setdefault(prefix.casefold(), prefix) != prefix:
                    raise ValueError("Unsafe plugin ZIP directory alias")
            roots.add(name.parts[0])
        if roots != {"inferrsi"}:
            raise ValueError("Plugin ZIP must contain one standalone inferrsi plugin")
        plugin = "inferrsi"
        allowed = {"plugin.json", "skills", "runtime", "LICENSE", "README.md"}
        if any(len(PurePosixPath(name).parts) > 1
               and PurePosixPath(name).parts[1] not in allowed for name in names):
            raise ValueError("Plugin ZIP includes a marketplace or unrelated wrapper")
        metadata = json.loads(archive.read(f"{plugin}/plugin.json"))
        manifest = json.loads(archive.read(f"{plugin}/runtime/manifest.json"))
        if metadata.get("$schema") != "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json":
            raise ValueError("Plugin manifest must use the portable plugin schema")
        archive.getinfo(f"{plugin}/skills/inferrsi/SKILL.md")
        archive.getinfo(f"{plugin}/README.md")
        archive.getinfo(f"{plugin}/LICENSE")
        check_versions(tag, metadata["version"], manifest["runtime_version"])
        if metadata["name"] != "inferrsi" or manifest["plugin_version"] != version:
            raise ValueError("Plugin identity/version does not match the release")
        prefix = f"{plugin}/runtime/"
        actual = {name[len(prefix):] for name in names
                  if name.startswith(prefix) and name != prefix + "manifest.json"
                  and not name.endswith("/")}
        if any(not name.startswith("inferrsi/") for name in actual):
            raise ValueError("Unexpected file outside the bundled runtime package")
        hashes = manifest["files"]
        if not hashes or set(hashes) != actual:
            raise ValueError("Plugin manifest must cover every bundled runtime file")
        for name, digest in hashes.items():
            if hashlib.sha256(archive.read(prefix + name)).hexdigest() != digest:
                raise ValueError("Plugin bundled runtime checksum mismatch")
        identity = "\n".join(f"{name}\0{digest}" for name, digest in sorted(hashes.items()))
        if hashlib.sha256(identity.encode("utf-8")).hexdigest() != manifest["content_sha256"]:
            raise ValueError("Plugin content identity mismatch")
        with tempfile.TemporaryDirectory(prefix="irsi-") as staging:
            destination = Path(staging).resolve()
            if os.name == "nt":
                value = str(destination)
                destination = Path("\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\")
                                   else "\\\\?\\" + value)
            archive.extractall(destination)
            launcher = destination / plugin / "skills/inferrsi/scripts/inferrsi.py"
            command = [sys.executable, "-I", "-S", "-X", "utf8", str(launcher)]

            def invoke(*args):
                try:
                    result = subprocess.run(command + list(args), cwd=staging, check=True,
                                            capture_output=True, text=True, encoding="utf-8",
                                            timeout=45)
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                    raise ValueError("Extracted Codex plugin failed isolated validation") from error
                return json.loads(result.stdout)

            info = invoke("--plugin-info")
            check_versions(tag, info["plugin_version"], info["runtime_version"])
            if info["runtime"] != "bundled" or info["content_sha256"] != manifest["content_sha256"]:
                raise ValueError("Plugin launcher did not select the verified bundled runtime")
            items = invoke("collect", "--limit", "1", "--json")["items"]
            if not items:
                raise ValueError("Plugin has no bundled knowledge")
            item = items[0]
            material = invoke("read", item["ref"], "--revision", item["revision"], "--material")
            if material["revision"] != item["revision"]:
                raise ValueError("Plugin knowledge read lost its revision identity")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan")
    plan.add_argument("--default-branch", required=True)
    plan.add_argument("--releases", type=Path, required=True)
    installed = commands.add_parser("installed")
    installed.add_argument("--tag", required=True)
    sdist = commands.add_parser("sdist")
    sdist.add_argument("path", type=Path)
    plugin = commands.add_parser("plugin")
    plugin.add_argument("path", type=Path)
    plugin.add_argument("--tag", required=True)
    args = parser.parse_args()
    try:
        if args.command == "plan":
            # The workflow uses Python 3.11; importing these helpers remains 3.10-safe.
            import tomllib

            config = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
            pages = json.loads(args.releases.read_text(encoding="utf-8"))
            releases = [release for page in pages for release in page]
            settings = config["tool"]["inferrsi"]["release"]
            result = plan_release(args.default_branch, releases,
                                  settings["initial_version"], settings["prerelease"])
            for key, value in result.items():
                print(f"{key}={value}")
        elif args.command == "sdist":
            check_sdist(args.path)
        elif args.command == "plugin":
            check_plugin(args.path, args.tag)
        else:
            from importlib.metadata import version

            from inferrsi import __version__

            check_versions(args.tag, version("inferrsi"), __version__)
            print("Installed release versions agree")
    except (ValueError, KeyError, OSError, zipfile.BadZipFile,
            subprocess.CalledProcessError) as error:
        parser.exit(1, f"Release validation failed: {error}\n")


if __name__ == "__main__":
    main()
