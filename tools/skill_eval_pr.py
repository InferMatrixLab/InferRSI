import argparse
import hashlib
import html
import io
import json
import os
import re
import shutil
import stat
import subprocess
import time
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError

from inferrsi.infra.artifacts import sha256, write_json
from inferrsi.model.anthropic_agent import money, reservation
from tools import skill_eval_compare as compare
from tools.check_knowledge_model_policy import GitHubHTTPError
from tools.skill_eval_feedback import (
    bound_results,
    code,
    comparison_lines,
    evidence_binding_lines,
    json_for_code,
    projection,
    safe_text,
)

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


def prepare(repo, mapping_path, identity, output, *, provider=None, planning_blocked=None):
    # Read only trusted configuration and raw Git objects, never PR Python or graders.
    for key in ("base", "head", "version"):
        if not re.fullmatch(SHA, identity[key]):
            raise ValueError("Expected immutable revision: " + key)
    mapping = compare.read_json(mapping_path)
    if provider is not None:
        required = {"model", "client", "pricing", "spend_limit"}
        if (not isinstance(provider, dict) or not required <= provider.keys()
                or provider.keys() - required - {"limits"}):
            raise ValueError("Unknown or incomplete provider configuration")
        overrides = provider.get("limits", {})
        if "limits" in provider and (
                not isinstance(overrides, dict) or set(overrides) != {"token_stop_new_trials"}
                or type(overrides["token_stop_new_trials"]) is not int
                or overrides["token_stop_new_trials"] <= 0):
            raise ValueError("Provider limits support one positive integer token_stop_new_trials")
        reservation(provider["model"]["name"], provider["client"], provider["pricing"],
                    provider["spend_limit"], 1, now=0)
        mapping.update({key: provider[key] for key in required})
        mapping["limits"] = {**mapping["limits"], **overrides}
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
        # The mapping is trusted repository data, but a path is a path: apply the
        # safe-ID rule here, before building any output path from it.
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", item["skill"]):
            raise ValueError("Unsafe skill ID in the PR case mapping")
        if planning_blocked is not None:
            comparisons.append({"skill": item["skill"],
                                "unsupported": "Mapping-only scope; provider unavailable"})
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
        if "adapter" in item:
            # Trusted mapping chooses an explicit typed contract; compare validates it.
            # Do not infer a diagnostic adapter from arbitrary PR file contents.
            config["adapter"] = item["adapter"]
        if provider is not None:
            config.update({key: provider[key] for key in ("client", "pricing", "spend_limit")})
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
    if planning_blocked is not None:
        plan["execution_blocked"] = planning_blocked
        plan["model"] = {"name": "unconfigured", "effort": "not_applicable"}
    if provider is not None:
        plan["provider_config"] = provider
        if plan["estimated_calls"]:
            try:
                plan["reservation"] = provider_reservation(plan, now=0)
            except ValueError:
                # Free scope reporting must survive a refused aggregate reservation.
                # Paid admission recomputes strict bounds and never splits this plan.
                plan["execution_blocked"] = "Complete paid reservation exceeds approved bounds"
    write_json(output / "pr-plan.json", plan)
    return plan


def provider_reservation(plan, *, now=None):
    provider = plan["provider_config"]
    selected = [c for c in plan["comparisons"] if "plan_sha256" in c]
    if sum(c["calls"] for c in selected) != plan["estimated_calls"] or not selected:
        raise ValueError("Provider plan requires supported paired trials")
    allocated = [reservation(provider["model"]["name"], provider["client"],
                              provider["pricing"], provider["spend_limit"], c["calls"], now=now)
                 for c in selected]
    amount = sum(money(c["amount"]) for c in allocated)
    if amount > money(provider["spend_limit"]["amount"]):
        raise ValueError("All-comparison reservation exceeds approved total")
    return {**allocated[0], "amount": str(amount),
            "requests": sum(c["requests"] for c in allocated)}


def budget(plan):
    value = {"estimated_calls": plan["estimated_calls"], "limits_per_comparison": plan["limits"],
             "comparisons": sum("plan_sha256" in c for c in plan["comparisons"])}
    if "provider_config" in plan:
        value.update(reservation=plan.get("reservation"),
                     provider_config_sha256=fingerprint(plan["provider_config"]))
    return value


def execution_id(plan):
    return "skill-eval-" + fingerprint(plan)


def run_title(pr, digest):
    return f"skill-eval execute PR {pr} plan {digest}"


def authorize(plan, request, actor, permission, current):
    if plan.get("execution_blocked"):
        raise ValueError("Planning-only plan is blocked from paid execution")
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
    if "provider_config" in plan and provider_reservation(plan) != plan["reservation"]:
        raise ValueError("Provider reservation changed")
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
    if plan.get("execution_blocked"):
        raise ValueError("Planning-only plan is blocked from paid execution")
    if approval["execution_id"] != execution_id(plan):
        raise ValueError("Approval belongs to another plan")
    if "provider_config" in plan:
        if client is not None:
            raise ValueError("A paid provider plan cannot substitute an injected client")
        if provider_reservation(plan) != plan["reservation"]:
            raise ValueError("Provider reservation changed")
        for item in plan["comparisons"]:
            if "plan_sha256" in item:
                frozen = compare.load_plan(output / item["skill"])
                provider = compare.provider_client(frozen)
                provider.require_live_readiness(len(frozen["schedule"]))
                provider.environment()  # Before the exclusive local consumption record.
    # Exclusive creation also protects local/offline callers sharing retained storage.
    with (output / "execution-claim.json").open("x", encoding="utf-8") as handle:
        handle.write(canonical(approval))
    for item in plan["comparisons"]:
        if "plan_sha256" in item:
            # Artifact downloads omit empty directories required by the executor.
            (output / item["skill"] / "results").mkdir(exist_ok=True)
            result = compare.execute(output / item["skill"], item["plan_sha256"], client=client,
                                     stop_on_unknown_usage="provider_config" in plan,
                                     require_request_authorization=client is None)
            if "provider_config" in plan and result["status"]["execution_state"] != "completed":
                break


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
        # Validate archive spelling before ZipInfo's platform-dependent normalization.
        names = [m.orig_filename for m in members]
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
        # Retry imports are snapshots, not overlays: omitted files must remain missing,
        # never inherited from a previous successful download in the same directory.
        for item in plan["comparisons"]:
            if "plan_sha256" in item:
                folder = output / item["skill"] / "results"
                if folder.exists():
                    shutil.rmtree(folder)
                folder.mkdir()
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
        status = result.get("status")
        if not isinstance(status, dict) or not isinstance(status.get("execution_state"), str):
            raise ValueError("Invalid retained execution status shape")
        tasks = {t["id"]: t for t in compare.read_json(directory / "plan/tasks.json")}
        # Recheck the exact built-in adapter with trusted code, not artifact verify.py.
        compare.verify_retained_grader(
            compare.load_plan(directory),
            [p[r] for p in result["pairs"] for r in compare.ROLES] + result["discovery"],
            tasks)
        frozen = compare.load_plan(directory)
        attach_feedback(result, {"adapter": frozen.get("adapter", "audit"),
                                 "tasks": tasks, "exam": frozen["exam"],
                                 "schema": compare.read_json(directory / "plan/schema.json")})
        results.append(result)
    return results


def attach_feedback(result, context):
    """Project only an exact current builtin exam, including historical reports.

    A historical report's trusted result remains intact when its grader has
    changed; explanations are unavailable rather than inferred under new rules.
    """
    diagnostic = compare.diagnostic
    adapter = context["adapter"]
    if adapter == diagnostic.ADAPTER:
        verifier, schema, path = diagnostic.verify, diagnostic.SCHEMA, Path(diagnostic.__file__)
    elif adapter == "audit":
        verifier, schema = compare.verify, compare.SCHEMA
        path = ROOT / "tools/skill_eval_verifier.py"
    else:
        return
    trials = [p[r] for p in result["pairs"] for r in compare.ROLES] + result["discovery"]
    for trial in trials:
        trial.pop("feedback", None)
    if context["exam"]["grader"] != sha256(path) or context["schema"] != schema:
        return
    tasks = context["tasks"]
    if isinstance(tasks, list):
        tasks = {task["id"]: task for task in tasks}
    for trial in trials:
        if trial.get("grader_trust") != "reverified" or trial["verdict"] not in ("PASS", "FAIL"):
            continue
        answer = json.loads(trial["output"])
        checks = verifier(tasks[trial["task_id"]], answer)
        if checks != trial["checks"] or checks["passed"] != (trial["verdict"] == "PASS"):
            raise ValueError("Historical grading disagrees with the current identical grader")
        trial["feedback"] = projection(adapter, tasks[trial["task_id"]], answer, checks)


def publish_historical(api, pr, source_run, writer_run, *, now, output=None):
    """Explicit no-execution retry; retain the original plan's complete identity."""
    from tools.skill_eval_retained import retained_reports

    revision = git(ROOT, "rev-parse", "HEAD").decode().strip()
    retained = retained_reports(api, pr, source_run, trusted_repo=ROOT,
                                renderer_revision=revision, now=now)
    plan, results = retained["plan"], retained["reports"]
    for result in results:
        attach_feedback(result, retained["contexts"][result["skill"]])
    from tools.skill_eval_auto import report_control

    body = summary(plan, results, retained["evidence_url"], retained["expires_at"], now,
                   evidence_state="available", execution_control=report_control(api, plan))
    body += ("\n\nPresentation implementation: `" + revision + "`. "
             "Original execution plan and frozen verifier bindings are retained; "
             "this report-only refresh starts no model execution or budget reservation.")
    if output is not None:
        write_json(output / "pr-plan.json", plan)
        write_json(output / "report-renderer.json", {"renderer_revision": revision,
                   "source_run": source_run, "original_plan_sha256": fingerprint(plan)})
        for result in results:
            directory = output / result["skill"]
            write_json(directory / "report.json", result)
            (directory / "report.md").write_text(body, encoding="utf-8")
    return api.publish(plan, body, writer_run)


def review_guidance(plan, results, *, evidence_state):
    """Advisory only, over trusted regenerated reports for this exact plan.

    Counts are presentation, not authority: inspect every scheduled pair and
    comparison binding so neither a fix nor another comparison hides a gap.
    """
    reasons, observations = [], []
    selected = [item for item in plan["comparisons"] if "plan_sha256" in item]
    if evidence_state != "available":
        reasons.append("Retained evidence is " + evidence_state + ".")
    if not selected:
        reasons.append("No supported comparison cases were selected.")
    gaps = [entry for entry in plan["coverage"] if entry["coverage"] != "covered"]
    if gaps:
        reasons.append("Uncovered/unsupported scope needs a case or explicit reviewer disposition.")
    regression = False
    seen = set()
    for item in selected if evidence_state == "available" else []:
        matches = [result for result in results if result.get("skill") == item["skill"]]
        if len(matches) != 1:
            reasons.append(item["skill"] + ": missing or ambiguous comparison report.")
            continue
        result = matches[0]
        seen.add(item["skill"])
        bound = (result.get("plan_sha256") == item["plan_sha256"]
                 and result.get("exam") == item["exam"]
                 and all(result.get("arms", {}).get(role, {}).get("git_revision") == plan[key]
                         for role, key in (("baseline", "base"), ("candidate", "head"))))
        if not bound or evidence_state != "available":
            if not bound:
                reasons.append(item["skill"] + ": stale or mismatched revision/plan/exam.")
            continue
        status = result.get("status")
        if not isinstance(status, dict) or status.get("execution_state") != "completed":
            reasons.append(item["skill"] + ": execution is incomplete or unverified.")
        expected = {(case["id"], repeat) for case in item["cases"]
                    if case["split"] != "discovery"
                    for repeat in range(1, plan["limits"]["repeats"] + 1)}
        pairs = result.get("pairs", [])
        actual = [(pair["case_id"], pair["repeat"]) for pair in pairs]
        if not expected or set(actual) != expected or len(actual) != len(expected):
            reasons.append(item["skill"] + ": incomplete paired-case coverage.")
        for pair in pairs:
            outcome = pair["outcome"]
            observations.append({"skill": item["skill"], "case": pair["case_id"],
                                 "repeat": pair["repeat"], "outcome": outcome})
            if outcome == "regression":
                regression = True
            elif outcome in ("missing_pair", "inconclusive"):
                reasons.append(item["skill"] + ": " + outcome + "; obtain valid paired evidence.")
            elif outcome == "unchanged_incorrect":
                reasons.append(item["skill"]
                               + ": existing failure remains; fix or explicitly disposition it.")
            elif outcome not in ("fix", "unchanged_correct"):
                reasons.append(item["skill"] + ": unsupported outcome.")
        if any(trial.get("verdict") not in ("PASS", "FAIL")
               for trial in result.get("discovery", [])):
            reasons.append(item["skill"] + ": discovery evidence is incomplete or erroneous.")
    if evidence_state == "available" and len(results) != len(seen):
        reasons.append("Unexpected or duplicate comparison reports cannot support guidance.")
    disposition = ("address observed regression" if regression else
                   "obtain missing evidence" if reasons else
                   "covered evidence supports proceeding to independent review")
    if regression:
        reasons.insert(0, "Fixes do not cancel observed regressions; "
                       "correct the failing candidate cases.")
    return {"disposition": disposition, "reasons": list(dict.fromkeys(reasons)),
            "observations": observations,
            "evidence_state": evidence_state, "plan_sha256": fingerprint(plan)}


def summary(plan, results, evidence_url, expires_at, now, *, evidence_state=None,
            execution_control=None):
    expired = now >= expires_at
    evidence_state = ("expired" if expired else evidence_state or
                      ("available" if results else "planned / unexecuted"))
    guidance = review_guidance(plan, results, evidence_state=evidence_state)
    lines = [MARKER, "## Skill evaluation"]
    lines += comparison_lines(plan, results, evidence_state)
    if plan.get("execution_blocked"):
        lines += ["", "Paid execution blocked: " + safe_text(plan["execution_blocked"]) + ". "
                  "New execution only: this does not invalidate available retained results. "
                  "No alternate provider/model is selected."]
    if execution_control is not None:
        lines += ["", "Automatic execution / cumulative PR budget: `"
                  + canonical(execution_control) + "`", ""]
    lines += ["### Advisory: " + guidance["disposition"],
              "Retained evidence availability: **" + evidence_state + "**. "
              "No approval or merge authorization is issued."]
    lines.extend("- " + safe_text(reason) for reason in guidance["reasons"][:6])
    if len(guidance["reasons"]) > 6:
        lines += [f"- {len(guidance['reasons']) - 6} additional reasons in details below."]
    lines += [""]
    counts = {k: 0 for k in ("fix", "regression", "unchanged_correct", "unchanged_incorrect",
                             "inconclusive", "missing_pair")}
    if expired or evidence_state == "expired":
        lines += ["**EXPIRED: retained evidence is no longer verifiable.**"]
    elif evidence_state in ("missing", "invalid"):
        lines += ["**INSUFFICIENT EVIDENCE: retained artifacts are " + evidence_state + ".**"]
    elif results:
        for _, result in bound_results(plan, results):
            for key in counts:
                counts[key] += result["counts"][key]
        lines += ["**RETAINED RESULTS**", "", "Outcomes: `" + canonical(counts) + "`",
                  "Discovery is reported separately in retained evidence."]
    else:
        counts["missing_pair"] = sum(
            sum(c["split"] != "discovery" for c in item["cases"]) * plan["limits"]["repeats"]
            for item in plan["comparisons"] if "plan_sha256" in item)
        lines += ["**PLANNED: execution is not authorized by knowing this hash.**",
                  "Outcomes: `" + canonical(counts) + "`",
                  "Earlier revision results are stale for this plan."]
    gaps = [c for c in plan["coverage"] if c["coverage"] != "covered"]
    selected = sum("plan_sha256" in item for item in plan["comparisons"])
    lines += ["", f"Selected comparisons: **{selected}** · Estimated task calls: "
              f"**{plan['estimated_calls']}**.",
              f"Uncovered/unsupported changes: **{len(gaps)}**. Gaps never count as passes.", "",
              "Applicable only while these revisions and inputs match the current PR.",
              "Paid execution requires trusted label authorization and cumulative PR reservation. "
              "Unknown accounting blocks new paid calls; planning is not execution.",
              "Pipeline evidence only; offline fixed outputs do not establish skill efficacy.",
              f"[Evidence and logs]({evidence_url}) · Retention: {RETENTION_DAYS} days.",
              f"Outcomes are historical; verifiable only before Unix time `{int(expires_at)}` "
              "while the linked artifact is available. Expired evidence is unverified.", "",
              "<details>",
              "<summary>Plan bindings, budget, frozen exam and advisory details</summary>", "",
              "Unchanged-correct is valid neutral evidence, not incremental benefit.",
              "Content/source review and authorship admission remain separate.",
              "Trusted regrading checks retained answers, not model/hardware provenance or "
              "a hostile executor; this is not an efficacy certification.",
              *["- " + safe_text(reason) for reason in guidance["reasons"][6:26]],
              "", "Per-case outcomes (discovery excluded; regressions and gaps first):",
              "```json", json_for_code(sorted(guidance["observations"], key=lambda item:
                  (item["outcome"] not in ("regression", "inconclusive", "missing_pair",
                                           "unchanged_incorrect"), item["skill"]))[:20]), "```",
              f"Showing at most 20 of {len(guidance['observations'])} pairs; "
              "the evidence link contains all outcomes, including omitted regressions/gaps.",
              "",
              *[line for line in evidence_binding_lines(plan, results, evidence_state)],
              f"Plan SHA-256: `{fingerprint(plan)}`",
              f"Base: `{plan['base']}` · Head: `{plan['head']}`",
              f"Trusted implementation: `{plan['version']}`", "",
              "Model/settings: `" + canonical(plan["model"]) + "`",
              "Budget: `" + canonical(budget(plan)) + "`", "",
              "| Skill | Comparison | Cases | Estimated calls |",
              "| --- | --- | --- | --- |"]
    for item in plan["comparisons"][:50]:
        if "plan_sha256" in item:
            cases = ", ".join(safe_text(c["id"], 128) + " (" + safe_text(c["split"], 24) + ")"
                              for c in item["cases"][:20])
            lines.append(f"| {code(item['skill'])} | {code(item['mode'])} | {cases} | "
                         f"{item['calls']} |")
            lines.append("\nFrozen exam hashes: `" + canonical(item["exam"]) + "`\n")
        else:
            lines.append(f"| {code(item['skill'])} | unsupported snapshot | — | 0 |")
    if "provider_config" in plan:
        lines += ["", "Provider/settings: `" + canonical(plan["provider_config"]) + "`"]
    lines += ["", "</details>", "", "<details>",
              f"<summary>Uncovered / unsupported paths ({len(gaps)})</summary>", ""]
    # A collapsed HTML container still requires data escaping for untrusted Git paths.
    for gap in gaps[:100]:
        lines.append("- " + safe_text(gap["coverage"], 24) + ": <code>"
                     + html.escape(canonical(gap["path"][:1024])).replace("@", "&#64;") + "</code>")
    if len(gaps) > 100:
        lines.append("Additional paths omitted; see retained evidence.")
    if not gaps:
        lines.append("(none)")
    lines += ["", "</details>"]
    return "\n".join(lines)


def comment_permission_requirements(headers):
    """Parse bounded server-advertised requirements, never granted permissions."""
    if headers is None:
        return {"status": "absent"}
    name = "X-Accepted-GitHub-Permissions"
    get_all = getattr(headers, "get_all", None)
    if callable(get_all):
        values = get_all(name, [])
        if type(values) is not list:
            return {"status": "unavailable"}
        if not values:
            return {"status": "absent"}
        if len(values) != 1:
            return {"status": "unavailable"}
        raw = values[0]
    else:
        missing = object()
        raw = headers.get(name, missing)
        if raw is missing:
            return {"status": "absent"}
    # ASCII makes the character bound a byte bound. Never parse a truncated prefix.
    if type(raw) is not str or len(raw) > 256 or not raw.isascii():
        return {"status": "unavailable"}
    # Commas join requirements; semicolons separate alternative permission sets.
    alternatives = raw.split(";")
    if len(alternatives) > 4:
        return {"status": "unavailable"}
    allowed = {"issues": ("read", "write"), "pull_requests": ("read", "write"),
               "contents": ("read", "write"), "metadata": ("read",)}
    sets, seen = [], set()
    for alternative in alternatives:
        entries = alternative.split(",")
        if len(entries) > 4:
            return {"status": "unavailable"}
        group = {}
        for entry in entries:
            match = re.fullmatch(r"[ \t]*([a-z_]+)[ \t]*=[ \t]*(read|write)[ \t]*", entry)
            if not match:
                return {"status": "unavailable"}
            permission, level = match.groups()
            if (permission not in allowed or level not in allowed[permission]
                    or permission in group):
                return {"status": "unavailable"}
            group[permission] = level
        identity = tuple(sorted(group.items()))
        if identity in seen:
            return {"status": "unavailable"}
        seen.add(identity)
        sets.append(group)
    return {"status": "available", "sets": sets}


def publication_http_error(error, method, path):
    """Reuse the existing allowlist formatter, without its client's retry behavior."""
    code = error.code if type(error.code) is int and 100 <= error.code <= 599 else 0
    routes = (
        (r"/pulls/[0-9]+", "/pulls/{number}"),
        (r"/issues/[0-9]+/comments", "/issues/{number}/comments"),
        (r"/issues/comments/[0-9]+", "/issues/comments/{id}"),
        (r"/actions/runs/[0-9]+", "/actions/runs/{id}"),
        (r"/actions/runs/[0-9]+/artifacts", "/actions/runs/{id}/artifacts"),
        (r"/actions/artifacts/[0-9]+/zip", "/actions/artifacts/{id}/zip"),
        (r"/actions/workflows/skill-eval-pr[.]yml/runs", "/actions/workflows/{workflow}/runs"),
        (r"/collaborators/[A-Za-z0-9_-]+/permission", "/collaborators/{actor}/permission"),
    )
    endpoint = next((label for pattern, label in routes
                     if re.fullmatch(pattern, path.split("?", 1)[0])), "<redacted>")
    context = {"method": method if method in ("GET", "POST", "PATCH") else "UNKNOWN",
               "endpoint": endpoint}
    try:
        try:
            # An extra byte detects truncation: a valid JSON prefix of an oversized body
            # must not establish a cause. Neither this body nor error URL/reason is logged.
            raw = error.read(8193)
            if not isinstance(raw, bytes) or len(raw) > 8192:
                raw = b""
        except Exception:
            raw = b""
        try:
            safe = HTTPError("", code, "", error.headers, io.BytesIO(raw))
            failure = GitHubHTTPError(safe)
        except Exception:
            # Diagnostics are best effort, including hostile headers and malformed JSON.
            # Always retain the original HTTP failure instead of failing in the formatter.
            failure = OSError("GitHub API " + json.dumps(
                {"http_status": code, "category": "unknown"}, sort_keys=True))
        permissions = ""
        if (method, endpoint) in (("POST", "/issues/{number}/comments"),
                                  ("PATCH", "/issues/comments/{id}")):
            try:
                permissions = " accepted_permissions=" + canonical(
                    comment_permission_requirements(error.headers))
            except Exception:
                permissions = ' accepted_permissions={"status":"unavailable"}'
        failure.args = (str(failure) + " request=" + canonical(context) + permissions,)
        return failure
    finally:
        try:
            error.close()
        except Exception:
            pass


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
        try:
            opener = urllib.request.build_opener(ArtifactRedirect())
            with opener.open(request, timeout=60) as response:
                raw = response.read(MAX_ARCHIVE + 1)
        except HTTPError as error:
            # Suppress the unsafe urllib reason/redirect URL in rendered tracebacks, while
            # retaining the original exception as context for in-process inspection.
            raise publication_http_error(error, method, path) from None
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


class MissingEvidence(ValueError):
    """A known absent artifact, not an API access or integrity failure."""


def artifact_download(api, run_id, name, now):
    artifacts = api.pages(f"/actions/runs/{run_id}/artifacts", "artifacts")
    selected = [a for a in artifacts if a["name"] == name]
    if not selected:
        raise MissingEvidence("Evidence artifact missing")
    if len(selected) != 1:
        raise ValueError("Evidence artifact ambiguous")
    artifact = selected[0]
    if artifact["size_in_bytes"] > MAX_ARCHIVE:
        raise ValueError("Artifact too large")
    from datetime import datetime

    expires = datetime.fromisoformat(artifact["expires_at"].replace("Z", "+00:00")).timestamp()
    if artifact["expired"] or now >= expires:
        return None, min(expires, now)
    raw = api.request("GET", f"/actions/artifacts/{artifact['id']}/zip", binary=True)
    if len(raw) > MAX_ARCHIVE:
        raise ValueError("Oversized artifact download")
    return raw, expires


def artifact_zip(api, run_id, name, now):
    raw, expires = artifact_download(api, run_id, name, now)
    if raw is None:
        return None, expires
    with zipfile.ZipFile(io.BytesIO(raw)) as zipped:
        if zipped.namelist() != ["results.zip"]:
            raise ValueError("Unexpected artifact envelope")
        member = zipped.infolist()[0]
        if member.file_size > MAX_ARCHIVE:
            raise ValueError("Oversized artifact payload")
        return zipped.read(member), expires


def source_plan_expiry(api, run_id, plan, now):
    """Bind automatic evidence to the trusted planner artifact from this source run.

    The run's authenticated workflow identity is checked by the caller. Neither a
    result's self-reported head nor the PR-only automatic run title is provenance.
    Read data only; never extract or execute any file from the planning archive.
    """
    raw, expires = artifact_download(api, run_id, "skill-eval-plan", now)
    if raw is None:
        return expires
    with zipfile.ZipFile(io.BytesIO(raw)) as zipped:
        members = zipped.infolist()
        names = [m.orig_filename for m in members]
        if (len(members) > 10000 or len(names) != len(set(names))
                or sum(m.file_size for m in members) > MAX_ARCHIVE
                or names.count("pr-plan.json") != 1):
            raise ValueError("Invalid source planning archive")
        for item, name in zip(members, names):
            path = PurePosixPath(name)
            mode = item.external_attr >> 16
            if (path.is_absolute() or ".." in path.parts or "\\" in name
                    or stat.S_ISLNK(mode)
                    or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                raise ValueError("Unsafe source planning archive member")
        member = members[names.index("pr-plan.json")]
        mode = member.external_attr >> 16
        if (member.file_size > 4_000_000 or stat.S_ISLNK(mode)
                or stat.S_IFMT(mode) not in (0, stat.S_IFREG)):
            raise ValueError("Invalid source plan member")
        original = json.loads(zipped.read(member))
    if fingerprint(original) != fingerprint(plan):
        raise ValueError("Source execution plan does not match current PR plan")
    return expires


def publish_retained(api, output, source_run, writer_run, now):
    plan = compare.read_json(output / "pr-plan.json")
    run = api.request("GET", f"/actions/runs/{source_run}")
    trusted_source = (run["event"] == "workflow_dispatch"
                      and run["display_title"] == run_title(plan["pr"], fingerprint(plan)))
    trusted_source |= (run["event"] == "pull_request_target"
                       and run["display_title"] == f"skill-eval plan or publish PR {plan['pr']}")
    if not trusted_source:
        raise ValueError("Untrusted or mismatched execution workflow")
    repository = api.request("GET", "")
    # Actions run head_sha names the PR head for pull_request_target, not the
    # trusted checkout. Its immutable source plan authenticates version separately.
    expected_sha = plan["head"] if run["event"] == "pull_request_target" else plan["version"]
    if (run["id"] != source_run or run["path"] != WORKFLOW or not trusted_source
            or repository.get("full_name") != plan["repository"]
            or type(repository.get("id")) is not int
            or run.get("repository", {}).get("id") != repository["id"]
            or run.get("repository", {}).get("full_name") != plan["repository"]
            or run["head_sha"] != expected_sha
            or run["status"] != "completed" and source_run != writer_run):
        raise ValueError("Untrusted or mismatched execution workflow")
    evidence_state = "available"
    data, expires = None, now + RETENTION_DAYS * 86400
    try:
        if run["event"] == "pull_request_target":
            expires = source_plan_expiry(api, source_run, plan, now)
        if now < expires:
            data, result_expiry = artifact_zip(api, source_run, "skill-eval-results", now)
            expires = min(expires, result_expiry)
    except MissingEvidence:
        evidence_state = "missing"
    except (ValueError, KeyError, TypeError, zipfile.BadZipFile):
        evidence_state = "invalid"
    results = []
    if data is not None:
        try:
            import_results(data, output)
            results = reports(output)
        except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile):
            # Never expose artifact-controlled exception text or reuse old counts.
            evidence_state = "invalid"
    url = f"https://github.com/{plan['repository']}/actions/runs/{source_run}"
    from tools.skill_eval_auto import report_control
    return api.publish(plan, summary(plan, results, url, expires, now,
                                     evidence_state=evidence_state,
                                     execution_control=report_control(api, plan)), writer_run)


def main():
    parser = argparse.ArgumentParser(description="Revision-bound skill PR integration")
    parser.add_argument("mode", choices=("prepare", "authorize", "execute", "pack",
                                        "publish", "control"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    event = compare.read_json(Path(os.environ["GITHUB_EVENT_PATH"]))
    inputs = event.get("inputs", {})
    if inputs.get("action") == "plan" and args.mode not in ("prepare", "publish"):
        raise ValueError("Plan-only dispatch supports prepare and publish only")
    pr = int(inputs.get("pr") or event["pull_request"]["number"])
    repository = os.environ["GITHUB_REPOSITORY"]
    run_id = int(os.environ["GITHUB_RUN_ID"])
    if inputs.get("action") == "execute":
        raise ValueError("Legacy paid dispatch is blocked; use the audited label controller")
    if args.mode == "control":
        from tools.skill_eval_auto import controlled_execute
        api = GitHub(repository, os.environ["GITHUB_TOKEN"])
        controlled_execute(api, output, run_id=run_id,
                           attempt=int(os.environ["GITHUB_RUN_ATTEMPT"]))
        return
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
        from tools.skill_eval_auto import CONFIG, configuration, live_label
        config, config_blocked = None, None
        try:
            config = configuration(CONFIG, now=0)
        except FileNotFoundError:
            config_blocked = "Trusted automatic configuration is missing"
        except (OSError, ValueError, KeyError, TypeError, ArithmeticError):
            config_blocked = "Trusted automatic configuration is invalid or unreadable"
        provider = config["provider"] if config else None
        # An explicitly requested manual plan is not an automatic provider fallback.
        if config is None and inputs.get("action") == "plan" and inputs.get("provider_config"):
            provider = json.loads(inputs["provider_config"])
        plan = prepare(ROOT, MAPPING, {"repository": repository, "pr": pr,
                       "version": version, **current}, output, provider=provider,
                       planning_blocked=config_blocked if provider is None else None)
        candidate, reason = False, (config_blocked or
                                   "Trusted provider configuration and audited PR genesis required")
        if config:
            try:
                configuration(CONFIG)
            except (OSError, ValueError, KeyError, TypeError, ArithmeticError):
                reason = "Trusted automatic configuration or pricing is expired or invalid"
            else:
                try:
                    from tools.skill_eval_auto import daily_store, eligible, ledger_store
                    eligible(api, plan, config)
                    live_label(api, plan, config)
                    store, key = ledger_store(api, config, pr)
                    store.read_verified(key)
                    global_store, global_key = daily_store(api, config)
                    global_store.read_verified(global_key).ledger.require_active()
                    candidate = True
                    reason = "Eligible; durable reservation required before execution"
                except (ValueError, KeyError, TypeError):
                    reason = "Blocked: label/operator, suitability, budget or audited ledger"
        write_json(output / "control-status.json", {"eligible": candidate, "reason": reason})
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as handle:
            handle.write(f"auto_candidate={str(candidate).lower()}\n")
            handle.write(f"pr={pr}\nplan_sha256={fingerprint(plan)}\n")
            handle.write("client_kind=" + (plan["provider_config"]["client"]["kind"]
                                         if "provider_config" in plan else "codex") + "\n")
        return
    if args.mode == "publish" and inputs.get("action") == "publish":
        if not inputs.get("source_run"):
            raise ValueError("Publish-only retry requires the original execution run ID")
        receipt = publish_historical(api, pr, int(inputs["source_run"]), run_id,
                                     now=time.time(), output=output)
        print(receipt["html_url"])
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
    if inputs.get("action") == "publish" and not inputs.get("source_run"):
        raise ValueError("Publish-only retry requires the original execution run ID")
    from tools.skill_eval_auto import retained_source
    source = (int(inputs["source_run"]) if inputs.get("action") == "publish"
              else retained_source(api, plan))
    if source is None and os.environ.get("SKILL_EVAL_AUTO_SOURCE") == "true":
        source = run_id
    if source is not None:
        receipt = publish_retained(api, output, source, run_id, time.time())
    else:
        now = time.time()
        url = f"https://github.com/{repository}/actions/runs/{run_id}"
        from tools.skill_eval_auto import report_control
        body = summary(plan, [], url, now + RETENTION_DAYS * 86400, now,
                       execution_control=report_control(api, plan))
        receipt = api.publish(plan, body, run_id)
    print(receipt["html_url"])


if __name__ == "__main__":
    main()
