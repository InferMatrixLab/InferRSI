"""Main-only, fixed historical pilot orchestration; no dispatch-controlled policy."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from inferrsi.harness import skill_eval_engineering as engineering
from inferrsi.infra.artifacts import sha256, write_json
from tools import skill_eval_auto as auto
from tools import skill_eval_compare as compare
from tools import skill_eval_historical_accounting as accounting
from tools import skill_eval_pr as pr
from tools.skill_eval_cloud_export import export

ROOT = pr.ROOT
CONFIG = ROOT / "tools/skill_eval_historical_config.json"
POLICY = ROOT / "tools/skill_eval_historical_policy.json"
WORKFLOW = ".github/workflows/skill-eval-historical.yml"
REPOSITORY = "InferMatrixLab/InferRSI"
FIXED = {
    "schema_version": 1, "experiment_id": "issue253-generation-only-20261030",
    "repository_id": 1409534281, "issue": 253, "charge_pr": 267,
    "charge_head": "f77f73539d4a5dc781ab1a956d60c49565d676bc",
    "baseline": "a1ee3266466194c16f4e2159ab845b758ed9561b",
    "candidate": "86f003364804d116b3202c4d807cc898a3a02ade",
    "max_requests": 2, "currency": "USD", "amount": "20.34",
    "qualification_run": 41017219756,
}
QUALIFICATION_HEAD = "37166b6f7323c76a091e423a7163ac99c4ae01ac"
LIMITS = {"repeats": 1, "max_task_calls": 2, "timeout_seconds": 180,
          "campaign_seconds": 600, "token_stop_new_trials": 200000}


def read(path):
    return json.loads(engineering.read_regular(Path(path), 1024 * 1024))


def configuration():
    policy, config = read(POLICY), auto.configuration(CONFIG)
    if (set(policy) != set(FIXED) | {"expires_at", "approval_evidence",
                                   "effective_group_attestation"}
            or any(policy.get(key) != value for key, value in FIXED.items())
            or type(policy["expires_at"]) is not int or policy["expires_at"] <= time.time()
            or policy["expires_at"] != config["expires_at"]
            or policy["expires_at"] != config["provider"]["pricing"]["expires_at"]
            or set(config["anchors"]) != {"267"}
            or config["repository_id"] != FIXED["repository_id"]
            or config["operators"] != ["Dong1017"]
            or any(not isinstance(policy[key], str) or not policy[key].strip()
                   for key in ("approval_evidence", "effective_group_attestation"))):
        raise ValueError("Fixed historical policy is incomplete, changed or expired")
    return policy, config


def runtime(config):
    expected = {"GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main",
                "GITHUB_REPOSITORY": REPOSITORY, "GITHUB_RUN_ATTEMPT": "1"}
    if any(os.environ.get(key) != value for key, value in expected.items()):
        raise ValueError("Only first-attempt manual main execution is supported")
    if any(os.environ.get(key) not in config["operators"]
           for key in ("GITHUB_ACTOR", "GITHUB_TRIGGERING_ACTOR")):
        raise ValueError("Unapproved manual operator")
    revision, run_id = os.environ.get("GITHUB_SHA", ""), os.environ.get("GITHUB_RUN_ID", "")
    if not re.fullmatch(r"[0-9a-f]{40}", revision) or not re.fullmatch(r"[1-9][0-9]*", run_id):
        raise ValueError("Invalid runtime identity")
    checkout = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if checkout != revision:
        raise ValueError("Checkout differs from the manual workflow revision")
    return revision, run_id


def verify_live_run(api, revision, run_id, config):
    run = api.request("GET", f"/actions/runs/{run_id}")
    if (run.get("event") != "workflow_dispatch" or run.get("head_branch") != "main"
            or run.get("head_sha") != revision or run.get("run_attempt") != 1
            or run.get("status") != "in_progress" or run.get("path") != WORKFLOW
            or run.get("repository", {}).get("id") != FIXED["repository_id"]
            or any(run.get(key, {}).get("login") not in config["operators"]
                   for key in ("actor", "triggering_actor"))):
        raise ValueError("Live workflow identity does not authorize this execution")
    qualification = api.request("GET", f"/actions/runs/{FIXED['qualification_run']}")
    if (qualification.get("head_sha") != QUALIFICATION_HEAD
            or qualification.get("path") != ".github/workflows/skill-eval-qualify.yml"
            or qualification.get("status") != "completed"
            or qualification.get("conclusion") != "success"):
        raise ValueError("Reviewed isolated-host qualification is not successful")


def prepare(output):
    if os.environ.get("SKILL_EVAL_YIBUAPI_KEY"):
        raise ValueError("Preparation must run before provider-secret injection")
    policy, config = configuration()
    revision, _ = runtime(config)
    output.mkdir(parents=True, exist_ok=False)
    protocol = {"policy": policy, "implementation_sha": revision,
                "execution_mode": engineering.GENERATION_MODE,
                "task_request_sha256": hashlib.sha256(engineering.REQUEST.encode()).hexdigest(),
                "starter_sha256": hashlib.sha256(engineering.STARTER.encode()).hexdigest(),
                "provider_sha256": config["provider_sha256"], "limits": LIMITS,
                "scope": "One public reconstructed CPU parser pair; no iterative agent, "
                         "holdout, hardware or causal/general efficacy claim",
                "comparison_order": ["baseline", "candidate"], "retry_policy": "none",
                "verification": "No source execution during generation; independent "
                                "secret-free same-host-qualified bubblewrap replay"}
    write_json(output / "protocol.json", protocol)
    write_json(output / "cases.json", [{"id": "serving-parser", "split": "development",
               "request": engineering.REQUEST, "provenance": "Public reconstructed parser "
               "contract from PR90; historical skill comparison, not original service replay"}])
    provider = config["provider"]
    comparison = {"mode": "update", "skill": "inference-optimization-casebook",
                  "skill_root": "src/inferrsi/data/skill_library/methods", "cases": "cases.json",
                  "adapter": engineering.ADAPTER, "execution_mode": engineering.GENERATION_MODE,
                  "snapshots": {role: {"git_revision": policy[role]} for role in compare.ROLES},
                  "limits": LIMITS, **{key: provider[key] for key in
                                        ("model", "client", "pricing", "spend_limit")}}
    write_json(output / "comparison.json", comparison)
    plan_digest = compare.prepare(output / "comparison.json", ROOT, output / "run")
    approval = {key: policy[key] for key in (
        "schema_version", "experiment_id", "repository_id", "issue", "charge_pr", "charge_head",
        "baseline", "candidate", "expires_at", "max_requests", "currency", "amount",
        "approval_evidence")}
    approval.update(implementation_sha=revision, plan_sha256=plan_digest,
                    protocol_sha256=sha256(output / "protocol.json"))
    write_json(output / "approval.json", approval)
    manifest = {"implementation_sha": revision, "policy_sha256": sha256(POLICY),
                "config_sha256": sha256(CONFIG), "controller_sha256": sha256(Path(__file__)),
                "approval_sha256": sha256(output / "approval.json"),
                "protocol_sha256": sha256(output / "protocol.json"), "plan_sha256": plan_digest}
    write_json(output / "freeze.json", manifest)
    return manifest


def execute(output):
    policy, config = configuration()
    revision, run_id = runtime(config)
    manifest = read(output / "freeze.json")
    expected = {"implementation_sha": revision, "policy_sha256": sha256(POLICY),
                "config_sha256": sha256(CONFIG), "controller_sha256": sha256(Path(__file__)),
                "approval_sha256": sha256(output / "approval.json"),
                "protocol_sha256": sha256(output / "protocol.json"),
                "plan_sha256": sha256(output / "run/plan/freeze.json")}
    if manifest != expected:
        raise ValueError("Prospective freeze changed before execution")
    # Receipt values are generated only by the reviewed main controller above,
    # not supplied by dispatch, PR artifacts or model output.
    approval = accounting.receipt(output / "approval.json", manifest["approval_sha256"])
    if any(approval[key] != policy[key] for key in policy if key in approval):
        raise ValueError("Approval differs from reviewed main policy")
    api = pr.GitHub(REPOSITORY, os.environ["GITHUB_TOKEN"])
    verify_live_run(api, revision, run_id, config)
    accounting.controlled_execute(api, output / "run", config_path=CONFIG,
                                  approval_path=output / "approval.json",
                                  approval_sha256=manifest["approval_sha256"],
                                  protocol_path=output / "protocol.json", run_id=run_id, attempt=1)


def package(output):
    """Copy only fixed public inputs/data and selected numeric receipts; no raw logs."""
    destination = output / "public"
    destination.mkdir(parents=True, exist_ok=False)
    for name in ("freeze.json", "protocol.json", "approval.json"):
        if (output / name).is_file():
            write_json(destination / name, read(output / name))
    run = output / "run"
    if not (run / "plan/freeze.json").is_file():
        write_json(destination / "capture.json", {"state": "not_prepared"})
        return
    plan = compare.load_plan(run)
    trials = []
    for entry in plan["schedule"]:
        trial = compare.retained_trial(run, entry, engineering.ADAPTER, engineering.GENERATION_MODE)
        observations = trial.get("observations") or {}
        usage = observations.get("usage") or {}
        error = trial.get("evaluation_error")
        trials.append({"task_id": entry["task_id"], "condition": entry["condition"],
                       "repeat": entry["repeat"],
                       "verdict": trial.get("verdict") if trial.get("verdict") in
                       ("PASS", "FAIL", "INCONCLUSIVE") else None,
                       "evaluation_error": error if isinstance(error, str) and
                       re.fullmatch(r"[a-z_]{1,80}", error) else None,
                       "missing": trial.get("missing") is True,
                       "usage": {key: value if type(value) is int and 0 <= value <= 10000000
                                 else None for key in ("input_tokens", "output_tokens",
                                                       "cached_input_tokens")
                                 for value in (usage.get(key),)},
                       "api_requests": observations.get("api_requests") if
                       type(observations.get("api_requests")) is int and
                       0 <= observations["api_requests"] <= 2 else None,
                       "usage_complete": observations.get("usage_complete") is True})
        artifact = compare.trial_directory(run, entry) / "parser.py"
        if artifact.is_file() and not artifact.is_symlink():
            data = engineering.read_regular(artifact, engineering.MAX_SOURCE_BYTES)
            folder = destination / "retained" / entry["condition"]
            folder.mkdir(parents=True)
            (folder / "parser.py").write_bytes(data)
    write_json(destination / "capture.json", {"state": "retained", "trials": trials,
               "scope": "Original capture only; independent artifact replay still required"})
    shutil.copytree(run / "plan", destination / "plan")
    try:
        bundle = export(run, output / "protocol.json")
    except (ValueError, OSError, KeyError):
        write_json(destination / "bundle-status.json", {"state": "incomplete_or_invalid_pair"})
    else:
        write_json(destination / "bundle.json", bundle)
        write_json(destination / "bundle-status.json", {"state": "ready_for_independent_replay",
                   "bundle_sha256": sha256(destination / "bundle.json")})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "execute", "package"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        {"prepare": prepare, "execute": execute, "package": package}[args.action](args.output)
    except Exception as error:
        # Credentials/HTTP diagnostics and model-supplied strings never enter logs.
        print(json.dumps({"state": "blocked_or_failed", "error_type": type(error).__name__}),
              file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
