import argparse
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from inferrsi.harness.skill_evaluation import CodexClient, export_bundle, run_trial, summarize
from inferrsi.infra.artifacts import sha256, write_json
from inferrsi.knowledge_operations import KnowledgeReader, safe_path
from tools.skill_eval_pilot import PROMPT, SCHEMA, observed_tokens

ROOT = Path(__file__).resolve().parents[1]
ROLES = ("baseline", "candidate")
CONTROLLERS = ("tools/skill_eval_compare.py", "tools/skill_eval_pilot.py",
               "src/inferrsi/harness/skill_evaluation.py")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate(config: dict, tasks: list[dict]) -> None:
    if set(config) - {"mode", "skill", "skill_root", "cases", "schema", "grader",
                      "snapshots", "model", "limits"}:
        raise ValueError("Unknown configuration field")
    if config["mode"] not in ("addition", "update"):
        raise ValueError("mode must be addition or update")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", config["skill"]):
        raise ValueError("skill must be an unqualified checkout skill ID")
    safe_path(config["skill_root"])
    if set(config["snapshots"]) != set(ROLES):
        raise ValueError("snapshots must declare baseline and candidate")
    for role in ROLES:
        if set(config["snapshots"][role]) - {"git_revision", "bundle_revision"}:
            raise ValueError("Unknown snapshot field")
        if not re.fullmatch(r"[0-9a-f]{40}", config["snapshots"][role]["git_revision"]):
            raise ValueError("Both snapshots require full immutable Git commit SHAs")
    if config["mode"] == "addition" and "bundle_revision" in config["snapshots"]["baseline"]:
        raise ValueError("Addition baseline has no target bundle revision")
    if set(config["model"]) != {"name", "effort"}:
        raise ValueError("model supports name and effort only")
    if not all(isinstance(v, str) and v for v in config["model"].values()):
        raise ValueError("model name and effort are required")
    limits = config["limits"]
    if set(limits) != {"repeats", "max_task_calls", "timeout_seconds", "campaign_seconds",
                       "token_stop_new_trials"}:
        raise ValueError("Unknown or missing execution limit")
    for name in ("repeats", "max_task_calls", "timeout_seconds", "campaign_seconds",
                 "token_stop_new_trials"):
        if type(limits[name]) is not int or limits[name] <= 0:
            raise ValueError(f"{name} must be a positive integer")
    if not tasks or len({t["id"] for t in tasks}) != len(tasks):
        raise ValueError("cases must be nonempty with unique IDs")
    for task in tasks:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*", task["id"]):
            raise ValueError("case IDs must be safe path components")
        if task["split"] not in ("development", "holdout", "discovery"):
            raise ValueError("Unknown case split")
        if "answer" in task or "expected" in task:
            raise ValueError("Cases must contain inputs only, never grading answers")
    if len(tasks) * limits["repeats"] * 2 > limits["max_task_calls"]:
        raise ValueError("schedule exceeds max_task_calls")


def build_schedule(tasks: list[dict], repeats: int) -> list[dict]:
    schedule = []
    for task in tasks:
        for repeat in range(1, repeats + 1):
            order = ROLES if (len(schedule) // 2) % 2 == 0 else tuple(reversed(ROLES))
            for role in order:
                schedule.append({"task_id": task["id"], "repeat": repeat, "condition": role,
                                 "split": task["split"]})
    return schedule


def snapshot(repo: Path, revision: str, skill_root: str, destination: Path) -> Path:
    # Short temporary paths also accommodate deep libraries on Windows.
    kind = subprocess.check_output(["git", "cat-file", "-t", revision], cwd=repo, text=True)
    if kind.strip() != "commit":
        raise ValueError("Snapshot revision must identify a Git commit")
    entries = subprocess.check_output(
        ["git", "ls-tree", "-rz", revision, "--", skill_root], cwd=repo,
    ).split(b"\0")[:-1]
    if not entries:
        raise ValueError("Snapshot skill_root contains no files")
    members = []
    for entry in entries:
        header, name = entry.split(b"\t", 1)
        mode, kind, digest = header.split()
        if mode not in (b"100644", b"100755") or kind != b"blob":
            raise ValueError("Snapshot symlinks and submodules are not supported")
        members.append((safe_path(name.decode("utf-8")), digest))
    # Read raw Git blobs: archive/export attributes and checkout filters must not alter bytes.
    data = subprocess.run(["git", "cat-file", "--batch"], cwd=repo, check=True,
                          input=b"".join(digest + b"\n" for _, digest in members),
                          capture_output=True).stdout
    offset = 0
    for name, digest in members:
        end = data.index(b"\n", offset)
        actual, kind, size = data[offset:end].split()
        assert actual == digest and kind == b"blob"
        offset = end + 1
        size = int(size)
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data[offset:offset + size])
        offset += size + 1
    return destination / skill_root


def prepare(config_path: Path, repo: Path, output: Path) -> str:
    config = read_json(config_path)
    tasks = read_json(config_path.parent / config["cases"])
    validate(config, tasks)
    schema = read_json(config_path.parent / config["schema"]) if "schema" in config else SCHEMA
    grader = config_path.parent / config["grader"] if "grader" in config else (
        ROOT / "tools/skill_eval_verifier.py"
    )
    output.mkdir(parents=True, exist_ok=False)
    for name in ("plan", "validator", "results"):
        (output / name).mkdir()
    write_json(output / "plan/tasks.json", tasks)
    write_json(output / "plan/schema.json", schema)
    shutil.copyfile(grader, output / "validator/verify.py")
    arms = {}
    with tempfile.TemporaryDirectory(prefix="se-") as temporary:
        for role, short in zip(ROLES, ("b", "c")):
            selected = config["snapshots"][role]
            root = snapshot(repo, selected["git_revision"], config["skill_root"],
                            Path(temporary) / short)
            bundle = None
            if role == "candidate" or config["mode"] == "update":
                reader = KnowledgeReader(skill_root=root)
                reader.read("checkout:" + config["skill"], revision=selected.get("bundle_revision"))
                bundle = export_bundle(reader, "checkout:" + config["skill"],
                                       output / "plan/bundles" / role)
            arms[role] = {"git_revision": selected["git_revision"], "bundle": bundle}
    before = arms["baseline"]["bundle"]
    after = arms["candidate"]["bundle"]
    old = before["resources"] if before else {}
    new = after["resources"]
    changes = [{"path": path, "baseline": old.get(path), "candidate": new.get(path)}
               for path in sorted(old.keys() | new.keys()) if old.get(path) != new.get(path)]
    source_changes = subprocess.check_output(
        ["git", "diff", "--name-status", arms["baseline"]["git_revision"],
         arms["candidate"]["git_revision"], "--"], cwd=repo, text=True,
    ).splitlines()
    files = {p.relative_to(output).as_posix(): sha256(p)
             for folder in (output / "plan", output / "validator")
             for p in sorted(folder.rglob("*")) if p.is_file()}
    plan = {
        "format_version": 1, "mode": config["mode"], "skill": config["skill"],
        "arms": arms, "model": config["model"], "limits": config["limits"],
        "schedule": build_schedule(tasks, config["limits"]["repeats"]),
        "bundle_changes": changes, "source_changes": source_changes,
        "exam": {"cases": files["plan/tasks.json"], "schema": files["plan/schema.json"],
                 "grader": files["validator/verify.py"]},
        "same_bundle": before is not None and before["revision"] == after["revision"],
        "prompt": PROMPT, "files": files,
        "controllers": {name: sha256(ROOT / name) for name in CONTROLLERS},
        "retry_policy": "none", "cost": None,
        "isolation": "Fresh sessions and workspaces; selected bundle only. "
        "CodexClient disables global skills, plugins, apps, memories and web. "
        "Controlled exposure is not OS read confinement.",
    }
    write_json(output / "plan/freeze.json", plan)
    return sha256(output / "plan/freeze.json")


def load_plan(output: Path) -> dict:
    plan = read_json(output / "plan/freeze.json")
    for name, digest in plan["files"].items():
        if sha256(output / name) != digest:
            raise ValueError(f"Frozen input changed: {name}")
    actual = {p.relative_to(output).as_posix()
              for folder in (output / "plan", output / "validator")
              for p in folder.rglob("*") if p.is_file()}
    if actual != set(plan["files"]) | {"plan/freeze.json"}:
        raise ValueError("Frozen input file set changed")
    return plan


def trial_directory(output: Path, entry: dict) -> Path:
    return output / "results" / f"{entry['task_id']}-{entry['condition']}-{entry['repeat']}"


def execute(output: Path, authorization: str, *, client=None) -> dict:
    if authorization != sha256(output / "plan/freeze.json"):
        raise ValueError("Execution requires authorization for this exact plan SHA-256")
    plan = load_plan(output)
    for name, digest in plan["controllers"].items():
        if sha256(ROOT / name) != digest:
            raise ValueError(f"Controller changed after freeze: {name}")
    if any((output / "results").iterdir()):
        raise ValueError("Execution requires fresh results; prepare a new output directory")
    write_json(output / "results/start.json", {"started_at": time.time()})
    if client is None:
        client = CodexClient(plan["model"]["name"], plan["model"]["effort"],
                             plan["limits"]["timeout_seconds"])
    tasks = {task["id"]: task for task in read_json(output / "plan/tasks.json")}
    deadline = time.monotonic() + plan["limits"]["campaign_seconds"]
    tokens, completed, stop_reason = 0, 0, None
    for entry in plan["schedule"]:
        if time.monotonic() >= deadline or tokens >= plan["limits"]["token_stop_new_trials"]:
            stop_reason = "time_budget" if time.monotonic() >= deadline else "token_budget"
            break
        task = tasks[entry["task_id"]]
        role = entry["condition"]
        bundle = plan["arms"][role]["bundle"]
        with tempfile.TemporaryDirectory(prefix="se-trial-") as temporary:
            workspace = Path(temporary)
            write_json(workspace / "task.json", task)
            prompt = plan["prompt"] + "\nTask operation: " + task["request"]
            if bundle is not None:
                folder = ".agents/skills" if task["split"] == "discovery" else "knowledge"
                shutil.copytree(output / "plan/bundles" / role, workspace / folder)
                if task["split"] != "discovery":
                    prompt += "\nUse the assigned skill at " + folder + "/" + bundle["entrypoint"]
            result = run_trial(client, task, role, entry["repeat"], workspace,
                               trial_directory(output, entry), output / "plan/schema.json",
                               output / "validator/verify.py", prompt, deadline)
        tokens += observed_tokens(result["observations"]["usage"])
        completed += 1
        if result["execution_state"] != "completed":
            stop_reason = "client_" + result["execution_state"]
            break
    status = {"recorded_trials": completed, "expected_trials": len(plan["schedule"]),
              "observed_tokens": tokens, "stop_reason": stop_reason,
              "execution_state": "completed" if completed == len(plan["schedule"]) else "stopped"}
    write_json(output / "results/status.json", status)
    return report(output)


def retained_trial(output: Path, entry: dict) -> dict:
    directory = trial_directory(output, entry)
    path = directory / "result.json"
    if not path.is_file():
        interrupted = directory.is_dir()
        return {**entry, "verdict": "INCONCLUSIVE" if interrupted else None,
                "evaluation_error": "interrupted_attempt" if interrupted else None,
                "missing": not interrupted, "checks": None, "output": None,
                "evidence": {}, "elapsed_seconds": None, "observations": {"usage": None}}
    record = read_json(path)
    if any(record[key] != entry[key] for key in ("task_id", "condition", "repeat", "split")):
        raise ValueError("Result identity disagrees with frozen schedule")
    # Select report fields; raw commands and private workspace paths stay in local artifacts.
    selected = {key: record[key] for key in ("task_id", "condition", "repeat", "split",
                "verdict", "checks", "elapsed_seconds", "observations")}
    selected["observations"] = {"usage": record["observations"]["usage"]}
    error = record.get("evaluation_error")
    if error or record["execution_state"] != "completed" or not record["inputs_unchanged"]:
        selected["verdict"] = "INCONCLUSIVE"
    evidence = {}
    for name in ("result.json", "answer.json", "execution.json", "agent/stdout.log",
                 "verification/result.json", "verification/stdout.log", "verification/stderr.log"):
        if (directory / name).is_file():
            evidence[name] = (directory / name).relative_to(output).as_posix()
    answer = directory / "answer.json"
    return {**selected, "evaluation_error": error, "missing": False,
            "output": answer.read_text(encoding="utf-8", errors="backslashreplace")
            if answer.is_file() else None,
            "evidence": evidence}


def condition_summary(trials: list[dict]) -> dict:
    groups = summarize([t for t in trials if not t["missing"]])["conditions"]
    for role in ROLES:
        selected = [t for t in trials if t["condition"] == role]
        group = groups.setdefault(role, {"trials": 0, "verdicts": {}, "evaluation_errors": 0,
                                         "elapsed_seconds": None, "cost": None})
        group["expected_trials"] = len(selected)
        group["missing_trials"] = sum(t["missing"] for t in selected)
        for metric in ("input_tokens", "output_tokens"):
            usage = [t["observations"]["usage"] for t in selected]
            group[metric] = sum(u[metric] for u in usage) if all(
                u is not None and u.get(metric) is not None for u in usage
            ) and usage else None
    return groups


def report(output: Path) -> dict:
    plan = load_plan(output)
    trials = [retained_trial(output, entry) for entry in plan["schedule"]]
    index = {(t["task_id"], t["repeat"], t["condition"]): t for t in trials}
    pairs = []
    for entry in plan["schedule"]:
        if entry["condition"] != "baseline" or entry["split"] == "discovery":
            continue
        arms = {role: index[entry["task_id"], entry["repeat"], role] for role in ROLES}
        before, after = (arms[role]["verdict"] for role in ROLES)
        if any(arm["missing"] for arm in arms.values()):
            outcome = "missing_pair"
        elif "INCONCLUSIVE" in (before, after):
            outcome = "inconclusive"
        else:
            outcome = {("FAIL", "PASS"): "fix", ("PASS", "FAIL"): "regression",
                       ("PASS", "PASS"): "unchanged_correct",
                       ("FAIL", "FAIL"): "unchanged_incorrect"}[before, after]
        pairs.append({"case_id": entry["task_id"], "repeat": entry["repeat"],
                      "outcome": outcome, **arms})
    discovery = [t for t in trials if t["split"] == "discovery"]
    result = {
        "mode": plan["mode"], "skill": plan["skill"],
        "plan_sha256": sha256(output / "plan/freeze.json"),
        "arms": plan["arms"], "model": plan["model"], "limits": plan["limits"],
        "exam": plan["exam"], "same_bundle": plan["same_bundle"],
        "bundle_changes": plan["bundle_changes"], "source_changes": plan["source_changes"],
        "conditions": condition_summary([t for t in trials if t["split"] != "discovery"]),
        "pairs": pairs,
        "counts": {name: sum(p["outcome"] == name for p in pairs) for name in (
            "fix", "regression", "unchanged_correct", "unchanged_incorrect", "missing_pair",
            "inconclusive")},
        "discovery": discovery, "discovery_conditions": condition_summary(discovery),
        "status": read_json(output / "results/status.json")
        if (output / "results/status.json").is_file() else {"execution_state": "not_completed"},
        "claim": "Pipeline results only; fixed-output offline clients do not establish "
        "skill efficacy. Discovery is separate. Unknown usage and cost remain unknown.",
    }
    write_json(output / "report.json", result)
    (output / "report.md").write_text(markdown(result), encoding="utf-8")
    return result


def markdown(result: dict) -> str:
    lines = ["# Skill comparison", "", result["claim"], "",
             f"Mode: **{result['mode']}** · Skill: `{result['skill']}`", "",
             f"Frozen plan: `{result['plan_sha256']}`", "",
             "| Role | Git revision | Bundle revision |", "| --- | --- | --- |"]
    for role, arm in result["arms"].items():
        bundle = arm["bundle"]
        lines.append(f"| {role} | `{arm['git_revision']}` | "
                     + (f"`{bundle['revision']}`" if bundle else "absent") + " |")
    lines += ["", "Shared model/settings: `" + json.dumps(result["model"], sort_keys=True) + "`",
              "", "Execution limits: `" + json.dumps(result["limits"], sort_keys=True) + "`",
              "", "Frozen exam hashes: `" + json.dumps(result["exam"], sort_keys=True) + "`",
              "", f"Identical bundle: {result['same_bundle']}", "",
              "Counts: `" + json.dumps(result["counts"], sort_keys=True) + "`", "",
              "Usage (null means unknown): `" + json.dumps(result["conditions"], sort_keys=True)
              + "`", "", "| Case | Repeat | Baseline | Candidate | Outcome |",
              "| --- | --- | --- | --- | --- |"]
    for pair in result["pairs"]:
        lines.append(f"| {pair['case_id']} | {pair['repeat']} | "
                     f"{pair['baseline']['verdict'] or 'missing'} | "
                     f"{pair['candidate']['verdict'] or 'missing'} | {pair['outcome']} |")
    lines += ["", "## Retained outputs and grading evidence", ""]
    if result["discovery"]:
        lines += ["Discovery is excluded from the paired counts and main condition totals.", "",
                  "Discovery totals: `" + json.dumps(result["discovery_conditions"], sort_keys=True)
                  + "`", ""]
    for trial in [p[role] for p in result["pairs"] for role in ROLES] + result["discovery"]:
        lines += [f"### {trial['task_id']} / {trial['repeat']} / {trial['condition']}", "",
                  f"Verdict: {trial['verdict'] or 'missing'}; error: "
                  f"{trial['evaluation_error'] or 'none'}; split: {trial['split']}", ""]
        lines += [f"[{name}]({path})" for name, path in trial["evidence"].items()]
        lines += ["", "Grading assertions:", "", "```json",
                  json.dumps(trial["checks"], ensure_ascii=False, sort_keys=True), "```", "",
                  "Output (invalid UTF-8 bytes are shown as backslash escapes):", "", "````text",
                  trial["output"] or "(unavailable)", "````", ""]
    lines += ["## Snapshot changes", "", "### Exported resources and dependencies", "",
              "```json", json.dumps(result["bundle_changes"], indent=2), "```", "",
              "### Git source changes", "", "The same frozen exam is used by both arms. "
              "Source changes below are surfaced, not substituted for that exam.", "", "```text",
              "\n".join(result["source_changes"]) or "(none)", "```", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Configured skill addition/update comparison")
    parser.add_argument("mode", choices=("prepare", "execute", "report"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--authorize", help="Explicit execution authorization: frozen plan SHA-256")
    args = parser.parse_args()
    output = args.output.resolve()
    if args.mode == "prepare":
        if args.config is None or args.repo is None:
            parser.error("prepare requires --config and --repo")
        digest = prepare(args.config.resolve(), args.repo.resolve(), output)
        print(json.dumps({"plan_sha256": digest}))
    elif args.mode == "execute":
        if args.authorize is None:
            parser.error("execute requires --authorize <frozen-plan-sha256>")
        execute(output, args.authorize)
    else:
        report(output)


if __name__ == "__main__":
    main()
