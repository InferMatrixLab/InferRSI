"""Pure public input construction shared by scripted qualification and live freeze.

No discovery, credentials, provider calls, ledger actions or hidden-trace input.
Expected development/benchmark data stays in the trusted workbench suite only.
"""

import hashlib

from inferrsi.harness.kv_edit_workbench import VisibleSuite
from inferrsi.model.anthropic_agent import canonical

COMMON = {"candidate.py", "task.json", "CONTRACT.md", "workbench.md", "development.json"}
KNOWLEDGE = {"knowledge/SKILL.md", "knowledge/metadata.json",
             "knowledge/references/source-notes.md"}
KNOWLEDGE_ROOT = "src/inferrsi/data/skill_library/repositories/vllm/audit-vllm-kv-lifetimes/"
PROMPT = (
    "Use only the exposed task, contract, starter and fixed visible workbench. "
    "Only candidate.py may change. External links are not readable files. "
    "Finish after current-revision checks and measurement. "
    "Any supplied knowledge is fallible guidance."
)
WORKBENCH = """# Fixed synthetic CPU workbench

Read task.json, CONTRACT.md, candidate.py and development.json. Only candidate.py
may change. The exposed development file contains public case IDs and events;
trusted expected outputs remain outside the read allowlist.

Use write_candidate to retain a revision, run_visible_checks for bounded public
correctness feedback, and run_visible_benchmark for fixed whole-command AB/BA
timing against the starter. Measurement includes sandbox/interpreter startup and
requires correct complete output. Rewriting invalidates previous receipts.
Submit only after checks and measurement on the current revision. Hidden final
grading occurs after immutable submission and never feeds another edit.

This synthetic feasibility task does not establish production performance or
knowledge efficacy. Any knowledge files explicitly exposed in the manifest are
fallible guidance; their outbound links do not expand the read allowlist.
"""


def common_actor_contract_sha256(config):
    """Bind exact shared exposure/protocol/workload despite transport-specific IDs.

    Scripted callback identities include response fixture bytes and therefore
    cannot equal live callback identities. No other edit-plan field is omitted.
    Outer campaign IDs are separately frozen by each supervising controller.
    """
    value = {k: config[k] for k in (
        "arm", "model", "client", "input_token_ceiling", "prompt", "suite_sha256",
        "baseline_sha256",
    )}
    value["schema"] = "kv-common-actor-contract-v1"
    value["edit_plan"] = {k: v for k, v in config["edit_plan"].items()
                          if k != "callbacks_sha256"}
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def build_inputs(baseline, contract, development, benchmark_events, benchmark_expected,
                 min_improvement_pct):
    """Return (public byte map, common prompt, private visible-workbench suite).

    All workload/gate inputs must come from the prospectively frozen task. No
    grader split is accepted, and no expected outputs enter the public byte map.
    Both arms use this same result; callers add only the allowlisted K to A3.
    """
    if (type(baseline) is not bytes or not 0 < len(baseline) <= 65536
            or type(contract) is not bytes or not contract):
        raise ValueError("Explicit bounded starter and contract bytes required")
    baseline.decode("utf-8")
    contract.decode("utf-8")
    suite = VisibleSuite(canonical({
        "schema": "kv-visible-suite-v1", "development": development,
        "benchmark_events": benchmark_events, "benchmark_expected": benchmark_expected,
        "min_improvement_pct": min_improvement_pct,
    }).encode())
    public = {
        "candidate.py": baseline,
        "CONTRACT.md": contract,
        "task.json": canonical({
            "request": "Optimize Reclaimer; preserve its complete contract.",
            "workbench": "fixed public checks and whole-command AB/BA timing",
            "scope": "synthetic CPU feasibility only; no production or knowledge-efficacy claim",
        }).encode(),
        "workbench.md": WORKBENCH.encode(),
        "development.json": canonical({
            "schema": "kv-public-development-v1",
            "traces": [{k: t[k] for k in ("id", "events")}
                       for t in suite.read()["development"]],
        }).encode(),
    }
    return public, PROMPT, suite
