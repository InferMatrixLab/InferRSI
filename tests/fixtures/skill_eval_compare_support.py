import copy
import json
import subprocess
import sys
from pathlib import Path

from inferrsi.infra.artifacts import sha256, write_json

ROOT = Path(__file__).resolve().parents[2]
DATA = json.loads((ROOT / "tests/fixtures/skill_eval_grading.json").read_text(encoding="utf-8"))


def git(repo, *args):
    return subprocess.check_output(
        ["git", "-c", "user.name=Offline Fixture", "-c", "user.email=fixture@example.invalid",
         "-c", "commit.gpgsign=false", *args], cwd=repo, text=True,
    ).strip()


def source_repo(root):
    repo = root / "repo"
    repo.mkdir(parents=True)
    git(repo, "init", "--quiet")
    (repo / ".gitattributes").write_text("library/selected/resource.txt export-ignore\n",
                                         encoding="utf-8")
    for identity in ("selected", "shared"):
        directory = repo / "library" / identity
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text(
            f"---\nname: {identity}\ndescription: offline snapshot fixture\n---\nOld body\n",
            encoding="utf-8",
        )
    write_json(repo / "library/selected/metadata.json", {"references": ["../shared/notes.md"]})
    (repo / "library/selected/resource.txt").write_text("old resource", encoding="utf-8")
    (repo / "library/shared/notes.md").write_text("old dependency", encoding="utf-8")
    (repo / "exam.txt").write_text("old exam (not selected)", encoding="utf-8")
    git(repo, "add", "library", "exam.txt", ".gitattributes")
    git(repo, "commit", "--quiet", "-m", "Fixture old snapshot")
    baseline = git(repo, "rev-parse", "HEAD")
    skill = repo / "library/selected/SKILL.md"
    skill.write_text(skill.read_text(encoding="utf-8").replace("Old body", "New body"),
                     encoding="utf-8")
    (repo / "library/selected/resource.txt").write_text("new resource", encoding="utf-8")
    (repo / "library/shared/notes.md").write_text("new dependency", encoding="utf-8")
    (repo / "exam.txt").write_text("new exam (not selected)", encoding="utf-8")
    git(repo, "add", "library", "exam.txt")
    git(repo, "commit", "--quiet", "-m", "Fixture new snapshot")
    return repo, baseline, git(repo, "rev-parse", "HEAD")


def configuration(root, mode="update", ids=("fix", "regression", "same", "wrong", "error"),
                  repeats=1, **limits):
    repo, baseline, candidate = source_repo(root)
    tasks = [{**copy.deepcopy(DATA["task"]), "id": identity,
              "split": "discovery" if identity == "discovery" else "holdout"} for identity in ids]
    write_json(root / "cases.json", tasks)
    config = {
        "mode": mode, "skill": "selected", "skill_root": "library", "cases": "cases.json",
        "snapshots": {"baseline": {"git_revision": baseline},
                      "candidate": {"git_revision": candidate}},
        "model": {"name": "offline-fixture", "effort": "test"},
        "limits": {"repeats": repeats, "max_task_calls": len(tasks) * repeats * 2,
                   "timeout_seconds": 60, "campaign_seconds": 900,
                   "token_stop_new_trials": 100000, **limits},
    }
    path = root / "config.json"
    write_json(path, config)
    return path, repo


class FixedOutputClient:
    def __init__(self, root, modes=None, timeout_seconds=60):
        self.answer = root / "expected-answer.json"
        write_json(self.answer, DATA["cases"][0]["answer"])
        self.timeout_seconds = timeout_seconds
        self.normal_timeout = timeout_seconds
        self.modes = modes or {}
        self.calls = []

    def command(self, workspace, final, schema, prompt):
        task = json.loads((workspace / "task.json").read_text(encoding="utf-8"))
        role = "baseline" if "-baseline-" in final.parent.name else "candidate"
        self.calls.append({"case_id": task["id"], "role": role, "workspace": workspace,
                           "inputs": {p.relative_to(workspace).as_posix(): p.read_bytes()
                                      for p in workspace.rglob("*") if p.is_file()},
                           "schema_sha256": sha256(schema), "prompt": prompt})
        mode = self.modes.get((task["id"], role), "correct")
        self.timeout_seconds = 1 if mode == "timeout" else self.normal_timeout
        return (sys.executable, str(ROOT / "tests/fixtures/skill_eval_fake_client.py"),
                mode, str(final), str(self.answer))
