"""CPU-only reproducible single-step experiment; all answer/usage choices are scripted."""

import argparse
import copy
import json
import sys
import tempfile
from pathlib import Path

from inferrsi.infra.artifacts import write_json
from tests.fixtures.skill_eval_compare_support import DATA, ROOT, source_repo
from tools import skill_eval_compare as compare
from tools import skill_eval_improve as improve


def configuration(root):
    repo, baseline, _ = source_repo(root)
    tasks = {}
    answers = {}
    # Different audit cases in development and holdout, with independent fixed answers.
    for split, indices in (("development", (0, 1, 2)), ("holdout", (3, 4, 5))):
        tasks[split] = []
        for category, index in zip(("control", "general", "domain"), indices):
            case = DATA["cases"][index]
            task = copy.deepcopy(DATA["task"])
            task.update(id=f"{split}-{category}", split=split)
            for key, value in case["changes"].items():
                target = task
                fields = key.split(".")
                for field in fields[:-1]:
                    target = target[field]
                target[fields[-1]] = value
            tasks[split].append(task)
            answers[task["id"]] = case["answer"]
    write_json(root / "answers.json", answers)
    config = {"skill": "selected", "skill_root": "library", "baseline": baseline,
              "allowed_paths": ["selected/SKILL.md", "selected/resource.txt"],
              "proposals": {
                  "inv": {"selected/SKILL.md": "---\nname: selected\n"
                          "description: offline snapshot fixture\n---\nINV enabled\n"},
                  "dom": {"selected/resource.txt": "DOM enabled\n"}},
              **tasks, "model": {"name": "offline-fixture", "effort": "test"},
              "selection": {"min_success_rate": 0.5, "max_regressions": 0},
              "limits": {"repeats": 1, "max_task_calls": 24, "timeout_seconds": 10,
                         "campaign_seconds": 300, "token_stop_new_trials": 2400}}
    return config, repo


class ScriptedClient:
    timeout_seconds = 10

    def __init__(self, root, phase, fault=None):
        self.root, self.phase, self.fault = root, phase, fault
        self.calls = []

    def command(self, workspace, final, schema, prompt):
        task = compare.read_json(workspace / "task.json")
        inv = "INV enabled" in (workspace / "knowledge/selected/SKILL.md").read_text()
        dom = "DOM enabled" in (workspace / "knowledge/selected/resource.txt").read_text()
        category = task["id"].split("-")[-1]
        correct = category == "control" or (category == "general" and inv) or (
            category == "domain" and dom)
        tokens = 60 if inv and dom else 80 if inv else 70 if dom else 100
        fault = "none"
        if self.fault == "worse" and (inv or dom):
            correct, tokens = False, 25
        elif self.fault == "compose_regression" and inv and dom:
            correct = False
        elif self.fault == "dominated" and inv and dom:
            correct, tokens = category != "domain", 90
        elif self.fault == "holdout_regression" and self.phase == "holdout" and (inv or dom):
            correct = False
        elif self.fault in ("unknown_usage", "string_usage", "list_usage",
                            "runner_error", "hidden_write") and inv:
            fault = self.fault
        answers = compare.read_json(self.root / "answers.json")
        answer = final.parent.parent / (final.parent.name + "-fixed.json")
        write_json(answer, answers[task["id"]])
        self.calls.append({"task_id": task["id"], "phase": self.phase,
                           "files": sorted(p.relative_to(workspace).as_posix()
                                           for p in workspace.rglob("*") if p.is_file())})
        return (sys.executable, str(ROOT / "tests/fixtures/harness_improvement_client.py"),
                str(answer), str(final), "yes" if correct else "no", str(tokens), fault)


def run_demo(output):
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="improvement-demo-") as temporary:
        root = Path(temporary)
        config, repo = configuration(root)
        results = {}
        for scenario, fault in (("bounded_loop", None), ("worse", "worse"),
                                ("compose_regression", "compose_regression"),
                                ("dominated", "dominated"),
                                ("holdout_regression", "holdout_regression")):
            directory = output / scenario
            digest = improve.prepare(config, repo, directory)
            results[scenario] = improve.run_offline(
                repo, directory, digest, client_factory=lambda phase, candidate, fault=fault:
                ScriptedClient(root, phase, fault))
        for name, repeats in (("h0", 1), ("repeated_h0", 4)):
            comparison = {key: config[key] for key in ("skill", "skill_root", "model")}
            comparison.update(mode="update", cases=f"{name}-tasks.json", snapshots={
                role: {"git_revision": config["baseline"]} for role in compare.ROLES},
                limits={**config["limits"], "repeats": repeats})
            write_json(output / f"{name}-tasks.json", config["holdout"])
            write_json(output / f"{name}-config.json", comparison)
            digest = compare.prepare(output / f"{name}-config.json", repo, output / name)
            results[name] = compare.execute(output / name, digest,
                                           client=ScriptedClient(root, name))
        summary = {name: {
            "selected": r["selected"], "accepted": r["accepted"],
            "successes": r["holdout"]["successes"], "trials": r["holdout"]["trials"],
            "total_calls": r["usage"]["total"]["calls"],
            "total_tokens": r["usage"]["total"]["total_tokens"],
            "search_tokens": r["usage"]["search"]["total_tokens"],
            "selected_holdout_tokens": r["usage"]["selected_holdout"]["total_tokens"],
            "wall_seconds": r["wall_seconds"],
        } for name, r in results.items() if name not in ("h0", "repeated_h0")}
        for name in ("h0", "repeated_h0"):
            r = results[name]
            summary[name] = {"successes": r["conditions"]["candidate"]["verdicts"]["PASS"],
                             "trials": r["conditions"]["candidate"]["trials"],
                             "total_calls": r["status"]["recorded_trials"],
                             "total_tokens": r["status"]["observed_tokens"]}
        write_json(output / "summary.json", {"kind": "scripted_controller_experiment",
                                              "limits": config["limits"], "results": summary})
        return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(run_demo(parser.parse_args().output.resolve()), indent=2))
