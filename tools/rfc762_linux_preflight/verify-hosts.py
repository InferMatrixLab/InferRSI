import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def tree(directory):
    return {
        p.relative_to(directory).as_posix(): digest(p.read_bytes()) if p.is_file() else None
        for p in directory.rglob("*")
    }


def run(command, cwd, cache, *args, expected=0):
    result = subprocess.run(
        command + list(map(str, args)), cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", timeout=90,
        env=dict(os.environ, LOCALAPPDATA=str(cache), XDG_CACHE_HOME=str(cache)),
    )
    assert result.returncode == expected, (result.args, result.stdout, result.stderr)
    return result


def main(root):
    wheel, = (root / "wheel").glob("*.whl")
    out = {"version": "0.4.762", "source": "f57fd106ad7fe7f5bd29579e89d9d067f79f0845", "artifacts": {}}
    with zipfile.ZipFile(wheel) as archive:
        wheel_files = {
            name: archive.read(name) for name in archive.namelist()
            if name.startswith("inferrsi/") and not name.endswith("/")
        }
    prefix = [sys.executable, "-I", "-S", "-B", "-X", "utf8"]
    commands = {
        "wheel": prefix + ["-c", "import runpy, sys; sys.path.insert(0, sys.argv.pop(1)); "
                           "runpy.run_module('inferrsi', run_name='__main__')", str(root / "install")],
    }
    out["artifacts"]["wheel"] = {"sha256": digest(wheel.read_bytes()), "files": len(wheel_files)}
    for host in ("codex", "workswarm"):
        plugin_zip = root / f"{host}.zip"
        installed = root / f"installed-{host}"
        destination = str(installed)
        if os.name == "nt":
            destination = "\\\\?\\" + destination
        with zipfile.ZipFile(plugin_zip) as archive:
            archive.extractall(destination)
            manifest = json.loads(archive.read("inferrsi/runtime/manifest.json"))
            assert manifest["runtime_version"] == manifest["plugin_version"] == out["version"]
            if host == "codex":
                host_files = {name: archive.read(f"inferrsi/runtime/{name}") for name in manifest["files"]}
            else:
                with zipfile.ZipFile(io.BytesIO(archive.read("inferrsi/runtime/payload.zip"))) as payload:
                    host_files = {name: payload.read(name) for name in manifest["files"]}
        assert all(digest(data) == manifest["files"][name] for name, data in host_files.items())
        assert all((root / "install" / name).read_bytes() == data for name, data in wheel_files.items())
        common = host_files.keys() & wheel_files.keys()
        different = sorted(name for name in common if host_files[name] != wheel_files[name])
        assert not different, different
        assert {"inferrsi/_version.py", "inferrsi/apps/cli/__init__.py",
                "inferrsi/apps/cli/arguments.py", "inferrsi/harness/records/optimization_log.py"} <= common
        commands[host] = prefix + [str(installed / "inferrsi/skills/inferrsi/scripts/inferrsi.py")]
        out["artifacts"][host] = {
            "sha256": digest(plugin_zip.read_bytes()),
            "content_sha256": manifest["content_sha256"],
            "runtime_files": len(host_files), "wheel_common_identical": len(common),
            "wheel_only": len(wheel_files.keys() - common), "host_only": len(host_files.keys() - common),
        }
    for host, command in commands.items():
        work = root / f"verify-{host}"
        work.mkdir()
        cache = root / f"cache-{host}"
        evidence = work / "manual"
        source = work / "input.json"
        if host != "wheel":
            info = json.loads(run(command, work, cache, "--plugin-info").stdout)
            assert info["runtime"] == "bundled" and info["runtime_version"] == out["version"]
            assert info["content_sha256"] == out["artifacts"][host]["content_sha256"]
        init_args = ["init", "--directory", evidence, "--id", "rfc762-release-preflight"]
        rejected = run(command, work, cache, "campaign", *init_args, expected=2)
        assert "campaign init has retired. Use inferrsi evidence init" in rejected.stderr
        assert not evidence.exists()
        run(command, work, cache, "evidence", *init_args)
        source.write_bytes((json.dumps({
            "schema_version": 2, "reviewed_by_caller": True, "campaign_id": "rfc762-release-preflight",
            "goal": {"statement": "Verify migrated evidence action", "metric": "Retained bytes"},
            "knowledge": [], "iterations": [],
            "search_space": {"state": "partial", "missing_reason": "Offline fixture", "dimensions": []},
            "summary": {"state": "partial", "missing_reason": "Offline fixture",
                        "successes": [], "failures": [], "lessons": [], "limitations": []},
        }, ensure_ascii=False) + "\r\n").encode("utf-8"))
        log_args = ["log", "--directory", evidence, "--file", source]
        recorded = json.loads(run(command, work, cache, "evidence", *log_args).stdout)
        raw = source.read_bytes()
        assert recorded == {"log": "optimization-log-v1.json", "sha256": digest(raw)}
        assert (evidence / recorded["log"]).read_bytes() == raw
        index, = (evidence / "optimization-log.jsonl").read_text(encoding="utf-8").splitlines()
        assert json.loads(index)["sha256"] == digest(raw)
        before = tree(work)
        rejected_log = run(command, work, cache, "campaign", *log_args, expected=2)
        assert "campaign log has retired. Use inferrsi evidence log" in rejected_log.stderr
        assert tree(work) == before
        out["artifacts"][host]["evidence"] = {
            "receipt": recorded, "legacy_init": rejected.returncode,
            "legacy_log": rejected_log.returncode, "files_unchanged": len(before),
        }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
