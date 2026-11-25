"""Seal the actual delivered patch, then reuse Harness for independent execution.

Run on the qualified execution host with the campaign's original InferRSI
runtime. Connection setup belongs to that host's skill/environment, not here.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path

from inferrsi.harness import candidates, project
from inferrsi.harness.artifact_primitives import digest, sha256
from inferrsi.harness.optimization import read_records
from inferrsi.harness.optimization_session import _project_execute, _runtime_identity

from .audit import EvidenceViolation, Report, audit_selection, read, select_patch_round


def write(path, document):
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git(repo, *args):
    # Arrays only; neither task data nor patch bytes are shell commands.
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def seal(project_repo, baseline_revision, campaign, patch, output, *, submission):
    """No measurement starts until clean-Git reconstruction matches the selected attempt."""
    project_repo, campaign, patch, output = map(Path, (project_repo, campaign, patch, output))
    plan, state, _ = read_records(campaign)
    report = Report()
    rounds = audit_selection(plan, state, campaign, report)
    if report.findings:
        raise ValueError("Campaign round/final checks must pass before independent replay")
    selected = select_patch_round(rounds)
    patch_bytes = patch.read_bytes()
    submitted = read(submission)
    expected = {"candidate_id": selected["candidate_id"], "attempt": selected["path"],
                "candidate_sha256": selected["candidate_sha256"],
                "patch_sha256": hashlib.sha256(patch_bytes).hexdigest()}
    if any(submitted[key] != value for key, value in expected.items()):
        raise EvidenceViolation("Patch or selection differs from original submission")
    revision = git(project_repo, "rev-parse", "--verify", baseline_revision + "^{commit}")
    revision = revision.decode().strip()
    if revision != baseline_revision:
        raise ValueError("A full pinned baseline commit is required")
    if output.exists():
        raise ValueError("Independent output must be new; preserve previous attempts")
    output.mkdir(parents=True)
    write(output / "status.json", {"stage": "reconstruction", "verdict": "INCONCLUSIVE"})
    # A separate clone avoids moving the Agent's HEAD or touching its working tree.
    git(project_repo, "clone", "--no-checkout", "--shared", str(project_repo.resolve()),
        str(output.resolve() / "reconstructed"))
    reconstructed = output / "reconstructed"
    git(reconstructed, "config", "core.autocrlf", "false")
    git(reconstructed, "checkout", "--detach", revision)
    includes = plan["candidate_includes"]
    baseline = output / "frozen/baseline"
    baseline.parent.mkdir()
    actual_baseline = candidates.retain(reconstructed, baseline, includes)
    if actual_baseline != plan["baseline_sha256"]:
        raise ValueError("Frozen baseline differs from the pinned clean Git checkout")
    if not patch_bytes.strip():
        raise ValueError("An actual nonempty Agent patch is required")
    (output / "candidate.patch").write_bytes(patch_bytes)
    try:
        git(reconstructed, "apply", "--check", str((output / "candidate.patch").resolve()))
        git(reconstructed, "apply", str((output / "candidate.patch").resolve()))
    except subprocess.CalledProcessError as error:
        raise EvidenceViolation("Delivered patch does not apply to the pinned baseline") from error
    # Reject changes outside the Agent's declared inputs, including new files.
    changed = git(reconstructed, "diff", "--name-only", "-z", "HEAD").split(b"\0")
    added = git(reconstructed, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0")
    declared = candidates.members(reconstructed, includes)
    allowed = set(declared) | set(candidates.members(baseline))
    if any(name.decode("utf-8") not in allowed for name in [*changed, *added] if name):
        raise EvidenceViolation("Delivered patch changes files outside declared candidate inputs")
    attempt = output / "attempt"
    attempt.mkdir()
    actual_candidate = candidates.retain(reconstructed, attempt / "candidate", includes)
    if actual_candidate != selected["candidate_sha256"]:
        raise EvidenceViolation(
            "Delivered patch does not reconstruct the selected Agent round/attempt")
    shutil.copytree(campaign / "frozen/protocol", output / "frozen/protocol")
    (output / "frozen/TASK.md").write_bytes((campaign / "frozen/TASK.md").read_bytes())
    for name, expected in plan["frozen_files"].items():
        if sha256(output / "frozen" / name) != expected:
            raise ValueError("Frozen files changed during independent preparation")
    seal_record = {
        "baseline_revision": revision, "baseline_sha256": actual_baseline,
        "candidate_id": selected["candidate_id"], "attempt": selected["path"],
        "candidate_sha256": actual_candidate, "patch_sha256": sha256(output / "candidate.patch"),
        "plan_digest": digest(plan), "sealed_at": time.time(),
    }
    write(output / "seal.json", seal_record)
    return plan, seal_record


def execute(output, plan, timeout):
    if timeout <= 0:
        raise ValueError("An explicit positive independent budget is required")
    if (output / "attempt/execution").exists() or (output / "receipt.json").exists():
        raise ValueError("Keep previous execution evidence; use a new independent attempt")
    sealed = read(output / "seal.json")
    if (sealed["plan_digest"] != digest(plan)
            or sealed["patch_sha256"] != sha256(output / "candidate.patch")
            or sealed["candidate_sha256"] != candidates.identity(output / "attempt/candidate")
            or sealed["baseline_sha256"] != candidates.identity(output / "frozen/baseline")):
        raise EvidenceViolation("Sealed independent inputs changed before timing")
    for name, expected in plan["frozen_files"].items():
        if sha256(output / "frozen" / name) != expected:
            raise ValueError("Frozen protocol changed before independent timing")
    if plan["runtime_identity"] != _runtime_identity():
        raise ValueError("Use the campaign's frozen InferRSI runtime for independent execution")
    started = time.time()
    write(output / "status.json", {"stage": "measurement", "verdict": "INCONCLUSIVE"})
    execution = _project_execute(output, output / "attempt", plan, started + timeout)
    assessment = project.assess(output / "attempt", plan["evaluation_settings"], execution)
    receipt = {"seal_sha256": sha256(output / "seal.json"), "started_at": started,
               "finished_at": time.time(), "assessment": assessment}
    write(output / "receipt.json", receipt)
    write(output / "status.json", {"stage": "finished", "verdict": assessment["verdict"]})
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("project", "baseline-revision", "campaign", "patch", "submission", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--timeout-seconds", type=float, required=True)
    args = parser.parse_args()
    plan, _ = seal(args.project, args.baseline_revision, args.campaign, args.patch, args.output,
                   submission=args.submission)
    execute(Path(args.output), plan, args.timeout_seconds)


if __name__ == "__main__":
    main()
