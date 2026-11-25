"""Validate the recorded replay inputs on the host before launching the first engine."""

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

from inferrsi._version import __commit_id__

import inferrsi
from inferrsi.harness.candidates import identity

PLAN = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text())


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_match(actual, expected, description):
    if actual != expected:
        raise ValueError(f"{description} differs from the recorded value")


def package_digest():
    """Cover installed code and package data independently of path, timestamps and umask."""
    root = Path(inferrsi.__file__).resolve().parent
    files = {
        p.relative_to(root).as_posix(): sha256(p)
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    }
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def check_source(tree, commit, snapshot, role):
    head = subprocess.check_output(["git", "-C", tree, "rev-parse", "HEAD"], text=True).strip()
    require_match(head, commit, f"{role} Git revision")
    require_match(identity(tree, ["vllm_omni"]), snapshot, f"{role} vllm_omni bytes and modes")


def check_sources(baseline, candidate, spec, candidate_digest):
    if baseline.samefile(candidate):
        raise ValueError("Baseline and candidate point to the same tree")
    check_source(baseline, spec["baseline"], spec["baseline_snapshot_sha256"], "Baseline")
    check_source(candidate, spec["candidate"], candidate_digest, "Candidate")


def check_weights(root, manifest_digest):
    manifest = PLAN / "weights.json"
    require_match(sha256(manifest), manifest_digest, "Weight manifest")
    records = read(manifest)
    files = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    require_match(files, {row["path"] for row in records}, "Staged checkpoint file set")
    for row in records:
        path = root / row["path"]
        require_match(path.stat().st_size, row["size"], row["path"])
        require_match(sha256(path), row["sha256"], row["path"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cohort", choices=("shared", "packed"))
    args = parser.parse_args()
    common = read(PLAN / "runspec.json")
    increment = read(PLAN.parent / "incremental/decision.json")
    spec = common if args.cohort == "shared" else increment
    candidate_digest = (
        increment["baseline_snapshot_sha256"]
        if args.cohort == "shared"
        else increment["candidate_sha256"]
    )
    check_sources(
        Path(os.environ["GLM_BASELINE"]), Path(os.environ["GLM_CANDIDATE"]), spec, candidate_digest
    )
    package_pin = read(PLAN / "package-pins.json")[spec["inferrsi"]]
    require_match(__commit_id__, package_pin["scm_commit_id"], "Installed InferRSI build revision")
    require_match(package_digest(), package_pin["files_sha256"], "Installed InferRSI files")
    protocol_root = PLAN.parent if args.cohort == "shared" else PLAN.parent / "incremental"
    for filename, expected in spec["protocol_sha256"].items():
        require_match(sha256(protocol_root / "validator" / filename), expected, filename)
    image_id = subprocess.check_output(
        ["docker", "image", "inspect", "--format", "{{.Id}}", os.environ["GLM_OMNI_IMAGE"]],
        text=True,
    ).strip()
    require_match(image_id, common["runtime_image_id"], "Docker runtime image")
    check_weights(Path(os.environ["GLM_IMAGE_WEIGHTS"]), common["weight_file_manifest_sha256"])
    print(image_id)


if __name__ == "__main__":
    main()
