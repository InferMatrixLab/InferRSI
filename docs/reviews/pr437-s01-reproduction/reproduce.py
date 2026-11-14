#!/usr/bin/env python3
"""Portable reproduction driver for InferRSI PR 437 (S01).

Run from a clone that can resolve the pinned SHAs. Paths are relative to
--scratch or the current working directory. This script does not depend on
any private C:\\ or /workspace host path.

Examples (from the repository root, after: git fetch origin
a590ccb25596396a592f237105166ade4aedeaaa
8b4a0cfbde8a1f726c2ec1dcc4886cbb5f773db3
03a6a62fab702bee2f730667aa3c6d497079cae4
1052925ff22f9a850cebc64afd0083b35ed1fae9
ca684ed407e19aec60c271f0032790ab0973bff1):

  python3 docs/reviews/pr437-s01-reproduction/reproduce.py preflight-diag
  python3 docs/reviews/pr437-s01-reproduction/reproduce.py trial-bytes --scratch /tmp/s01-repro
  python3 docs/reviews/pr437-s01-reproduction/reproduce.py qualify --revision 8b4a0cfbde8a1f726c2ec1dcc4886cbb5f773db3 --scratch /tmp/s01-repro
  python3 docs/reviews/pr437-s01-reproduction/reproduce.py replay-a --scratch /tmp/s01-repro
  python3 docs/reviews/pr437-s01-reproduction/reproduce.py replay-b --revision 8b4a0cfbde8a1f726c2ec1dcc4886cbb5f773db3 --scratch /tmp/s01-repro
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_BEFORE = "a590ccb25596396a592f237105166ade4aedeaaa"
DEFAULT_AFTER = "8b4a0cfbde8a1f726c2ec1dcc4886cbb5f773db3"
TREE_IDENTICAL_HEAD = "03a6a62fab702bee2f730667aa3c6d497079cae4"
HISTORICAL = "1052925ff22f9a850cebc64afd0083b35ed1fae9"
EVIDENCE = "ca684ed407e19aec60c271f0032790ab0973bff1"
OFFICIAL_BUNDLE_SHA256 = "a401b170080e87ce5af14d1f3a49a5495d76d4db8da1353882841c5733b26547"
EXPECTED_FILE_DIGEST = "7457bb7d4b998be31f64d4e9cb25e4e21e0b8bcf21ab8bdd1669496f9f616f61"
EXPECTED_RESULT_DIGEST = "9302f92978c0d97f56e6ebfff463a7aa0ef062c7788b88e75a6d4277c042f782"
EXPECTED_TRIALS = 58
EXPECTED_FILES = 448
BUNDLE_URL = (
    "https://raw.githubusercontent.com/InferMatrixLab/InferRSI/"
    f"{EVIDENCE}/artifacts/skill-eval-cloud/bundle.json"
)
RUNNER_IMAGE = "debian-13.7/local-box-bwrap-0.12.0"

BEFORE_MODULES = {
    "trial-entry": "inferrsi.harness.skill_evaluation",
    "executor": "inferrsi.harness.skill_evaluation",
    "engineering-task": "inferrsi.harness.skill_eval_engineering",
    "engineering-verify": "inferrsi.harness.skill_eval_engineering",
    "sandbox": "inferrsi.harness.skill_eval_engineering",
    "diagnostic": "inferrsi.harness.skill_eval_diagnostic",
    "improvement": "inferrsi.harness.improvement",
}
AFTER_MODULES = {
    "trial-entry": "inferrsi.apps.skill_evaluation",
    "executor": "inferrsi.harness.skill_evaluation",
    "engineering-task": "inferrsi.benchmark.skill_eval_engineering",
    "engineering-verify": "inferrsi.apps.skill_eval_engineering",
    "sandbox": "inferrsi.harness.artifact_sandbox",
    "diagnostic": "inferrsi.benchmark.skill_eval_diagnostic",
    "improvement": "inferrsi.apps.improvement",
}


def repo_from(args) -> Path:
    if args.repo:
        return Path(args.repo).resolve()
    # docs/reviews/pr437-s01-reproduction -> repository root
    guessed = HERE.parents[2]
    if (guessed / ".git").exists() or (guessed / "tools" / "skill_eval_qualify.py").exists():
        return guessed
    return Path.cwd().resolve()


def run(cmd, *, cwd=None, env=None, check=True):
    print("+", " ".join(str(part) for part in cmd), flush=True)
    completed = subprocess.run(cmd, cwd=cwd, env=env)
    if check and completed.returncode != 0:
        raise SystemExit(completed.returncode)
    return completed.returncode


def git_archive(repo: Path, sha: str, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    proc = subprocess.run(
        ["git", "archive", sha], cwd=repo, stdout=subprocess.PIPE, check=True
    )
    subprocess.run(["tar", "-x", "-C", str(dest)], input=proc.stdout, check=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_digest(files: dict) -> str:
    lines = "".join(f"{digest}  {name}\n" for name, digest in sorted(files.items()))
    return hashlib.sha256(lines.encode()).hexdigest()


def preflight_diag(_args) -> int:
    print("platform:", sys.platform)
    print("python:", sys.version.replace("\n", " "))
    print("executable:", sys.executable)
    system_py = Path("/usr/bin/python3")
    print("system_/usr/bin/python3:", system_py, "exists=" + str(system_py.exists()),
          "resolved=" + (str(system_py.resolve()) if system_py.exists() else "n/a"))
    bwrap = shutil.which("bwrap")
    print("bwrap:", bwrap)
    if bwrap:
        subprocess.run([bwrap, "--version"])
    userns = Path("/proc/sys/kernel/unprivileged_userns_clone")
    if userns.exists():
        print("unprivileged_userns_clone:", userns.read_text().strip())
    else:
        print("unprivileged_userns_clone: (file not present)")
    max_ns = Path("/proc/sys/user/max_user_namespaces")
    if max_ns.exists():
        print("max_user_namespaces:", max_ns.read_text().strip())
    if bwrap:
        probe = subprocess.run(
            [bwrap, "--unshare-all", "--die-with-parent", "--dev", "/dev",
             "--proc", "/proc", "--tmpfs", "/tmp", "--unshare-user",
             "/bin/true"],
            capture_output=True, text=True,
        )
        # Some hosts do not need/accept a second --unshare-user; try the qualify shape next.
        print("bwrap --unshare-all /bin/true exit:", probe.returncode)
        if probe.returncode != 0:
            err = (probe.stderr or probe.stdout or "").strip()
            if err:
                print(err[:1000])
        simple = subprocess.run([bwrap, "--unshare-all", "--", "/bin/true"],
                                capture_output=True, text=True)
        print("bwrap --unshare-all -- /bin/true exit:", simple.returncode)
        if simple.returncode != 0:
            err = (simple.stderr or simple.stdout or "").strip()
            if err:
                print(err[:1000])
    print("This host is a local Linux qualify host only if the bwrap unshare probe")
    print("succeeds and /usr/bin/python3 is a system CPython 3.x. It is not the")
    print("GitHub ubuntu-22.04 official workflow runner.")
    return 0


def capture_one(repo_tree: Path, work: Path, output: Path, modules: dict) -> None:
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_tree / "src")
    env["PYTHONUTF8"] = "1"
    cmd = [
        sys.executable, str(HERE / "trial_bytes.py"), "run",
        "--repo", str(repo_tree),
        "--work", str(work),
        "--output", str(output),
    ]
    for flag, value in modules.items():
        cmd.extend(["--" + flag, value])
    run(cmd, env=env)


def trial_bytes(args) -> int:
    repo = repo_from(args)
    scratch = Path(args.scratch).resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    before_tree = scratch / "tree-before"
    after_tree = scratch / "tree-after"
    shared_work = scratch / "shared-work"
    before_out = scratch / "bytes-before"
    after_out = scratch / "bytes-after"
    if shared_work.exists():
        shutil.rmtree(shared_work)
    shared_work.mkdir(parents=True)
    git_archive(repo, args.before, before_tree)
    git_archive(repo, args.after, after_tree)
    capture_one(before_tree, shared_work, before_out, BEFORE_MODULES)
    capture_one(after_tree, shared_work, after_out, AFTER_MODULES)
    compare = subprocess.run(
        [sys.executable, str(HERE / "trial_bytes.py"), "compare",
         str(before_out), str(after_out)]
    )
    table = subprocess.run(
        [sys.executable, str(HERE / "hash_table.py"), str(before_out), str(after_out)],
        check=True, capture_output=True, text=True,
    )
    sys.stdout.write(table.stdout)
    after_manifest = json.loads((after_out / "manifest.json").read_text(encoding="utf-8"))
    files = after_manifest["files"]
    results = {name: digest for name, digest in files.items()
               if name.endswith("/result.json") and "/verification/" not in name
               and not name.startswith("pure/")}
    digest_files = tree_digest(files)
    digest_results = tree_digest(results)
    print("expected files digest:", EXPECTED_FILE_DIGEST)
    print("actual   files digest:", digest_files)
    print("expected result.json digest:", EXPECTED_RESULT_DIGEST)
    print("actual   result.json digest:", digest_results)
    ok = (
        compare.returncode == 0
        and len(results) == EXPECTED_TRIALS
        and len(files) == EXPECTED_FILES
        and digest_files == EXPECTED_FILE_DIGEST
        and digest_results == EXPECTED_RESULT_DIGEST
    )
    # Linux reference is 448 files. A Windows capture of the same fixtures was
    # historically 447; treat a 447-file capture as a documented platform
    # difference, not a before/after mismatch, but do not claim the Linux digest.
    if compare.returncode == 0 and len(results) == EXPECTED_TRIALS and len(files) != EXPECTED_FILES:
        print("NOTE: retained file count is", len(files),
              "not the Linux reference 448. If this is Windows, see README (447 vs 448).")
        print("Do not compare this digest to the Linux tree digest above.")
        return 0 if digest_results == EXPECTED_RESULT_DIGEST else 2
    return 0 if ok else 2


def qualify(args) -> int:
    repo = repo_from(args)
    scratch = Path(args.scratch).resolve()
    tree = scratch / f"tree-{args.revision[:12]}"
    git_archive(repo, args.revision, tree)
    output = scratch / f"qualify-{args.revision[:12]}"
    if output.exists():
        shutil.rmtree(output)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tree / "src")
    env["PYTHONUTF8"] = "1"
    rc = run([
        sys.executable, "-m", "tools.skill_eval_qualify",
        "--output", str(output),
        "--revision", args.revision,
        "--runner-image", args.runner_image,
    ], cwd=tree, env=env, check=False)
    receipt = output / "qualification.json"
    if receipt.is_file():
        print(receipt.read_text(encoding="utf-8"))
    return rc


def fetch_official_bundle(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        from urllib.request import urlopen
        with urlopen(BUNDLE_URL, timeout=60) as response:
            dest.write_bytes(response.read())
    except Exception as exc:  # noqa: BLE001 — surface a clear reviewer action
        print("Failed to download the official bundle from", BUNDLE_URL)
        print("Error:", exc)
        print("A reviewer with git can also run:")
        print(f"  git fetch origin {EVIDENCE} && git show {EVIDENCE}:artifacts/skill-eval-cloud/bundle.json > {dest}")
        raise SystemExit(2) from exc
    digest = sha256_file(dest)
    if digest != OFFICIAL_BUNDLE_SHA256:
        print("bundle sha256 mismatch:", digest, "expected", OFFICIAL_BUNDLE_SHA256)
        raise SystemExit(2)
    print("official bundle sha256 ok:", digest)
    return dest


def replay_a(args) -> int:
    repo = repo_from(args)
    scratch = Path(args.scratch).resolve()
    tree = scratch / "tree-historical-1052925"
    git_archive(repo, HISTORICAL, tree)
    bundle = fetch_official_bundle(scratch / "official-bundle.json")
    output = scratch / "replay-A"
    if output.exists():
        shutil.rmtree(output)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tree / "src")
    env["PYTHONUTF8"] = "1"
    # The CLI fetches from raw GitHub by evidence commit; passing the pin is enough
    # when the network can reach raw.githubusercontent.com. Keep a local copy for
    # the sha256 check above.
    _ = bundle
    return run([
        sys.executable, "-m", "tools.skill_eval_cloud_replay",
        "--evidence-commit", EVIDENCE,
        "--bundle-sha256", OFFICIAL_BUNDLE_SHA256,
        "--revision", HISTORICAL,
        "--runner-image", args.runner_image,
        "--output", str(output),
    ], cwd=tree, env=env, check=False)


def replay_b(args) -> int:
    repo = repo_from(args)
    scratch = Path(args.scratch).resolve()
    tree = scratch / f"tree-{args.revision[:12]}"
    git_archive(repo, args.revision, tree)
    fetch_official_bundle(scratch / "official-bundle.json")
    output = scratch / "replay-B"
    if output.exists():
        shutil.rmtree(output)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tree / "src")
    env["PYTHONUTF8"] = "1"
    return run([
        sys.executable, "-m", "tools.skill_eval_cloud_replay",
        "--evidence-commit", EVIDENCE,
        "--bundle-sha256", OFFICIAL_BUNDLE_SHA256,
        "--revision", args.revision,
        "--runner-image", args.runner_image,
        "--output", str(output),
    ], cwd=tree, env=env, check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", help="Git clone that contains the pinned SHAs")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("preflight-diag", help="Print sandbox-preflight environment facts")
    p.set_defaults(handler=preflight_diag)

    p = sub.add_parser("trial-bytes", help="Shared-work trial-record capture and compare")
    p.add_argument("--scratch", required=True, help="Writable directory for archives and outputs")
    p.add_argument("--before", default=DEFAULT_BEFORE)
    p.add_argument("--after", default=DEFAULT_AFTER)
    p.set_defaults(handler=trial_bytes)

    p = sub.add_parser("qualify", help="Real bwrap skill_eval_qualify (Linux only)")
    p.add_argument("--scratch", required=True)
    p.add_argument("--revision", default=DEFAULT_AFTER)
    p.add_argument("--runner-image", default=RUNNER_IMAGE)
    p.set_defaults(handler=qualify)

    p = sub.add_parser("replay-a", help="Official bundle on historical controller 1052925")
    p.add_argument("--scratch", required=True)
    p.add_argument("--runner-image", default=RUNNER_IMAGE)
    p.set_defaults(handler=replay_a)

    p = sub.add_parser("replay-b", help="Official bundle on the S01 tree (expected reject)")
    p.add_argument("--scratch", required=True)
    p.add_argument("--revision", default=DEFAULT_AFTER)
    p.add_argument("--runner-image", default=RUNNER_IMAGE)
    p.set_defaults(handler=replay_b)

    args = parser.parse_args()
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main() or 0)
