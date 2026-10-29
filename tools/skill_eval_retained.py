"""Read-only bridge to an authenticated historical main-ancestor verifier.

This is deliberately not an execution/reservation entry point. The caller must run
from a trusted main checkout and publish through GitHub.publish's live-PR guards.
Artifact Python is hash-checked data, never an import or executable.
"""

import hashlib
import io
import json
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

MAX_BYTES = 100 * 1024 * 1024
MAX_FILES = 10000
SHA = r"[0-9a-f]{40}"
DIGEST = r"[0-9a-f]{64}"
WORKFLOW = ".github/workflows/skill-eval-pr.yml"
GIT = ("git", "--no-replace-objects", "--no-lazy-fetch")


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _path(name):
    if (not isinstance(name, str) or not name or "\\" in name or "\x00" in name
            or str(PurePosixPath(name)) != name or name.startswith("/")
            or any(p in {"", ".", ".."} for p in name.split("/"))):
        raise ValueError("Unsafe retained path")
    return name


def _archive(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise ValueError("Missing or oversized retained archive")
    with zipfile.ZipFile(io.BytesIO(raw)) as zipped:
        entries = zipped.infolist()
        names = [m.orig_filename for m in entries]
        if (len(entries) > MAX_FILES or len(set(names)) != len(names)
                or sum(m.file_size for m in entries) > MAX_BYTES):
            raise ValueError("Duplicate or oversized retained archive")
        files = {}
        for member in entries:
            name = member.orig_filename
            mode = stat.S_IFMT(member.external_attr >> 16)
            if member.is_dir():
                _path(name[:-1])
                if mode not in (0, stat.S_IFDIR):
                    raise ValueError("Unsafe retained archive directory")
                continue
            _path(name)
            if mode not in (0, stat.S_IFREG):
                raise ValueError("Unsafe retained archive file")
            files[name] = zipped.read(member)
        return files


def _git(repo, *args):
    return subprocess.check_output([*GIT, *args], cwd=repo, stderr=subprocess.DEVNULL)


def _trusted_code(repo, revision, renderer, plan, destination):
    for value in (revision, renderer):
        if not isinstance(value, str) or re.fullmatch(SHA, value) is None:
            raise ValueError("Expected immutable trusted revision")
    if _git(repo, "rev-parse", "HEAD").decode().strip() != renderer:
        raise ValueError("Renderer is not the trusted checkout")
    try:
        _git(repo, "merge-base", "--is-ancestor", revision, renderer)
    except subprocess.CalledProcessError as error:
        raise ValueError("Verifier is not a trusted main ancestor") from error
    for field, name in (("adapter_sha256", "tools/skill_eval_pr.py"),
                        ("mapping_sha256", "tools/skill_eval_pr_cases.json")):
        if plan.get(field) != _hash(_git(repo, "show", f"{revision}:{name}")):
            raise ValueError("Historical Git blob binding mismatch")
    # Git archive is trusted source; avoid checkout hooks, filters and submodules.
    raw = _git(repo, "archive", "--format=tar", revision, "src", "tools")
    if len(raw) > MAX_BYTES:
        raise ValueError("Oversized historical source archive")
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        members = archive.getmembers()
        if len(members) > MAX_FILES or sum(m.size for m in members) > MAX_BYTES:
            raise ValueError("Oversized historical source tree")
        for member in members:
            if not member.name.endswith(".py"):
                continue
            _path(member.name)
            if not member.isfile():
                raise ValueError("Historical Python must be a regular Git blob")
            path = destination / member.name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.extractfile(member).read())


def _materialize(files, plan, destination, code):
    """Select only frozen inputs, bound to the authenticated original PR plan."""
    contexts = {}
    for item in plan["comparisons"]:
        skill = item["skill"]
        if not isinstance(skill, str) or re.fullmatch(r"[a-z0-9][a-z0-9._-]*", skill) is None:
            raise ValueError("Unsafe retained skill")
        if skill in contexts:
            raise ValueError("Duplicate retained comparison")
        if "plan_sha256" not in item:
            continue
        name = skill + "/plan/freeze.json"
        raw = files[name]
        if _hash(raw) != item["plan_sha256"]:
            raise ValueError("Retained freeze binding mismatch")
        frozen = json.loads(raw)
        if (frozen["skill"] != skill or frozen["exam"] != item["exam"]
                or any(frozen["arms"][role]["git_revision"] != plan[key]
                       for role, key in (("baseline", "base"), ("candidate", "head")))):
            raise ValueError("Retained comparison identity mismatch")
        selected = {name: raw}
        for path, digest in frozen["files"].items():
            _path(path)
            if not path.startswith(("plan/", "validator/")) or path == "plan/freeze.json":
                raise ValueError("Unsafe frozen input path")
            payload = files[skill + "/" + path]
            if (not isinstance(digest, str) or re.fullmatch(DIGEST, digest) is None
                    or _hash(payload) != digest):
                raise ValueError("Frozen input hash mismatch")
            selected[skill + "/" + path] = payload
        for path, digest in frozen["controllers"].items():
            _path(path)
            if not path.startswith(("src/", "tools/")) or not path.endswith(".py"):
                raise ValueError("Unsafe historical controller")
            if _hash((code / path).read_bytes()) != digest:
                raise ValueError("Historical controller hash mismatch")
        # Unexpected plan/validator files cannot hide behind selective extraction.
        prefixes = (skill + "/plan/", skill + "/validator/")
        actual = {name for name in files if name.startswith(prefixes)}
        if actual != set(selected):
            raise ValueError("Frozen input file set mismatch")
        for name, payload in selected.items():
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        contexts[skill] = {"adapter": frozen.get("adapter", "audit"), "exam": frozen["exam"],
                           "tasks": json.loads(selected[skill + "/plan/tasks.json"]),
                           "schema": json.loads(selected[skill + "/plan/schema.json"])}
    (destination / "pr-plan.json").write_bytes(files["pr-plan.json"])
    return contexts


# Fixed program: no artifact-derived command, imports, Python flags or executable.
# Ancestor source is trusted, not hostile sandbox input. The audit hook and denied
# entry points additionally prevent accidental execution/network in report mode.
REPORT_PROGRAM = r'''
import json, sys
from pathlib import Path
code, data, output = map(Path, sys.argv[1:])
sys.dont_write_bytecode = True
sys.path[:0] = [str(code), str(code / "src")]
def deny(*args, **kwargs):
    raise RuntimeError("Historical bridge is report-only")
def audit(event, args):
    if (event.startswith(("socket.", "subprocess.", "os.exec", "os.spawn"))
            or event in {"os.system", "os.fork", "os.posix_spawn"}):
        deny()
sys.addaudithook(audit)
from tools import skill_eval_pr as pr
from tools import skill_eval_compare as compare
for module, names in ((pr, ("main", "prepare", "execute", "authorize", "claim")),
                      (compare, ("main", "prepare", "execute", "provider_client", "run_trial"))):
    for name in names:
        setattr(module, name, deny)
pr.import_results((data / "results.zip").read_bytes(), data)
results = pr.reports(data)
output.write_text(json.dumps(results, allow_nan=False), encoding="utf-8")
'''


def _regrade(code, data, home):
    result = home / "report.json"
    # -I ignores PYTHONPATH/user-site; a fresh HOME and explicit allowlist prevent
    # all GitHub/provider/proxy/cloud credentials from entering the interpreter.
    environment = {"HOME": str(home), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    subprocess.run([sys.executable, "-I", "-c", REPORT_PROGRAM, str(code), str(data), str(result)],
                   cwd=code, env=environment, check=True, timeout=120,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if result.stat().st_size > MAX_BYTES:
        raise ValueError("Oversized historical report")
    reports = json.loads(result.read_text(encoding="utf-8"))
    if not isinstance(reports, list):
        raise ValueError("Invalid historical report")
    return reports


def retained_reports(api, pr_number, source_run, *, trusted_repo, renderer_revision, now):
    """Authenticate and regrade retained data; performs no GitHub writes or spend.

    ``trusted_repo``/``renderer_revision`` MUST be the caller's trusted main
    checkout, never a PR checkout. Missing Git ancestry fails closed (no fetch).
    Failures propagate so a valid existing comment is not replaced by PLANNED.
    """
    from tools import skill_eval_pr as pr
    from tools.skill_eval_auto import retained_source

    if (type(source_run) is not int or source_run <= 0
            or type(pr_number) is not int or pr_number <= 0):
        raise ValueError("Expected positive retained run and PR IDs")
    run = api.request("GET", f"/actions/runs/{source_run}")
    repository = api.request("GET", "")
    if (run.get("id") != source_run or run.get("run_attempt") != 1
            or run.get("path") != WORKFLOW or run.get("event") != "pull_request_target"
            or run.get("status") != "completed"
            or run.get("display_title") != f"skill-eval plan or publish PR {pr_number}"
            or type(repository.get("id")) is not int
            or run.get("repository", {}).get("id") != repository["id"]
            or run.get("repository", {}).get("full_name") != repository.get("full_name")):
        raise ValueError("Untrusted retained source workflow")
    raw, expires = pr.artifact_download(api, source_run, "skill-eval-plan", now)
    if raw is None or now >= expires:
        raise ValueError("Expired retained plan")
    files = _archive(raw)
    if len(files.get("pr-plan.json", b"")) > 4_000_000:
        raise ValueError("Oversized retained plan")
    plan = json.loads(files["pr-plan.json"])
    if (plan["pr"] != pr_number or plan["repository"] != repository["full_name"]
            or plan["head"] != run.get("head_sha")
            or api.pr(pr_number) != {"head": plan["head"], "base": plan["base"]}
            or retained_source(api, plan) != source_run):
        raise ValueError("Stale or unauthenticated retained plan")
    data, result_expiry = pr.artifact_zip(api, source_run, "skill-eval-results", now)
    expires = min(expires, result_expiry)
    if data is None or now >= expires:
        raise ValueError("Expired retained results")
    _archive(data)  # Validate names/modes/size before historical import's whitelist.
    with tempfile.TemporaryDirectory(prefix="skill-eval-retained-") as temporary:
        root = Path(temporary)
        code, inputs, home = (root / name for name in ("code", "inputs", "home"))
        for path in (code, inputs, home):
            path.mkdir()
        _trusted_code(trusted_repo, plan["version"], renderer_revision, plan, code)
        contexts = _materialize(files, plan, inputs, code)
        (inputs / "results.zip").write_bytes(data)
        reports = _regrade(code, inputs, home)
    expected = {item["skill"]: item for item in plan["comparisons"] if "plan_sha256" in item}
    if len(reports) != len(expected) or {r["skill"] for r in reports} != set(expected):
        raise ValueError("Historical report comparison mismatch")
    for report in reports:
        item = expected[report["skill"]]
        if (report["plan_sha256"] != item["plan_sha256"] or report["exam"] != item["exam"]
                or any(report["arms"][role]["git_revision"] != plan[key]
                       for role, key in (("baseline", "base"), ("candidate", "head")))):
            raise ValueError("Historical report binding mismatch")
    return {"plan": plan, "reports": reports, "contexts": contexts, "expires_at": expires,
            "evidence_url": f"https://github.com/{plan['repository']}/actions/runs/{source_run}",
            "renderer_revision": renderer_revision}
