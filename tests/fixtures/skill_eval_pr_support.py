import io
import shutil
import zipfile
from urllib.parse import parse_qs, urlsplit

from inferrsi.infra.artifacts import write_json
from tests.fixtures.skill_eval_compare_support import configuration, git
from tools import skill_eval_compare as compare
from tools import skill_eval_pr as integration


def setup(root, mode="update", ids=("fix", "regression", "same", "wrong", "error", "missing"),
          **limits):
    config_path, repo = configuration(root, ids=ids, **limits)
    config = compare.read_json(config_path)
    before = config["snapshots"]["baseline"]["git_revision"]
    head = config["snapshots"]["candidate"]["git_revision"]
    if mode == "addition":
        addition = root / "addition"
        addition.mkdir()
        git(addition, "init", "--quiet")
        (addition / "seed.txt").write_text("Before skills", encoding="utf-8")
        git(addition, "add", "seed.txt")
        git(addition, "commit", "--quiet", "-m", "Fixture before skill addition")
        before = git(addition, "rev-parse", "HEAD")
        shutil.copytree(repo / "library", addition / "library")
        git(addition, "add", "library")
        git(addition, "commit", "--quiet", "-m", "Fixture skill addition")
        repo, head = addition, git(addition, "rev-parse", "HEAD")
    mapping = {"skill_root": "library", "model": config["model"], "limits": config["limits"],
               "skills": [{"skill": "selected", "entrypoint": "selected/SKILL.md",
                           "paths": ["library/selected", "library/shared/notes.md"],
                           "cases": "cases.json"}]}
    path = root / "mapping.json"
    write_json(path, mapping)
    identity = {"repository": "example/fixture", "pr": 7, "base": before,
                "head": head, "version": head}
    return repo, path, identity


def approval(plan):
    request = {"plan_sha256": integration.fingerprint(plan), "version": plan["version"],
               "base": plan["base"], "head": plan["head"], "budget": integration.budget(plan)}
    current = {key: plan[key] for key in ("base", "head")}
    return integration.authorize(plan, request, "fixture-operator", "write", current)


def envelope(data):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("results.zip", data)
    return buffer.getvalue()


class SimulatedGitHub(integration.GitHub):
    def __init__(self, plan, data=b"", run_id=10):
        super().__init__(plan["repository"], "offline-not-a-credential")
        self.current = {key: plan[key] for key in ("base", "head")}
        self.comments, self.writes, self.fail_response = [], [], False
        self.change_during_read = False
        self.run = {"id": run_id, "path": integration.WORKFLOW, "event": "workflow_dispatch",
                    "display_title": integration.run_title(plan["pr"],
                                                          integration.fingerprint(plan)),
                    "head_sha": plan["version"], "status": "completed"}
        self.artifact = {"id": 90, "name": "skill-eval-results", "expired": False,
                         "expires_at": "2030-01-01T00:00:00Z", "size_in_bytes": len(data)}
        self.data = envelope(data)

    def request(self, method, path, data=None, *, binary=False):
        if method == "GET":
            if path.startswith("/pulls/"):
                return {"state": "open", **{key: {"sha": value}
                                           for key, value in self.current.items()}}
            if path.startswith("/actions/runs/") and "/artifacts" not in path:
                return self.run
            if path.startswith("/actions/runs/") and "/artifacts" in path:
                return {"artifacts": [self.artifact]}
            if path.startswith("/actions/artifacts/"):
                assert binary
                return self.data
            if path.startswith("/issues/") and "/comments?" in path:
                if self.change_during_read:
                    self.current["head"] = "f" * 40
                return self.comments
        if method in ("POST", "PATCH"):
            self.writes.append((method, path, data))
            if method == "POST":
                self.comments.append({"id": 1, "user": {"login": "github-actions[bot]"},
                                      "body": data["body"]})
            else:
                self.comments[0]["body"] = data["body"]
            if self.fail_response:
                self.fail_response = False
                raise ConnectionError("Offline lost response after server accepted publication")
            return {"html_url": "https://github.com/example/fixture/pull/7#issuecomment-1"}
        raise AssertionError((method, path))


class SimulatedWorkflowHistory(integration.GitHub):
    def __init__(self, plan, responses):
        super().__init__(plan["repository"], "offline-not-a-credential")
        self.plan, self.responses, self.pages_requested = plan, responses, []

    def request(self, method, path, data=None, *, binary=False):
        assert method == "GET" and not binary and data is None
        if path.startswith("/collaborators/"):
            return {"permission": "write"}
        if path.startswith("/pulls/"):
            return {"state": "open", **{key: {"sha": self.plan[key]}
                                       for key in ("base", "head")}}
        if path.startswith("/actions/workflows/skill-eval-pr.yml/runs?"):
            query = parse_qs(urlsplit(path).query)
            assert query["event"] == ["workflow_dispatch"] and query["per_page"] == ["100"]
            page = int(query["page"][0])
            self.pages_requested.append(page)
            return self.responses[page - 1]
        raise AssertionError((method, path))
