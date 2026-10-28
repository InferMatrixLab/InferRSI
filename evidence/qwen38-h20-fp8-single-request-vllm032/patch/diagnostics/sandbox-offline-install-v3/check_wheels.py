"""Read-only controls over the retained complete wheelhouse; no installation."""
import copy
import hashlib
import importlib.util
import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

from packaging.tags import parse_tag

spec = importlib.util.spec_from_file_location("verify", Path(__file__).with_name("verify_wheels.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
root = Path(sys.argv[1])
bundle = root / "sandbox-offline-prefetch-v1/fetched"
build = root / "sandbox-resolve-1991/build.lock"
runtime = root / "sandbox-resolve-1991/dependencies.lock"
raw = (bundle / "manifest.json").read_bytes()
digest = hashlib.sha256(raw).hexdigest()
manifest = json.loads(raw)
tags = [next(iter(parse_tag(tag))) for tag in json.loads(
    (root / "sandbox-platform-fs-v1/observations.json").read_bytes())["platform"]["supported_tags"]]
checks = []


def run():
    return m.verify(bundle, build, runtime, digest)


def rejects(function, name):
    try:
        function()
    except ValueError:
        checks.append(name)
    else:
        raise RuntimeError(name)


with patch.object(m, "sys_tags", return_value=tags), patch.object(m.platform, "python_version", return_value="3.12.13"):
    result = run()
    if result["package_count"] != 96 or result["total_wheel_bytes"] != 172422937:
        raise RuntimeError("Complete wheelhouse")
    checks.append("complete-wheelhouse-with-recorded-target-tags")
    for field, value in (("completed", False), ("installed", True), ("executed_downloads", True),
                         ("errors", [{"name": "synthetic"}]), ("files", manifest["files"][:-1])):
        modified = copy.deepcopy(manifest)
        modified[field] = value
        with patch.object(m.helper, "strict_json", return_value=modified):
            rejects(run, "manifest-" + field)
    for field, value in (("version", "0.0.0"), ("sha256", "0" * 64), ("size", True),
                         ("requires_python", ">=99")):
        modified = copy.deepcopy(manifest)
        modified["files"][0][field] = value
        with patch.object(m.helper, "strict_json", return_value=modified):
            rejects(run, "wheel-" + field)
    actual_open = Path.open

    def bad_open(path, *args, **kwargs):
        if path.name == manifest["files"][0]["filename"]:
            return io.BytesIO(b"synthetic-corruption")
        return actual_open(path, *args, **kwargs)

    with patch.object(Path, "open", bad_open):
        rejects(run, "corrupted-wheel-bytes")
    with patch.object(m, "sys_tags", return_value=[]):
        rejects(run, "no-compatible-target-tags")
    rejects(lambda: m.verify(bundle, build, runtime, "0" * 64), "manifest-digest")
print(json.dumps({"checks_passed": len(checks), "checks": checks,
                  "actual_linux_execution": False, "installed": False}, indent=2))
