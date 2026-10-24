import argparse
import hashlib
import html
import io
import json
import os
import re
import stat
import subprocess
import time
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from inferrsi.infra.artifacts import sha256, write_json
from tools import skill_eval_compare as compare
from tools.skill_eval_verifier import verify

ROOT = Path(__file__).resolve().parents[1]
MAPPING = ROOT / "tools/skill_eval_pr_cases.json"
WORKFLOW = ".github/workflows/skill-eval-pr.yml"
MARKER = "<!-- inferrsi-skill-eval-pr:v1 -->"
RETENTION_DAYS = 30
MAX_ARCHIVE = 100 * 1024 * 1024
SHA = r"[0-9a-f]{40}"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def git(repo, *args):
    return subprocess.check_output([*compare.GIT_READ, *args], cwd=repo)


def changed_files(repo, base, head):
    fields = git(repo, "diff", "--no-renames", "--name-status", "-z", base, head).split(b"\0")
    return [{"status": fields[i].decode(), "path": fields[i + 1].decode()}
            for i in range(0, len(fields) - 1, 2)]


def blob_exists(repo, revision, path):
    return bool(git(repo, "ls-tree", revision, "--", path).strip())


def prepare(repo, mapping_path, identity, output):
    # Read only trusted configuration and raw Git objects, never PR Python or graders.
    for key in ("base", "head", "version"):
        if not re.fullmatch(SHA, identity[key]):
            raise ValueError("Expected immutable revision: " + key)
    mapping = compare.read_json(mapping_path)
    changes = changed_files(repo, identity["base"], identity["head"])
    output.mkdir(parents=True, exist_ok=False)
    coverage, selected = [], set()
    for change in changes:
        matches = [item for item in mapping["skills"] if any(
            change["path"] == path or change["path"].startswith(path.rstrip("/") + "/")
            for path in item["paths"])]
        status = "uncovered"
        if matches:
            status = "unsupported" if change["status"] not in ("A", "M") else "covered"
            if status == "covered":
                selected.update(item["skill"] for item in matches)
        coverage.append({**change, "coverage": status})
    comparisons = []
    for item in mapping["skills"]:
        if item["skill"] not in selected:
            continue
        entrypoint = mapping["skill_root"] + "/" + item["entrypoint"]
        if not blob_exists(repo, identity["head"], entrypoint):
            for entry in coverage:
                if any(entry["path"].startswith(p.rstrip("/") + "/")
                       or entry["path"] == p for p in item["paths"]):
                    entry["coverage"] = "unsupported"
            continue
        config = {"mode": "update" if blob_exists(repo, identity["base"], entrypoint)
                  else "addition", "skill": item["skill"], "skill_root": mapping["skill_root"],
                  "cases": str((mapping_path.parent / item["cases"]).resolve()),
                  "snapshots": {"baseline": {"git_revision": identity["base"]},
                                "candidate": {"git_revision": identity["head"]}},
                  "model": mapping["model"], "limits": mapping["limits"]}
        config_path = output / (item["skill"] + ".json")
        write_json(config_path, config)
        destination = output / item["skill"]
        try:
            digest = compare.prepare(config_path, repo, destination)
        except ValueError as error:
            # Unsupported snapshots remain visible; they are never task passes.
            comparisons.append({"skill": item["skill"], "unsupported": str(error)})
            for entry in coverage:
                if any(entry["path"] == p or entry["path"].startswith(p.rstrip("/") + "/")
                       for p in item["paths"]):
                    entry["coverage"] = "unsupported"
            continue
        finally:
            config_path.unlink()
        plan = compare.load_plan(destination)
        comparisons.append({"skill": item["skill"], "mode": plan["mode"],
                            "plan_sha256": digest, "cases": [
                                {"id": t["id"], "split": t["split"]}
                                for t in compare.read_json(destination / "plan/tasks.json")],
                            "exam": plan["exam"], "calls": len(plan["schedule"])})
    plan = {"format_version": 1, **identity, "mapping_sha256": sha256(mapping_path),
            "adapter_sha256": sha256(Path(__file__)), "coverage": coverage,
            "comparisons": comparisons, "model": mapping["model"], "limits": mapping["limits"],
            "estimated_calls": sum(c.get("calls", 0) for c in comparisons),
            "retention_days": RETENTION_DAYS}
    write_json(output / "pr-plan.json", plan)
    return plan


def budget(plan):
    return {"estimated_calls": plan["estimated_calls"], "limits_per_comparison": plan["limits"],
            "comparisons": sum("plan_sha256" in c for c in plan["comparisons"])}


def execution_id(plan):
    return "skill-eval-" + fingerprint(plan)


def run_title(pr, digest):
    return f"skill-eval execute PR {pr} plan {digest}"


def authorize(plan, request, actor, permission, current):
    expected = {"plan_sha256": fingerprint(plan), "version": plan["version"],
                "base": plan["base"], "head": plan["head"], "budget": budget(plan)}
    if permission not in ("write", "maintain", "admin") or not actor:
        raise ValueError("Execution requires an operator with repository write permission")
    if request != expected:
        raise ValueError("Explicit approval must match the exact plan, versions and budget")
    if current != {"base": plan["base"], "head": plan["head"]}:
        raise ValueError("PR changed; prepare and authorize a new plan")
    if not plan["estimated_calls"]:
        raise ValueError("No supported comparisons selected")
    return {**expected, "actor": actor, "execution_id": execution_id(plan)}


def claim(plan, runs, run_id, attempt):
    # Actions' serialized workflow and durable run history are the execution tombstone.
    # Failed/cancelled/rerun attempts remain consumed, even after evidence expires.
    if attempt != 1:
        raise ValueError("Execution attempts cannot be rerun; publish retained evidence only")
    title = run_title(plan["pr"], fingerprint(plan))
    owners = [r["id"] for r in runs if r["event"] == "workflow_dispatch"
              and r["display_title"] == title]
    if not owners or min(owners) != run_id:
        raise ValueError("Duplicate or uncertain execution; paid work will not be restarted")
    return execution_id(plan)


def execute(output, approval, *, client=None):
    plan = compare.read_json(output / "pr-plan.json")
    if approval["execution_id"] != execution_id(plan):
        raise ValueError("Approval belongs to another plan")
    # Exclusive creation also protects local/offline callers sharing retained storage.
    with (output / "execution-claim.json").open("x", encoding="utf-8") as handle:
        handle.write(canonical(approval))
    for item in plan["comparisons"]:
        if "plan_sha256" in item:
            # Artifact downloads omit empty directories required by the executor.
            (output / item["skill"] / "results").mkdir(exist_ok=True)
            compare.execute(output / item["skill"], item["plan_sha256"], client=client)


def result_archive(output):
    plan = compare.read_json(output / "pr-plan.json")
    archive = output / "results.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
        for item in plan["comparisons"]:
            folder = output / item["skill"] / "results"
            if folder.is_dir():
                for path in sorted(folder.rglob("*")):
                    if path.is_file() and not path.is_symlink():
                        zipped.write(path, path.relative_to(output).as_posix())
    return archive


def import_results(data, output):
    # No extractall, artifact imports, or artifact commands in the trusted publisher.
    if len(data) > MAX_ARCHIVE:
        raise ValueError("Result archive too large")
    plan = compare.read_json(output / "pr-plan.json")
    allowed = set()
    for item in plan["comparisons"]:
        if "plan_sha256" not in item:
            continue
        prefix = item["skill"] + "/results/"
        allowed.update(prefix + p for p in ("start.json", "status.json", "status.receipt.json"))
        frozen = compare.load_plan(output / item["skill"])
        for entry in frozen["schedule"]:
            trial = compare.trial_directory(output / item["skill"], entry).name
            files = ("answer.json", "result.json", "receipt.json", *compare.EVIDENCE)
            allowed.update(prefix + trial + "/" + p for p in files)
    with zipfile.ZipFile(io.BytesIO(data)) as zipped:
        members = zipped.infolist()
        names = [m.filename for m in members]
        if (len(names) != len(set(names)) or set(names) - allowed
                or sum(m.file_size for m in members) > MAX_ARCHIVE):
            raise ValueError("Unexpected, duplicate or oversized result archive entries")
        for member in members:
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG)):
                raise ValueError("Only regular result files are accepted")
            path = PurePosixPath(member.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in member.filename:
                raise ValueError("Unsafe result path")
        for member in members:
            target = output / member.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zipped.read(member))


def reports(output):
    plan = compare.read_json(output / "pr-plan.json")
    results = []
    for item in plan["comparisons"]:
        if "plan_sha256" not in item:
            continue
        directory = output / item["skill"]
        for entry in compare.load_plan(directory)["schedule"]:
            path = compare.trial_directory(directory, entry) / "result.json"
            if path.is_file():
                record = compare.read_json(path)
                if (not isinstance(record, dict)
                        or type(record.get("inputs_unchanged")) is not bool):
                    raise ValueError("Untrusted input-integrity flag must be a boolean")
        result = compare.report(directory)
        tasks = {t["id"]: t for t in compare.read_json(directory / "plan/tasks.json")}
        for trial in [p[r] for p in result["pairs"] for r in compare.ROLES] + result["discovery"]:
            if trial["verdict"] in ("PASS", "FAIL"):
                # Recheck the supported grader using trusted code, not artifact verify.py.
                checks = verify(tasks[trial["task_id"]], json.loads(trial["output"]))
                if checks != trial["checks"] or checks["passed"] != (trial["verdict"] == "PASS"):
                    raise ValueError("Untrusted grading disagrees with the trusted grader")
        results.append(result)
    return results


def summary(plan, results, evidence_url, expires_at, now):
    expired = now >= expires_at
    lines = [MARKER, "## Skill evaluation", "", f"Plan SHA-256: `{fingerprint(plan)}`",
             f"Base: `{plan['base']}` · Head: `{plan['head']}`",
             f"Trusted implementation: `{plan['version']}`", "",
             "Applicable only while these revisions and inputs match the current PR.", "",
             "Model/settings: `" + canonical(plan["model"]) + "`",
             "Budget: `" + canonical(budget(plan)) + "`", "",
             "Token usage stops new trials; it is not a hard provider token or monetary cap.",
             "Cost remains unknown.", "", "| Skill | Comparison | Cases | Estimated calls |",
             "| --- | --- | --- | --- |"]
    for item in plan["comparisons"]:
        if "plan_sha256" in item:
            cases = ", ".join(c["id"] + " (" + c["split"] + ")" for c in item["cases"])
            lines.append(f"| {item['skill']} | {item['mode']} | {cases} | {item['calls']} |")
            lines.append("\nFrozen exam hashes: `" + canonical(item["exam"]) + "`\n")
        else:
            lines.append(f"| {item['skill']} | unsupported snapshot | — | 0 |")
    counts = {k: 0 for k in ("fix", "regression", "unchanged_correct", "unchanged_incorrect",
                             "inconclusive", "missing_pair")}
    if expired:
        lines += ["", "**EXPIRED: retained evidence is no longer verifiable.**"]
    elif results:
        for result in results:
            for key in counts:
                counts[key] += result["counts"][key]
        lines += ["", "Outcomes: `" + canonical(counts) + "`", "",
                  "Discovery is reported separately in retained evidence."]
    else:
        counts["missing_pair"] = sum(
            sum(c["split"] != "discovery" for c in item["cases"]) * plan["limits"]["repeats"]
            for item in plan["comparisons"] if "plan_sha256" in item)
        lines += ["", "**PLANNED: execution is not authorized by knowing this hash.**",
                  "Outcomes: `" + canonical(counts) + "`",
                  "Earlier revision results are stale for this plan."]
    gaps = [c for c in plan["coverage"] if c["coverage"] != "covered"]
    lines += ["", f"Uncovered/unsupported changes: **{len(gaps)}**. "
              "Gaps never count as passes.", ""]
    # Encode untrusted Git paths as data, so Markdown/mentions cannot escape into the comment.
    for gap in gaps:
        lines.append("- " + gap["coverage"] + ": <code>"
                     + html.escape(canonical(gap["path"])).replace("@", "&#64;") + "</code>")
    lines += ["", f"[Evidence and logs]({evidence_url}) · Retention: {RETENTION_DAYS} days.",
              f"Outcomes are historical; verifiable only before Unix time `{int(expires_at)}` "
              "while the linked artifact is available. Expired evidence is unverified.",
              "", "Pipeline evidence only; offline fixed outputs do not establish skill efficacy."]
    return "\n".join(lines)


class GitHub:
    def __init__(self, repository, token):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("Invalid repository")
        self.repository, self.token = repository, token

    def request(self, method, path, data=None, *, binary=False):
        url = "https://api.github.com/repos/" + self.repository + path
        request = urllib.request.Request(url, method=method, headers={
            "Authorization": "Bearer " + self.token, "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"},
            data=None if data is None else canonical(data).encode())
        with urllib.request.build_opener(ArtifactRedirect()).open(request, timeout=60) as response:
            raw = response.read(MAX_ARCHIVE + 1)
        return raw if binary else json.loads(raw)

    def pages(self, path, key=None, *, require_complete=False):
        records, page, total, seen = [], 1, None, set()
        while True:
            data = self.request("GET", path + ("&" if "?" in path else "?")
                                + f"per_page=100&page={page}")
            batch = data[key] if key else data
            if require_complete:
                count = data.get("total_count")
                # Filtered workflow-run searches stop at 1,000; that boundary is ambiguous.
                if type(count) is not int or not 0 <= count < 1000:
                    raise ValueError(
                        "Workflow history total is unknown or reaches the search limit")
                if total is not None and count != total:
                    raise ValueError("Workflow history changed during pagination")
                total = count
                identities = {record["id"] for record in batch}
                if len(identities) != len(batch) or seen & identities:
                    raise ValueError("Workflow history pages contain duplicate records")
                if len(records) + len(batch) > total:
                    raise ValueError("Workflow history exceeds its reported total")
                seen.update(identities)
            records.extend(batch)
            if require_complete and len(records) == total:
                return records
            if len(batch) < 100:
                if require_complete:
                    raise ValueError("Workflow history ended before its reported total")
                return records
            page += 1

    def pr(self, number):
        result = self.request("GET", f"/pulls/{number}")
        if result["state"] != "open":
            raise ValueError("PR must be open")
        return {"base": result["base"]["sha"], "head": result["head"]["sha"]}

    def publish(self, plan, body, run_id):
        current = self.pr(plan["pr"])
        if current != {"base": plan["base"], "head": plan["head"]}:
            raise ValueError("Stale report cannot replace the current PR summary")
        comments = self.pages(f"/issues/{plan['pr']}/comments")
        matches = [c for c in comments if c["user"]["login"] == "github-actions[bot]"
                   and c["body"].startswith(MARKER)]
        if len(matches) > 1:
            raise ValueError("Multiple owned summaries; refusing an ambiguous update")
        stamp = f"\n<!-- skill-eval-writer:{run_id} -->"
        if matches:
            previous = re.search(r"<!-- skill-eval-writer:(\d+) -->", matches[0]["body"])
            if previous and int(previous[1]) > run_id:
                raise ValueError("Older workflow cannot replace a newer summary")
        # A second live read covers head changes while fetching the comment pages.
        if self.pr(plan["pr"]) != current:
            raise ValueError("PR changed before publication")
        if matches:
            return self.request("PATCH", f"/issues/comments/{matches[0]['id']}",
                                {"body": body + stamp})
        return self.request("POST", f"/issues/{plan['pr']}/comments", {"body": body + stamp})


class ArtifactRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, *args, **kwargs):
        redirected = super().redirect_request(request, *args, **kwargs)
        if redirected is not None:
            redirected.remove_header("Authorization")
        return redirected


def artifact_zip(api, run_id, name, now):
    artifacts = api.pages(f"/actions/runs/{run_id}/artifacts", "artifacts")
    selected = [a for a in artifacts if a["name"] == name]
    if len(selected) != 1:
        raise ValueError("Evidence artifact missing or ambiguous")
    artifact = selected[0]
    if artifact["size_in_bytes"] > MAX_ARCHIVE:
        raise ValueError("Artifact too large")
    from datetime import datetime

    expires = datetime.fromisoformat(artifact["expires_at"].replace("Z", "+00:00")).timestamp()
    if artifact["expired"] or now >= expires:
        return None, min(expires, now)
    raw = api.request("GET", f"/actions/artifacts/{artifact['id']}/zip", binary=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as zipped:
        if zipped.namelist() != ["results.zip"]:
            raise ValueError("Unexpected artifact envelope")
        member = zipped.infolist()[0]
        if member.file_size > MAX_ARCHIVE:
            raise ValueError("Oversized artifact payload")
        return zipped.read(member), expires


def publish_retained(api, output, source_run, writer_run, now):
    plan = compare.read_json(output / "pr-plan.json")
    run = api.request("GET", f"/actions/runs/{source_run}")
    if (run["path"] != WORKFLOW or run["event"] != "workflow_dispatch"
            or run["display_title"] != run_title(plan["pr"], fingerprint(plan))
            or run["head_sha"] != plan["version"]
            or run["status"] != "completed" and source_run != writer_run):
        raise ValueError("Untrusted or mismatched execution workflow")
    data, expires = artifact_zip(api, source_run, "skill-eval-results", now)
    results = []
    if data is not None:
        import_results(data, output)
        results = reports(output)
    url = f"https://github.com/{plan['repository']}/actions/runs/{source_run}"
    return api.publish(plan, summary(plan, results, url, expires, now), writer_run)


def main():
    parser = argparse.ArgumentParser(description="Revision-bound skill PR integration")
    parser.add_argument("mode", choices=("prepare", "authorize", "execute", "pack", "publish"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    event = compare.read_json(Path(os.environ["GITHUB_EVENT_PATH"]))
    inputs = event.get("inputs", {})
    pr = int(inputs.get("pr") or event["pull_request"]["number"])
    repository = os.environ["GITHUB_REPOSITORY"]
    run_id = int(os.environ["GITHUB_RUN_ID"])
    if args.mode == "execute":
        execute(output, compare.read_json(output / "approval.json"))
        return
    if args.mode == "pack":
        result_archive(output)
        return
    api = GitHub(repository, os.environ["GITHUB_TOKEN"])
    if args.mode == "prepare":
        current = api.pr(pr)
        subprocess.run(["git", "fetch", "--no-tags", "--no-recurse-submodules",
                        "https://github.com/" + repository + ".git", current["base"],
                        f"refs/pull/{pr}/head"], cwd=ROOT, check=True)
        version = git(ROOT, "rev-parse", "HEAD").decode().strip()
        plan = prepare(ROOT, MAPPING, {"repository": repository, "pr": pr,
                       "version": version, **current}, output)
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as handle:
            handle.write(f"pr={pr}\nplan_sha256={fingerprint(plan)}\n")
        return
    plan = compare.read_json(output / "pr-plan.json")
    if args.mode == "authorize":
        actor = os.environ["GITHUB_ACTOR"]
        permission = api.request("GET", f"/collaborators/{actor}/permission")["permission"]
        request = {key: inputs[key] for key in ("plan_sha256", "version", "base", "head")}
        request["budget"] = json.loads(inputs["budget"])
        approval = authorize(plan, request, actor, permission, api.pr(pr))
        runs = api.pages("/actions/workflows/skill-eval-pr.yml/runs?event=workflow_dispatch",
                         "workflow_runs", require_complete=True)
        claim(plan, runs, run_id, int(os.environ["GITHUB_RUN_ATTEMPT"]))
        write_json(output / "approval.json", approval)
        return
    if inputs.get("action") in ("execute", "publish"):
        if inputs["action"] == "publish" and not inputs.get("source_run"):
            raise ValueError("Publish-only retry requires the original execution run ID")
        receipt = publish_retained(api, output, int(inputs.get("source_run") or run_id),
                                   run_id, time.time())
    else:
        now = time.time()
        url = f"https://github.com/{repository}/actions/runs/{run_id}"
        body = summary(plan, [], url, now + RETENTION_DAYS * 86400, now)
        receipt = api.publish(plan, body, run_id)
    print(receipt["html_url"])


if __name__ == "__main__":
    main()
