"""Inspect selected Issues and PRs without changing GitHub. See --help."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

if __package__:
    from .label_audit_evidence import CAPACITY, ISSUE_COMMENT, REPO, Evidence, actor, own_text
    from .label_cutover import AREAS, LABELS, handoff_gaps, instant, merge_event, replay_pr_kind
else:  # Direct invocation: python tools/audit_issue_labels.py
    from label_audit_evidence import CAPACITY, ISSUE_COMMENT, REPO, Evidence, actor, own_text
    from label_cutover import AREAS, LABELS, handoff_gaps, instant, merge_event, replay_pr_kind

PROGRESS_KINDS = {"kind:task", "kind:rfc", "kind:acceptance", "kind:tracking"}
ISSUE_KINDS = {row["name"] for row in LABELS if row["group"] == "kind"}
# First rule introducing single Issue kind: PR #299's merged timeline event.
KIND_RULE_AT = "2026-11-01T13:13:59Z"
WORDS = {"proposed", "active", "blocked", "delivered", "done"}
FIELD = re.compile(
    r"^[ \t]*(?:[-*] )?(?:\*\*)?(Current state|Decision needed|Next action):"
    r"(?:\*\*)?[ \t]*(.*?)[ \t]*$",
    re.I | re.M,
)


def get_json(path: str) -> dict | list:
    command = ["gh", "api", "--method", "GET", path]
    response = subprocess.run(command, capture_output=True, encoding="utf-8", timeout=90)
    if response.returncode:
        raise ValueError(f"GitHub GET {path}: {response.stderr.strip()}")
    return json.loads(response.stdout)


def paginated(path: str) -> list[dict]:
    rows = []
    page = 1
    while True:
        separator = "&" if "?" in path else "?"
        batch = get_json(f"{path}{separator}per_page=100&page={page}")
        rows.extend(batch)
        if len(batch) < 100:
            return rows
        page += 1


def progress_fields(body: str) -> dict:
    fields = {}
    for match in FIELD.finditer(own_text(body)):
        fields.setdefault(match[1].lower(), match[2])
    state = fields.get("current state", "").lstrip("`*").split()
    fields["word"] = re.split(r"[^a-z]", state[0].lower())[0] if state else ""
    return fields


def event_link(obj: dict, event: dict) -> str:
    return event.get("html_url") or f"{obj['html_url']}#event-{event['id']}"


def audit_object(
    obj: dict,
    events: list[dict],
    evidence: dict,
    snapshot: dict,
    cutover: dict | None,
    linked: dict | None = None,
) -> dict:
    """Evidence is a human interpretation of linked public records, never a write grant."""
    pr = "pull_request" in obj
    url = obj["html_url"]
    labels = sorted(v["name"] for v in obj["labels"])
    status = [v for v in labels if v.startswith("status:")]
    kinds = [v for v in labels if v.startswith("kind:")]
    result = {
        "number": obj["number"],
        "url": url,
        "type": "PR" if pr else "Issue",
        "labels": labels,
        "findings": [],
        "uninvited_standing_reviews": 0,
    }
    if pr:
        result["head"] = obj["head_sha"]

    def finding(code, detail, *, pending=False, add=(), remove=(), sources=()):
        result["findings"].append(
            {
                "code": code,
                "state": "pending" if pending else "advisory",
                "detail": detail,
                "add": list(add),
                "remove": list(remove),
                "sources": list(sources) or [url],
            }
        )

    proof = Evidence(obj, events, evidence, linked or {})
    source = proof.field
    for code, detail, pending, sources in proof.standing_reviews(pr):
        finding(code, detail, pending=pending, sources=sources)
        if code == "uninvited-standing-review":
            result["uninvited_standing_reviews"] += 1

    area_scope = source("area_scope")
    suggested = evidence.get("suggested_areas")
    valid_areas = isinstance(suggested, list) and all(
        isinstance(v, str) and v in AREAS for v in suggested
    )
    if area_scope and valid_areas and suggested:
        additions = sorted(set(suggested) - set(labels))
        if additions:
            finding(
                "area",
                "Cited responsibilities touched by this object.",
                add=additions,
                sources=[area_scope],
            )
    elif not any(v.startswith("area:") for v in labels):
        finding(
            "area", "Identify the changed responsibilities from the scope or diff.", pending=True
        )
    if pr:
        if status:
            finding("pr-status", "Use native PR progress.", remove=status)
        if cutover:
            report = replay_pr_kind(obj, events, snapshot, cutover)
            result["kind_history"] = report
            for gap in report["pending"]:
                finding("pr-kind-history", gap, pending=True, sources=[url, cutover["url"]])
            for addition in report["new_additions"]:
                finding(
                    "new-pr-kind",
                    f"Post-cutover addition of {addition['label']}.",
                    remove=[addition["label"]] if addition["label"] in kinds else [],
                    sources=[addition["url"], cutover["url"]],
                )
        elif kinds:
            finding(
                "pr-kind",
                "Historical kind observed; cutover evidence needed to date it.",
                pending=True,
            )
        return result

    if not kinds:
        selected = evidence.get("suggested_kind")
        if source("kind_choice") and selected in ISSUE_KINDS:
            finding(
                "issue-kind",
                "Creator's or delegate's cited purpose.",
                add=[selected],
                sources=[source("kind_choice")],
            )
        else:
            finding("issue-kind", "Creator or delegate selects the Issue's purpose.", pending=True)
    if len(kinds) > 1 and (len(kinds) > 2 or instant(obj["created_at"]) >= instant(KIND_RULE_AT)):
        finding(
            "issue-kind-count",
            "Resolve overlapping Issue kinds against the creator's purpose.",
            pending=True,
        )
    if len(status) > 1:
        finding("status-conflict", "Multiple scope decisions are displayed together.")
    proposed = "status:proposed" in status
    fields = progress_fields(obj.get("body") or "")
    word = fields["word"]
    closed = obj["state"] == "closed"
    if not closed and set(kinds) & PROGRESS_KINDS:
        if word not in WORDS or not fields.get("decision needed") or not fields.get("next action"):
            finding("progress-block", "Complete the three-line progress block.", pending=True)
        if word == "proposed" and not status:
            if source("open_question"):
                finding(
                    "open-decision",
                    "Named outstanding decision and owner.",
                    add=["status:proposed"],
                    sources=[source("open_question")],
                )
            else:
                finding(
                    "open-decision",
                    "Verify the open question and its decision owner.",
                    pending=True,
                )
        if "status:deferred" in status and word in WORDS - {"proposed"}:
            finding("deferred-progress", "A deferred decision uses proposed in the first line.")
        if word in {"active", "delivered"} and not source("scope_decision"):
            finding("accepted-scope", "Link the owner's accepted scope.", pending=True)
        if word in {"active", "delivered", "done"} and proposed:
            finding("progress-decision", "The progress word and undecided scope conflict.")
        if word == "delivered" and not source("delivery"):
            finding(
                "delivery",
                "Verify the agreed delivery artifacts and applicable merges.",
                pending=True,
            )
        if word == "blocked" and not source("blocker"):
            finding("blocker", "Verify the obstacle and who can unblock it.", pending=True)

    if proposed and closed:
        disposition = source("disposition")
        finding(
            "closed-proposed",
            "Check the recorded disposition and separate write authority.",
            pending=not disposition,
            remove=["status:proposed"] if disposition else [],
            sources=[url, disposition] if disposition else [url],
        )
    if proposed and not closed:
        decisions = [
            (source(key), target)
            for key, target in (
                ("whole_scope_acceptance", "status:accepted"),
                ("deferral", "status:deferred"),
            )
            if source(key)
        ]
        if len(decisions) > 1:
            finding(
                "scope-update",
                "Resolve which owner decision governs this scope.",
                pending=True,
                sources=[link for link, _ in decisions],
            )
        elif decisions:
            link, target = decisions[0]
            finding(
                "scope-update",
                "Recorded owner decision; verify write delegation separately.",
                add=[target],
                remove=["status:proposed"],
                sources=[link],
            )
            if not source("label_delegation"):
                finding(
                    "label-authority", "Verify the executor's applicable delegation.", pending=True
                )
    if any(v in status for v in ("status:accepted", "status:deferred")) and not source(
        "scope_decision"
    ):
        finding("status-decision", "Identify the applicable owner's decision.", pending=True)
    if closed or word == "done":
        cycles = [e for e in events if e.get("event") in {"reopened", "closed"}]
        last_open = next((e for e in reversed(cycles) if e["event"] == "reopened"), None)
        last_close = cycles[-1] if closed and cycles and cycles[-1]["event"] == "closed" else None

        def current_cycle(record):
            return not last_open or bool(
                record.get("created_at")
                and instant(record["created_at"]) > instant(last_open["created_at"])
            )

        links = []
        required = ["closure_summary", "goal_decision", "owner_authority"]
        role = evidence.get("closer_role")
        close_actor = actor(last_close or {})
        identity = proof.proof(evidence.get("closer_identity"))
        if (
            role not in {"owner", "delegate"}
            or not close_actor
            or (evidence.get("closer_login") or "").lower() != close_actor
            or not identity
            or not current_cycle(identity[1])
            or identity[2] not in own_text(identity[1].get("body") or "")
            or actor(identity[1]) != close_actor
            or not CAPACITY[role].search(identity[2])
            or (role == "owner" and CAPACITY["delegate"].search(identity[2]))
        ):
            role = None
        if role not in {"owner", "delegate"}:
            finding(
                "closure-identity",
                "Establish whether the actor was the owner or a delegate; "
                "a shared GitHub login is insufficient.",
                pending=True,
            )
        if role == "delegate":
            required.append("closure_delegation")
        for key in required:
            link = source(key)
            record = proof.local.get(link) or proof.linked.get(link) or {}
            if link and not current_cycle(record):
                link = None
            if not link:
                finding(key, f"Verify {key.replace('_', ' ')} for this open cycle.", pending=True)
            else:
                links.append(link)
        result["closure"] = {
            "role": role,
            "sources": links,
            "close_event": event_link(obj, last_close) if last_close else None,
        }
    return result


def read_file(path: Path | None) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path else {}


def linked_comments(root, evidence, obj, events):
    """Read explicitly cited parent comments only when a local record references them."""
    local = {e["html_url"]: e for e in events if e.get("html_url")}
    local[obj["html_url"]] = obj
    refs = list(evidence.values())
    for item in evidence.get("standing_reviews", []):
        if isinstance(item, dict):
            refs.extend(item.values())
    linked = {}
    for item in refs:
        if not isinstance(item, dict) or not isinstance(item.get("url"), str):
            continue
        url = item["url"]
        match = ISSUE_COMMENT.fullmatch(url)
        via = local.get(item.get("via")) or {}
        if match and url not in local and url not in linked and url in (via.get("body") or ""):
            record = get_json(f"{root}/issues/comments/{match[1]}")
            if record.get("html_url") == url:
                linked[url] = record
    return linked


def inspect(root, number, evidence, snapshot, cutover):
    path = f"{root}/issues/{number}"
    obj = get_json(path)
    if "pull_request" in obj:
        obj["head_sha"] = get_json(f"{root}/pulls/{number}")["head"]["sha"]
    events = paginated(f"{path}/timeline")
    linked = linked_comments(root, evidence, obj, events)
    after = get_json(path)
    if any(obj[k] != after[k] for k in ("updated_at", "body", "state", "labels")) or (
        "head_sha" in obj and get_json(f"{root}/pulls/{number}")["head"]["sha"] != obj["head_sha"]
    ):
        return {
            "number": number,
            "url": obj["html_url"],
            "pending": "Changed during inspection; retry.",
        }
    return audit_object(obj, events, evidence, snapshot, cutover, linked)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("numbers", type=int, nargs="*", help="Issue or PR numbers")
    parser.add_argument(
        "--recent-hours", type=int, help="inspect Issues and PRs updated in this window"
    )
    parser.add_argument(
        "--cutover-pr", type=int, help="the merged inspector PR; reads its actual merge event"
    )
    parser.add_argument("--snapshot", type=Path, help="original timestamp and per-object kind rows")
    parser.add_argument(
        "--evidence", type=Path, help="reviewed public evidence keyed by object number"
    )
    parser.add_argument("--handoff", type=Path, help="operator's freeze and dry-run record")
    args = parser.parse_args(argv)
    if bool(args.numbers) == (args.recent_hours is not None):
        parser.error("supply object numbers or one recent time window")
    if args.recent_hours is not None and args.recent_hours <= 0:
        parser.error("--recent-hours must be positive")
    if any(n <= 0 for n in args.numbers) or (args.cutover_pr is not None and args.cutover_pr <= 0):
        parser.error("use positive object numbers")
    if args.handoff and not args.cutover_pr:
        parser.error("--handoff needs --cutover-pr")
    root = f"repos/{REPO}"
    try:
        snapshot, evidence, cutover = read_file(args.snapshot), read_file(args.evidence), None
        if args.cutover_pr:
            pr = get_json(f"{root}/pulls/{args.cutover_pr}")
            if not pr["merged"] or pr["base"]["ref"] != "main":
                raise ValueError("the inspector PR must have merged into main")
            cutover = merge_event(
                paginated(f"{root}/issues/{args.cutover_pr}/timeline"),
                pr["merge_commit_sha"],
                pr["html_url"],
            )
        report = {"cutover": cutover, "objects": []}
        report["published_samples"] = {
            "original_2026_11_24": {"issues": 186, "prs": 323, "prs_with_kind": 176},
            "shanghai_30_complete_days": {"issues": 181, "prs": 319, "prs_with_kind": 184},
        }
        numbers = args.numbers
        if args.recent_hours:
            since = datetime.now(timezone.utc) - timedelta(hours=args.recent_hours)
            report["updated_since"] = since.isoformat()
            query = urlencode(
                {"state": "all", "since": since.isoformat(), "sort": "updated", "direction": "asc"}
            )
            numbers = [o["number"] for o in paginated(f"{root}/issues?{query}")]
        if args.handoff:
            report["handoff_pending"] = handoff_gaps(read_file(args.handoff), cutover)
        for number in dict.fromkeys(numbers):
            report["objects"].append(
                inspect(root, number, evidence.get(str(number), {}), snapshot, cutover)
            )
        print(json.dumps(report, indent=2, ensure_ascii=False))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(f"Could not complete read-only label inspection: {exc}", file=sys.stderr)
        return 1
    return 0  # Advisory findings can be nonempty.


if __name__ == "__main__":
    raise SystemExit(main())
