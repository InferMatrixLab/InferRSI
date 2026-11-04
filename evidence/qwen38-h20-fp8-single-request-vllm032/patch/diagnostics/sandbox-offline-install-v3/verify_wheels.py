"""Verify all offline wheels against unchanged locks and the actual interpreter."""

import argparse
import hashlib
import importlib.util
import json
import platform
from pathlib import Path

from packaging.specifiers import SpecifierSet
from packaging.tags import sys_tags
from packaging.utils import parse_wheel_filename
from packaging.version import Version

spec = importlib.util.spec_from_file_location("prefetch", Path(__file__).with_name("prefetch.py"))
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def verify(bundle, build, runtime, expected_sha):
    raw = (bundle / "manifest.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError("Manifest digest mismatch")
    manifest = helper.strict_json(raw)
    if (manifest["completed"] is not True or manifest["errors"]
            or manifest["installed"] is not False or manifest["executed_downloads"] is not False):
        raise ValueError("Unexpected prefetch state")
    locks = [helper.parse_lock(path.read_bytes()) for path in (build, runtime)]
    expected = helper.merged_locks(locks)
    if [len(lock) for lock in locks] != [5, 92] or len(expected) != 96:
        raise ValueError("Unexpected locked package set")
    entries = manifest["files"]
    if len(entries) != 96 or {entry["name"] for entry in entries} != set(expected):
        raise ValueError("Manifest closure differs")
    wheelhouse = bundle / "wheelhouse"
    names = {entry["filename"] for entry in entries}
    if len(names) != 96 or {p.name for p in wheelhouse.iterdir()} != names:
        raise ValueError("Wheelhouse inventory differs")
    tags = list(sys_tags())
    accepted = set(tags)
    for entry in entries:
        filename = entry["filename"]
        if Path(filename).name != filename or "\\" in filename:
            raise ValueError("Unsafe filename")
        path = wheelhouse / filename
        if path.is_symlink() or not path.is_file():
            raise ValueError("Wheel is not a regular file")
        name, version, _, wheel_tags = parse_wheel_filename(filename)
        wanted_version, hashes = expected[entry["name"]]
        if (name != entry["name"] or version != Version(wanted_version)
                or entry["version"] != wanted_version or not accepted & wheel_tags
                or entry["sha256"] not in hashes or type(entry["size"]) is not int):
            raise ValueError("Wheel package/tag/hash identity differs")
        requires = entry.get("requires_python")
        if requires and not SpecifierSet(requires).contains(platform.python_version(), prereleases=True):
            raise ValueError("Requires-Python mismatch")
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
        if size != entry["size"] or digest.hexdigest() != entry["sha256"]:
            raise ValueError("Wheel bytes differ")
    return {"completed": True, "package_count": len(entries),
            "manifest_sha256": expected_sha, "python": platform.python_version(),
            "supported_tags_sha256": hashlib.sha256("\n".join(map(str, tags)).encode()).hexdigest(),
            "total_wheel_bytes": sum(entry["size"] for entry in entries)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = verify(args.bundle, args.build, args.runtime, args.sha256)
    with args.output.open("x") as stream:
        json.dump(report, stream, sort_keys=True)
        stream.write("\n")


if __name__ == "__main__":
    main()
