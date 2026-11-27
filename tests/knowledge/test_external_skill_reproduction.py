import json
import os
import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[2] / "tools" / "reproduce_external_skill.py"
CLOSURE = "52fdf73e8e2cda67bc7ea121f411e699f9a1aef9dde61f5f8f2a15e073ab5d03"
PATHS = {"LICENSE", "SKILL.md", "references/guide.md"}


def run_tool(*args, offline=False):
    env = os.environ.copy()
    if offline:
        env["PATH"] = ""
    return subprocess.run(
        [sys.executable, str(TOOL), *map(str, args)],
        capture_output=True,
        text=True,
        env=env,
        timeout=100,
    )


def test_pinned_link_and_submodule_then_independent_offline_verification(tmp_path):
    evidence = tmp_path / "evidence"
    demo = run_tool("demo", evidence)
    assert demo.returncode == 0, demo.stderr
    report = json.loads(demo.stdout)
    assert report == json.loads((evidence / "report.json").read_text(encoding="utf-8"))
    manifest_path = evidence / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert set(manifest) == PATHS
    assert report["manifest_sha256"] == CLOSURE
    assert report["moved_tag_commit"] != report["registered_commit"]
    assert report["repository"].startswith("http://127.0.0.1:")
    assert report["fresh"]["submodule"]["gitlink"] == report["registered_commit"]
    assert report["fresh"]["link"]["commands"][-1]["argv"][-1] == report["registered_commit"]
    for route in ("link", "submodule"):
        fresh = report["fresh"][route]
        assert fresh["resolved_url"] == report["repository"]
        assert fresh["checkout_commit"] == report["registered_commit"]
        assert fresh["manifest"] == manifest
        assert all(step["exit_code"] == 0 for step in fresh["commands"])
        cold = report["source_unavailable_cold"][route]
        assert cold["exit_code"] != 0
        assert cold["argv"][1] == ("clone" if route == "link" else "submodule")
        assert cold["source_status"] == 503
        assert cold["files"] == {}

    snapshot = evidence / "snapshot"
    assert {p.relative_to(snapshot).as_posix() for p in snapshot.rglob("*") if p.is_file()} == PATHS
    offline_args = ("verify", snapshot, manifest_path, CLOSURE)
    replay = run_tool(*offline_args, offline=True)
    assert replay.returncode == 0, replay.stderr
    expected = {
        "matches": True,
        "closure_sha256": CLOSURE,
        "missing": [],
        "changed": [],
        "unexpected": [],
    }
    assert json.loads(replay.stdout) == expected
    assert report["offline"] == {"snapshot": expected, "populated_submodule": expected}

    (snapshot / "references" / "guide.md").write_bytes(b"changed attachment")
    (snapshot / "LICENSE").unlink()
    (snapshot / "extra.md").write_bytes(b"unregistered")
    replay = run_tool(*offline_args, offline=True)
    assert replay.returncode == 1
    diff = json.loads(replay.stdout)
    assert not diff["matches"] and diff["closure_sha256"] != CLOSURE
    assert diff["changed"] == ["references/guide.md"]
    assert diff["missing"] == ["LICENSE"]
    assert diff["unexpected"] == ["extra.md"]

    manifest.pop("LICENSE")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    altered_manifest = run_tool(*offline_args, offline=True)
    assert altered_manifest.returncode == 1
    assert "Manifest does not match the recorded closure SHA-256" in altered_manifest.stderr
