import copy
import json
import sys

from inferrsi.infra.artifacts import write_json
from tests.fixtures.skill_eval_compare_support import DATA, ROOT, git


def configuration(root, *, repeats=1, max_calls=32, token_stop=100000):
    root.mkdir(parents=True, exist_ok=True)
    repo = root / "repo"
    repo.mkdir()
    git(repo, "init", "--quiet")
    folder = repo / "library/audit"
    folder.mkdir(parents=True)
    body = "---\nname: audit\ndescription: offline test fixture\n---\nH0\n"
    (folder / "SKILL.md").write_text(body, encoding="utf-8")
    (folder / "notes.md").write_text("H0 notes\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "--quiet", "-m", "H0 fixture")
    baseline = git(repo, "rev-parse", "HEAD")
    (folder / "SKILL.md").write_text(body + "INV\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "--quiet", "-m", "INV fixture")
    inv = git(repo, "rev-parse", "HEAD")
    (folder / "SKILL.md").write_text(body, encoding="utf-8")
    (folder / "notes.md").write_text("DOM notes\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "--quiet", "-m", "DOM fixture")
    dom = git(repo, "rev-parse", "HEAD")
    tasks = [{**copy.deepcopy(DATA["task"]), "id": f"{split}-{i}", "split": split}
             for split in ("development", "holdout") for i in (1, 2)]
    write_json(root / "cases.json", tasks)
    config = {
        "skill": "audit", "skill_root": "library", "cases": "cases.json",
        "snapshots": {name: {"git_revision": rev}
                      for name, rev in (("H0", baseline), ("INV", inv), ("DOM", dom))},
        "model": {"name": "offline-fixture", "effort": "fixed"},
        "limits": {"repeats": repeats, "max_task_calls": 8 * repeats,
                   "timeout_seconds": 20, "campaign_seconds": 120,
                   "token_stop_new_trials": token_stop},
        "budget": {"max_task_calls": max_calls, "campaign_seconds": 120,
                   "token_stop_new_trials": token_stop},
        "policy": {"min_success_rate": 1.0, "max_regressions": 0,
                   "quality_weight": 1.0, "token_weight": 1.0},
        "allowlist": ["audit/SKILL.md", "audit/notes.md"],
    }
    write_json(root / "config.json", config)
    return root / "config.json", repo


class ImprovementClient:
    """A trusted fixture adapter; scripted outcomes must never be called efficacy."""

    timeout_seconds = 20

    def __init__(self, root, overrides=None, token_overrides=None):
        self.answer = root / "answer.json"
        write_json(self.answer, DATA["cases"][0]["answer"])
        self.overrides = overrides or {}
        self.token_overrides = token_overrides or {}
        self.calls = []

    def command(self, workspace, final, schema, prompt):
        task = json.loads((workspace / "task.json").read_text(encoding="utf-8"))
        body = (workspace / "knowledge/audit/SKILL.md").read_text(encoding="utf-8")
        notes = (workspace / "knowledge/audit/notes.md").read_text(encoding="utf-8")
        candidate = "INV" if "INV" in body else "DOM" if "DOM" in notes else "H0"
        stage = final.parents[2].name
        mode = "incorrect" if candidate == "DOM" and task["id"].endswith("-1") else "correct"
        mode = self.overrides.get((stage, candidate), mode)
        tokens = self.token_overrides.get((stage, candidate),
                                         {"H0": 120, "INV": 60, "DOM": 40}[candidate])
        self.calls.append({"stage": stage, "candidate": candidate, "case": task["id"],
                           "files": sorted(p.relative_to(workspace).as_posix()
                                           for p in workspace.rglob("*") if p.is_file()),
                           "prompt": prompt})
        return (sys.executable, str(ROOT / "tests/fixtures/skill_eval_improvement_client.py"),
                mode, str(final), str(self.answer), str(tokens))
