"""Exercise the actual publisher shell against a tag/Release-only GitHub mock."""

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/release.yml"
COMMIT = "1" * 40

MOCK_GH = r'''#!/usr/bin/env python
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
sys.stdout.reconfigure(newline="\n")
state_path = Path(os.environ["FAKE_GH_STATE"])
state = json.loads(state_path.read_text())
log = Path(os.environ["FAKE_GH_LOG"])


def record(operation, **data):
    with log.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"operation": operation, **data}) + "\n")


def save():
    state_path.write_text(json.dumps(state))


record("call", args=args)
repo = "repos/example/release"
commit = "1" * 40
tag = "v1.2.3"
if args == ["api", f"{repo}/compare/{commit}...main"]:
    print(json.dumps({"status": state.get("ancestry", "identical"),
                      "base_commit": {"sha": state.get("resolved", commit)}}))
elif args == ["api", "--paginate", "--slurp", f"{repo}/releases?per_page=100"]:
    releases = [{"tag_name": "v1.2.2", "draft": False, "prerelease": True}]
    if state.get("existing"):
        releases.append({"tag_name": tag, "draft": False, "prerelease": True})
    print(json.dumps([releases]))
elif args == ["api", "--method", "POST", f"{repo}/git/refs",
              "-f", f"ref=refs/tags/{tag}", "-f", f"sha={commit}"]:
    record("create_tag", ref=f"refs/tags/{tag}", sha=commit)
    state["tag_created"] = True
    save()
elif args[:3] == ["release", "create", tag]:
    if not state.get("tag_created") or "--draft" not in args or "--verify-tag" not in args:
        raise SystemExit("Release must be prepared as a draft on the existing tag")
    record("create_release")
    state["assets"] = ["inferrsi-1.2.3.whl", "inferrsi-1.2.3.tar.gz", "SHA256SUMS"]
    if state.get("missing_asset"):
        state["assets"].pop()
    save()
elif args == ["release", "view", tag, "--json", "assets", "--jq", ".assets[].name"]:
    print("\n".join(state["assets"]))
elif args == ["api", f"{repo}/git/ref/tags/{tag}", "--jq", ".object.sha"]:
    print("2" * 40 if state.get("moved") else commit)
elif args[:3] == ["release", "edit", tag] and "--draft=false" in args:
    record("publish_release")
else:
    raise SystemExit("Forbidden operation: publisher may only create tags and publish Releases")
'''


def workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_write_token_is_confined_to_a_no_checkout_publisher():
    config = workflow()
    assert config["permissions"] == {"contents": "read", "pull-requests": "none"}
    for name, job in config["jobs"].items():
        if name != "publish":
            assert not job.get("permissions")
            continue
        assert job["permissions"] == {"contents": "write", "pull-requests": "none"}
        actions = [step["uses"] for step in job["steps"] if "uses" in step]
        assert actions == ["actions/download-artifact@v4"]


@pytest.fixture
def publisher(tmp_path):
    bash = shutil.which("bash")
    if os.name == "nt":
        candidate = Path(os.environ.get("ProgramFiles", "")) / "Git/bin/bash.exe"
        bash = str(candidate) if candidate.is_file() else None
    if not bash or not shutil.which("jq"):
        pytest.skip("Publisher shell integration requires bash and jq")
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()
    gh = mock_bin / "gh"
    gh.write_text(MOCK_GH, encoding="utf-8", newline="\n")
    gh.chmod(0o755)
    dist = tmp_path / "dist"
    dist.mkdir()
    checksums = []
    for name in ("inferrsi-1.2.3.whl", "inferrsi-1.2.3.tar.gz"):
        (dist / name).write_bytes(b"synthetic package")
        checksums.append(hashlib.sha256(b"synthetic package").hexdigest() + "  " + name)
    (dist / "SHA256SUMS").write_text("\n".join(checksums) + "\n", encoding="utf-8", newline="\n")
    blocks = []
    for step in workflow()["jobs"]["publish"]["steps"]:
        if "run" in step:
            directory = step.get("working-directory", ".")
            blocks.append(f"(cd {directory}\n{step['run']})")
    script = tmp_path / "publish.sh"
    # Match the Linux runner's LF output when using the native Windows jq binary.
    shim = 'jq() { command jq --binary "$@"; }\n' if os.name == "nt" else ""
    script.write_text("set -euo pipefail\n" + shim + "\n".join(blocks),
                      encoding="utf-8", newline="\n")

    def run(state=None, **inputs):
        state_path, log_path = tmp_path / "state.json", tmp_path / "calls.jsonl"
        state_path.write_text(json.dumps(state or {}), encoding="utf-8")
        env = dict(os.environ)
        env.update(PATH=str(mock_bin) + os.pathsep + env["PATH"],
                   FAKE_GH_STATE=str(state_path), FAKE_GH_LOG=str(log_path),
                   GH_TOKEN="fake-no-access", GH_REPO="example/release", DEFAULT_BRANCH="main",
                   RELEASE_TAG="v1.2.3", RELEASE_COMMIT=COMMIT, PREVIOUS_TAG="v1.2.2",
                   PRERELEASE="true")
        env.update(inputs)
        result = subprocess.run([bash, str(script)], cwd=tmp_path, env=env,
                                capture_output=True, text=True, timeout=30)
        entries = [json.loads(line) for line in log_path.read_text().splitlines()] if (
            log_path.exists()) else []
        mutations = [entry for entry in entries if entry["operation"] != "call"]
        return result, mutations

    return run


def test_publisher_only_creates_a_tag_and_publishes_its_release(publisher):
    result, mutations = publisher()
    assert result.returncode == 0, result.stderr
    assert mutations == [
        {"operation": "create_tag", "ref": "refs/tags/v1.2.3", "sha": COMMIT},
        {"operation": "create_release"}, {"operation": "publish_release"},
    ]


@pytest.mark.parametrize("inputs", [
    {"RELEASE_TAG": "main"}, {"RELEASE_TAG": "refs/heads/main"},
    {"RELEASE_TAG": "--help"}, {"RELEASE_TAG": "v1.2.3\nrefs/heads/main"},
    {"RELEASE_COMMIT": "main"}, {"RELEASE_COMMIT": "1" * 39},
    {"PREVIOUS_TAG": "refs/heads/main"}, {"PRERELEASE": "yes"},
])
def test_invalid_publication_inputs_cannot_write(publisher, inputs):
    result, mutations = publisher(**inputs)
    assert result.returncode != 0
    assert mutations == []


@pytest.mark.parametrize("state", [
    {"existing": True}, {"ancestry": "diverged"}, {"resolved": "2" * 40},
])
def test_conflicting_or_unverified_source_cannot_write(publisher, state):
    result, mutations = publisher(state)
    assert result.returncode != 0
    assert mutations == []


@pytest.mark.parametrize("state", [{"moved": True}, {"missing_asset": True}])
def test_incomplete_or_retargeted_release_cannot_be_published(publisher, state):
    result, mutations = publisher(state)
    assert result.returncode != 0
    assert [entry["operation"] for entry in mutations] == ["create_tag", "create_release"]
