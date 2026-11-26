"""Compare two ways to reproduce a synthetic, pinned Git skill on loopback.

    python tools/reproduce_external_skill.py demo <new-evidence-directory>
    python tools/reproduce_external_skill.py verify <snapshot> <manifest.json> <closure-sha256>

The second command needs only the retained files, manifest and independently recorded digest.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

FILES = {
    "LICENSE": b"Controlled fixture. Copying is permitted for this local experiment.\n",
    "SKILL.md": b"# Controlled fixture\nSee references/guide.md.\n",
    "references/guide.md": b"Local procedure v1.\n",
}
MODULE = "vendor/fixture"


def closure(manifest):
    canonical = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def manifest_for(directory, *, checkout=False):
    def fail_on_unreadable(error):
        raise error

    manifest = {}
    for root, dirs, files in os.walk(directory, onerror=fail_on_unreadable):
        here = Path(root)
        if checkout and here == directory:
            dirs[:] = [name for name in dirs if name != ".git"]
            files = [name for name in files if name != ".git"]
        for name in [*dirs, *files]:
            if (here / name).is_symlink():
                raise ValueError(f"Expected regular fixture content: {name}")
        for name in files:
            path = here / name
            manifest[path.relative_to(directory).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return dict(sorted(manifest.items()))


def verify(directory, manifest, digest, *, checkout=False):
    if closure(manifest) != digest:
        raise ValueError("Manifest does not match the recorded closure SHA-256")
    actual = manifest_for(directory, checkout=checkout)
    return {
        "matches": actual == manifest,
        "closure_sha256": closure(actual),
        "missing": sorted(manifest.keys() - actual.keys()),
        "unexpected": sorted(actual.keys() - manifest.keys()),
        "changed": sorted(k for k in manifest.keys() & actual.keys() if manifest[k] != actual[k]),
    }


def git(where, *args, check=True):
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    env.update(
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_ATTR_NOSYSTEM="1",
        GIT_TERMINAL_PROMPT="0",
        GIT_ALLOW_PROTOCOL="file:http",
        NO_PROXY="127.0.0.1",
        no_proxy="127.0.0.1",
        GIT_AUTHOR_DATE="2001-01-01T00:00:00Z",
        GIT_COMMITTER_DATE="2001-01-01T00:00:00Z",
    )
    return subprocess.run(
        [
            "git",
            "-c",
            "user.name=Local fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "core.autocrlf=false",
            "-c",
            f"core.attributesFile={os.devnull}",
            "-C",
            str(where),
            *args,
        ],
        env=env,
        capture_output=True,
        text=True,
        check=check,
        timeout=45,
    )


def checked_equal(observed, expected, description):
    if observed != expected:
        raise ValueError(f"{description}: expected {expected!r}, observed {observed!r}")


def fetch_step(work, directory, args, *, check=True):
    result = git(directory, *args, check=check)
    return {
        "cwd": directory.relative_to(work).as_posix(),
        "argv": ["git", *args],
        "exit_code": result.returncode,
    }


@contextmanager
def serve_repo(directory):
    unavailable = threading.Event()
    refusals = []

    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self):
            if unavailable.is_set():
                refusals.append(self.path)
                self.send_error(503)
            else:
                super().do_GET()

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(Handler, directory=str(directory))
    ) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}/fixture.git", unavailable, refusals
        finally:
            server.shutdown()
            worker.join()


def prepare_source(work):
    source = work / "source"
    git(work, "init", "-q", "-b", "main", str(source))
    for name, data in FILES.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    git(source, "add", ".")
    git(source, "commit", "-qm", "controlled v1")
    pin = git(source, "rev-parse", "HEAD").stdout.strip()
    git(source, "tag", "scene", pin)
    (source / "references/guide.md").write_bytes(b"Local procedure v2.\n")
    git(source, "commit", "-qam", "controlled v2")
    git(source, "tag", "-f", "scene", "HEAD")
    web = work / "http"
    web.mkdir()
    git(work, "clone", "-q", "--no-local", "--bare", str(source), str(web / "fixture.git"))
    git(web / "fixture.git", "update-server-info")
    return web, pin, git(source, "rev-parse", "HEAD").stdout.strip()


def fetched(checkout, url, pin, manifest):
    origin = git(checkout, "remote", "get-url", "origin").stdout.strip()
    observed = git(checkout, "rev-parse", "HEAD").stdout.strip()
    actual = manifest_for(checkout, checkout=True)
    checked_equal((origin, observed, actual), (url, pin, manifest), "Fresh checkout")
    return {"resolved_url": origin, "checkout_commit": observed, "manifest": actual}


def demonstrate(output):
    if output.exists():
        raise FileExistsError(f"Choose a new evidence directory: {output}")
    manifest = {p: hashlib.sha256(b).hexdigest() for p, b in FILES.items()}
    digest = closure(manifest)
    with tempfile.TemporaryDirectory(prefix="skill-reproduction-") as temp:
        work = Path(temp)
        web, pin, moved = prepare_source(work)
        proof = work / "evidence"
        snapshot = proof / "snapshot"
        parent, direct, cold_parent = (work / p for p in ("parent", "direct", "cold-parent"))
        with serve_repo(web) as (url, unavailable, refusals):
            git(work, "init", "-q", "-b", "main", str(parent))
            git(parent, "config", "-f", ".gitmodules", "submodule.fixture.path", MODULE)
            git(parent, "config", "-f", ".gitmodules", "submodule.fixture.url", url)
            git(parent, "add", ".gitmodules")
            git(parent, "update-index", "--add", "--cacheinfo", f"160000,{pin},{MODULE}")
            git(parent, "commit", "-qm", "pin controlled v1")
            git(work, "clone", "-q", "--no-local", str(parent), str(cold_parent))
            gitlink = git(cold_parent, "ls-tree", "HEAD", MODULE).stdout.split()
            checked_equal(gitlink, ["160000", "commit", pin, MODULE], "Cold parent gitlink")

            clone = fetch_step(work, work, ["clone", "-q", url, direct.name])
            observed_tag = git(direct, "rev-parse", "scene^{commit}").stdout.strip()
            checked_equal(observed_tag, moved, "Moved tag")
            if observed_tag == pin:
                raise ValueError("Fixture tag still points at the registered version")
            checkout = fetch_step(work, direct, ["checkout", "-q", "--detach", pin])
            link = fetched(direct, url, pin, manifest)
            link["commands"] = [clone, checkout]
            update_args = ["submodule", "update", "--init", "--", MODULE]
            update = fetch_step(work, parent, update_args)
            module = fetched(parent / MODULE, url, pin, manifest)
            module["commands"] = [update]
            for name in manifest:
                destination = snapshot / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(direct / name, destination)
            unavailable.set()
            cold = {}
            for route, cwd, args, target in (
                ("link", work, ["clone", "-q", url, "cold-link"], work / "cold-link"),
                (
                    "submodule",
                    cold_parent,
                    update_args,
                    cold_parent / MODULE,
                ),
            ):
                before = len(refusals)
                step = fetch_step(work, cwd, args, check=False)
                delivered = manifest_for(target, checkout=True) if target.exists() else {}
                if not step["exit_code"] or len(refusals) == before or delivered:
                    raise ValueError(f"Expected fresh {route} to fail at the unavailable source")
                cold[route] = {
                    **step,
                    "source_status": 503,
                    "files": delivered,
                }

        offline = {
            "snapshot": verify(snapshot, manifest, digest),
            "populated_submodule": verify(parent / MODULE, manifest, digest, checkout=True),
        }
        for result in offline.values():
            checked_equal(result["matches"], True, "Offline bytes")
        report = {
            "repository": url,
            "registered_commit": pin,
            "moved_tag_commit": observed_tag,
            "manifest_sha256": digest,
            "manifest_encoding": "UTF-8 JSON, sorted path keys, compact separators, no trailing LF",
            "fresh": {"link": link, "submodule": {**module, "gitlink": gitlink[2]}},
            "offline": offline,
            "source_unavailable_cold": cold,
        }
        for filename, payload in [("manifest.json", manifest), ("report.json", report)]:
            (proof / filename).write_bytes((json.dumps(payload, indent=2) + "\n").encode("utf-8"))
        shutil.copytree(proof, output)
    return report


def main():
    cli = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = cli.add_subparsers(dest="command", required=True)
    commands.add_parser("demo").add_argument("output", type=Path)
    verifier = commands.add_parser("verify")
    verifier.add_argument("snapshot", type=Path)
    verifier.add_argument("manifest", type=Path)
    verifier.add_argument("digest")
    args = cli.parse_args()
    try:
        if args.command == "demo":
            result = demonstrate(args.output)
        else:
            manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
            result = verify(args.snapshot, manifest, args.digest)
    except (ValueError, OSError) as error:
        cli.exit(1, f"{error}\n")
    print(json.dumps(result, indent=2))
    return 0 if result.get("matches", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
