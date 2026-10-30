"""Deterministic advice over trusted artifact checks; never a judge or acceptance gate."""

import html

LIMITS = [
    "Artifact checks do not establish skill causality, hardware efficacy or whole-PR acceptance.",
    "Public development cases are not holdout evidence; "
    "source fidelity and uncovered claims still need review.",
]
CORRECTIONS = {
    "stream_error": "Reject error-bearing frames even when HTTP status is 200.",
    "missing_terminal": "Reject streams without a valid terminal frame.",
    "http_failure": "Reject unsuccessful HTTP responses before classifying completion.",
    "length_mismatch": "Require length completion to match the requested token count.",
    "stop_overflow": "Reject stop completions whose token count exceeds the request.",
    "duplicate_terminal": "Reject a second terminal frame.",
    "post_terminal_content": "Reject content after a terminal frame.",
    "boolean_count": "Reject booleans where an integer token count is required.",
    "negative_count": "Reject negative completion counts.",
    "misplaced_done": "Accept an optional DONE marker only in its permitted final position.",
    "duplicate_done": "Reject duplicate DONE markers.",
}


def assertions(trial):
    """Unknown, untrusted and malformed evidence is not an empty successful set."""
    checks = trial.get("checks")
    if trial.get("trusted") is not True or not isinstance(checks, dict):
        return None
    values = checks.get("assertions")
    if (
        not isinstance(values, dict)
        or not values
        or any(not isinstance(k, str) or type(v) is not bool for k, v in values.items())
        or type(checks.get("passed")) is not bool
        or checks["passed"] != all(values.values())
    ):
        return None
    return values


def guidance(pairs):
    """Input is an internal projection of regenerated reports, not self-reported grades."""
    observations, actions, gaps = [], [], []
    for pair in pairs:
        before, after = (assertions(pair[role]) for role in ("baseline", "candidate"))
        refs = [pair[role]["evidence_ref"] for role in ("baseline", "candidate")]
        changes = {
            key: []
            for key in ("improved", "regressed", "still_failing", "unchanged_passing", "uncompared")
        }
        if before is None or after is None:
            gaps.append(
                {
                    "case": pair["case"],
                    "reason": "missing_or_unverified_artifact_checks",
                    "evidence_refs": refs,
                }
            )
        else:
            for name in sorted(before.keys() | after.keys()):
                category = (
                    "uncompared"
                    if name not in before or name not in after
                    else {
                        (False, True): "improved",
                        (True, False): "regressed",
                        (False, False): "still_failing",
                        (True, True): "unchanged_passing",
                    }[before[name], after[name]]
                )
                changes[category].append(name)
            if changes["uncompared"]:
                gaps.append(
                    {
                        "case": pair["case"],
                        "reason": "check_sets_differ",
                        "checks": changes["uncompared"],
                        "evidence_refs": refs,
                    }
                )
        # A known candidate failure remains actionable even when the other arm is missing.
        failed = sorted(name for name, passed in (after or {}).items() if not passed)
        for name in failed:
            actions.append(
                {
                    "case": pair["case"],
                    "kind": "inspect_failed_check",
                    "check": name,
                    "action": "Inspect the retained candidate and frozen test for this failure. "
                    + CORRECTIONS.get(
                        name, "Check the declared criterion against the retained behavior."
                    )
                    + " This identifies the required behavior, not the cause of the failure.",
                    "evidence_refs": [refs[1]],
                    "requires_new_execution": False,
                }
            )
        observations.append(
            {
                "case": pair["case"],
                "changes": changes,
                "capture_state": pair.get("capture_state", "not_supplied"),
                "evidence_refs": refs,
            }
        )
    if not pairs:
        gaps.append({"reason": "no_paired_artifacts", "evidence_refs": []})
    regressions = any(x["changes"]["regressed"] for x in observations)
    improvements = any(x["changes"]["improved"] for x in observations)
    if regressions:
        disposition, headline = (
            "address_regression",
            "Observed check regressions; fixes do not cancel them.",
        )
    elif actions:
        disposition, headline = (
            "address_remaining_failure",
            "Candidate checks still fail; no complete fix is demonstrated.",
        )
    elif gaps:
        disposition, headline = (
            "obtain_valid_evidence",
            "Artifact comparison is incomplete or unverified.",
        )
    elif improvements:
        disposition, headline = (
            "review_observed_improvement",
            "Some artifact checks improved; this alone does not prove skill benefit.",
        )
    else:
        disposition, headline = (
            "no_observed_check_change",
            "Covered artifact checks are unchanged; no improvement was observed.",
        )
    if gaps:
        actions.append(
            {
                "kind": "resolve_evidence_gap",
                "action": "Verify retained bytes, frozen check identity "
                "and a qualified replay host "
                "before comparing; "
                "do not treat missing evidence as PASS or start new model calls automatically.",
                "evidence_refs": list(dict.fromkeys(r for g in gaps for r in g["evidence_refs"])),
                "requires_new_execution": False,
            }
        )
    if not actions:
        actions.append(
            {
                "kind": "review_scope",
                "action": "No corrective edit is indicated by these passing checks. "
                "This fixture shows no incremental "
                "benefit when checks are unchanged. Before a broader benefit claim, "
                "select a justified "
                "discriminating task and obtain any required execution authorization; do not rerun "
                "automatically. Review uncovered PR claims separately; this is not merge approval.",
                "evidence_refs": [],
                "requires_new_execution": False,
            }
        )
    return {
        "schema_version": "artifact-guidance-v1",
        "disposition": disposition,
        "headline": headline,
        "observations": observations,
        "next_steps": actions,
        "missing_evidence": gaps,
        "limitations": LIMITS.copy(),
        "automatic_acceptance": False,
    }


def safe(value):
    text = html.escape(str(value)).replace("\n", " ")
    # Entity spelling prevents active Markdown even for model-controlled case/check names.
    for char in "\\`|[]()!*_#~":
        text = text.replace(char, f"&#{ord(char)};")
    return text


def markdown(value):
    lines = ["## What to do next", "", "**" + safe(value["headline"]) + "**", ""]
    for row in value["observations"]:
        changes = row["changes"]
        lines.append(
            "- "
            + safe(row["case"])
            + ": "
            + "; ".join(
                key.replace("_", " ")
                + "="
                + (
                    str(len(names))
                    if key == "unchanged_passing"
                    else (", ".join(safe(x) for x in names) or "none")
                )
                for key, names in changes.items()
            )
            + ". Capture state: "
            + safe(row["capture_state"])
            + "."
        )
        lines.append(
            "  Evidence: " + ", ".join(safe(ref) for ref in row["evidence_refs"])
        )
    for step in value["next_steps"]:
        target = (
            safe(step.get("case", "")) + " / " + safe(step["check"]) + ": "
            if "check" in step
            else ""
        )
        lines.append("- **Next:** " + target + safe(step["action"]))
        if step["evidence_refs"]:
            lines.append(
                "  Evidence: " + ", ".join(safe(ref) for ref in step["evidence_refs"])
            )
    lines += ["", *["- Limit: " + safe(limit) for limit in value["limitations"]], ""]
    return "\n".join(lines)


def comparison(result):
    pairs = []
    for i, pair in enumerate(result["pairs"]):
        item = {
            "case": f"{pair['case_id']} / repeat {pair['repeat']}",
            "capture_state": pair["outcome"],
        }
        for role in ("baseline", "candidate"):
            trial = pair[role]
            item[role] = {
                "trusted": trial.get("grader_trust") == "reverified",
                "checks": trial.get("artifact_checks") or trial.get("checks"),
                "evidence_ref": f"report.json#/pairs/{i}/{role}",
            }
        pairs.append(item)
    return guidance(pairs)


def replay(receipt):
    by_arm = {a["arm"]: a for a in receipt.get("artifacts", [])}
    item = {
        "case": receipt.get("provenance", {}).get("task_id", "unknown"),
        "capture_state": "separate original capture; not rewritten by replay",
    }
    for index, role in enumerate(("baseline", "candidate")):
        item[role] = {
            "trusted": receipt.get("verdict") == "PASS"
            and receipt.get("qualification", {}).get("verdict") == "PASS",
            "checks": by_arm.get(role, {}).get("result"),
            "evidence_ref": f"replay.json#/artifacts/{index}",
        }
    return guidance([item])
