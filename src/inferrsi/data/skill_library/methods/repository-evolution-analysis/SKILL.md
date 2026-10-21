---
name: repository-evolution-analysis
description: 'Analyze a repository''s commit history to build a capability-evolution model: what the system can do, how it got there, and what patterns allow it to iterate quickly. Use to produce history-derived knowledge for agent skill conditioning, and to design temporal-split benchmarks for skill evaluation.

  '
---

# Repository Evolution Analysis

Status: candidate. Procedures have not been evaluated against a real campaign.

## When to use this skill

Use this skill when you need to answer one of these questions before acting
on a repository:

- What capabilities has this repository accumulated, and in what order?
- Why can this team iterate quickly, and what patterns should I preserve?
- What historical tasks can I construct for skill evaluation with a proper
  temporal cutoff?
- Does this repository have a recurring convention for adding a new provider,
  adapter, or capability class that I should follow?

Do not use this skill to justify a specific code change — that requires
evidence from the current source. This skill produces history-derived
knowledge that conditions how you approach future changes.

## Evidence to inspect first

Before analysing history, determine what you have:

1. Does `git log` work? (Full history vs. shallow clone — report the clone depth.)
2. What are the top-level directories and their activity counts?
   `git log --numstat --format='%H' | grep -v '^$' | awk '{print $3}' | cut -d/ -f1 | sort | uniq -c | sort -rn | head -10`
3. What is the commit rate over time? A prepared JSONL extract is faster than
   re-scanning — if one exists, use it.
4. Are there already extracted commit clusters, coupling indexes, or important-
   commit shortlists? If so, read those first and validate by sampling diffs
   rather than running a full re-scan.

## Building the evolution model

The model has three parts. Build them in order.

### State model

Identify what state the repository carries across commits: registered modules,
provider/adapter lists, config surfaces, routing tables. These are the nouns
that change.

Method: look for `register`, `PROVIDERS`, `ADAPTERS`, `BACKENDS`, `ROUTES`,
`plugins`, `catalog` patterns in the most-active files. Count commits per
top-level directory as a proxy for where state lives.

From the Magpie analysis (source-grounded, commit history 2026-09-22 to
2026-10-14, 3428 commits):
- State lives almost entirely in `internal/` (3280 commits = 95.7% of activity).
- Key state surfaces: provider registry, subscription manager, routing groups,
  session index, library (MCP/skills/instructions), gateway config, usage ledger.
- `docs/` (152) and `site/` (83) are secondary; `.github/` (26) is CI-only.
Source: `magpie-change-coupling.json`, `magpie-commits.jsonl`.

### Capability model

Name the recurring capability families. A family is a cluster of commits that
add, repair, and extend one coherent user-facing capability.

Method: start from existing clusters if available; validate each by sampling
2-3 diffs per cluster. For an unanalysed repository, use `git log --follow
--numstat -- <path>` on the most-active files, then group files by co-commit
frequency.

From the Magpie analysis (source-grounded):

| Family | Subsystem | Commits (approx) | Description |
|--------|-----------|-------------------|-------------|
| Provider onboarding | internal | ~300 | Adding a new AI provider/subscription |
| Subscription/auth | internal | ~200 | Sign-in flows, session tokens, metering |
| Routing & affinity | internal | ~150 | Routing groups, per-client affinity |
| GUI settings | internal | ~200 | Settings pages, UI state |
| Library/MCP | internal | ~180 | Skills, MCP servers, instructions sharing |
| Session search | internal | ~120 | Session index, search, folders |
| Usage/metering | internal | ~160 | Balance, usage charts, gateway keys |
| i18n | internal | ~120 | German, Japanese, Traditional Chinese |

Source: `magpie-clusters.json`, validated by diff sampling on 8 SHAs from
`magpie-important-commits.md`.

### Transition model

For each family, reconstruct the actual commit sequence. The task description
proposes: initial feature → repair → edge-case → abstraction → compatibility
→ validation → cleanup. Do **not** assume this order. Infer it from real SHAs.

From the Magpie analysis, the observed sequence for **provider onboarding**:

1. `702477525a` (2026-09-24): Claude subscription as a provider; model lists
   fetched, never compiled in. [initial feature]
2. `9bf6d43527` (2026-10-01): magpie no longer asks Anthropic for usage; adding
   an account improved. [repair + edge-case]
3. `09c635cf03` (2026-09-25): model tells Pi/Crush/Codex how much it holds.
   [capability extension, concurrent with step 2]
4. `4f22d103d3` (2026-09-27): Kiro served through its own API. [parallel provider
   variant — abstraction follows feature]

Observed sequence for **library/MCP centralization**:

1. `dfc2d7fa93` (2026-09-25): MCP servers, skills, instructions kept once in
   magpie, given to every agent. [initial abstraction — after several individual
   agent-specific skills existed]
2. `bf0f3e3f73` (2026-10-03): a remote MCP server signed in once in magpie used
   by every agent. [capability extension]
3. `9848a9062a` (2026-10-03): RTK says when it is missing and installs it.
   [repair — self-healing environment]

Source: `magpie-important-commits.md`, verified via `git show --stat` on each SHA.

**Key observation:** In Magpie, abstraction layers are introduced *after* 2-5
features exist that would share them, not speculatively upfront. This is
consistent across provider onboarding, library/MCP, and routing. Source: inferred
from commit date ordering; not causally established.

## Historical Magpie observations and their limits

These are carried history-analysis results from the earlier corpus, not a fresh
coordination audit. Commit granularity, repair intervals and subject patterns do
not causally establish speed, review latency, automation or release reliability.
The first-hand ownership/concurrency/review/testing/integration/release case is
pending Dot delivery and owner review; do not reconstruct it from these counts.

**Evidence-grounded findings:**

- **Change granularity**: 71% of commits under 1000 lines; p50 = 151 lines,
  p75 = 342. Review speed and change safety were not measured.
  Source: computed from `magpie-commits.jsonl` numstat.

- **Repair latency**: median 1.54 hours from feature commit to related fix
  (454 validated commit pairs). 42% of repairs land within 1 hour.
  Source: computed from `magpie-commits.jsonl` date fields.

- **Single-subsystem focus**: 91.3% of focused commits touch only one top-level
  area. Provider, gateway, and GUI changes arrive in separate commits.
  Source: computed from `magpie-commits.jsonl` top-3 paths.

- **PR merge cadence**: ~40 PRs/day (from `(#NNNN)` patterns in subjects);
  27% of commits include a PR number.
  Source: computed from `magpie-commits.jsonl` subjects.

- **Abstraction timing**: shared layers introduced post-feature (observed for
  library/MCP, provider registry, routing groups). Correlation with speed;
  causation not established.

**What this implies for an agent working on such a repository:**
When adding a new provider, adapter, or capability class, follow the existing
registration pattern — do not introduce a new abstraction unless 2+ concrete
implementations already exist.

## Auditing a claimed capability

When a release note or README claims a capability and you need to state whether
it runs at a given revision, use
[capability presence audit](references/capability-presence-audit.md). It classifies
each claim into implemented, hook, documented only or contradicted, and requires
the enabling gate for anything not implemented. This is narrower than the
capability model above: it answers presence and wiring, not speed.

## Temporal-split benchmark construction (LearningToCommit method)

For skill evaluation, construct historical tasks with a hard temporal cutoff.

**Key pipeline stages** (source: `LearningToCommit` @ 7e5a1d77):

1. Scan commits (`s1_scan_commits.py`): extract commit metadata, diffs, and
   affected files. Filter to commits that change a non-trivial number of files
   with a clear intent signal.

2. Cluster (`s2_cluster.py`): group commits by affected subsystem and change
   type. Clusters become task categories.

3. Tag (`s3_tag.py`): tag each commit with the cutoff date. The cutoff is
   enforced by the tag, not by filtering the log — the agent's provided snapshot
   is built from the repository at the cutoff revision, not the current HEAD.

4. Sample (`s4_sample.py`): stratified sampling by cluster to balance categories.

5. Build benchmark (`s5_build.py`): for each sampled commit, create a task
   record with fields:
   ```
   task_id, repo, base_commit (= parent of the sampled commit),
   problem (synthesised from commit message + diff context),
   expected_capability, tier (A = CPU/static, B = device/runtime),
   verification (argv for the validator), validator (frozen Python file),
   oracle (private merged reference)
   ```
   Source: `data/learning_to_commit_benchmark.jsonl` field schema (observed,
   7e5a1d77).

**Temporal cutoff enforcement:**
The agent receives a source archive built from `base_commit` (the commit just
before the sampled change). The archive excludes the `.git` directory and any
path listed in `hidden_paths`. The agent must not have access to any file that
postdates the cutoff. Verification uses a frozen validator file stored outside
the editable workspace.
Source: `LearningToCommit/modules/agent.py`, `skill_distill.py` `snapshot()`
function (observed in sibling workstream @ 82218b4).

**Skill conditioning:**
The agent receives the skill document injected before the task context. The
`solve_with_skill.txt` prompt template places the skill before the problem
statement; `solve_baseline.txt` omits it. All other parameters (model, harness,
tools, timeout, budget) are held constant.
Source: `LearningToCommit/system_prompts/solve_with_skill.txt`,
`modules/prompt_builder.py`.

**Evaluation:**
- Programmatic: does the frozen validator pass? (exit 0 = success, 1 = task
  failure, other = inconclusive). Source: `evaluation/programmatic_metrics.py`.
- Pairwise judge: LLM comparison of agent trajectory against oracle trajectory.
  Used only when programmatic check is ambiguous.
  Source: `evaluation/pairwise_judge.py`.

**Portability to NPU/kernel repositories:**
The temporal split and stratified sampling transfer directly. What must change:
- Task synthesis: kernel repo commits rarely have prose issue descriptions;
  problem statements must come from the commit message and diff context, not
  issue trackers.
- Validation: success criteria for kernel tasks involve compiler correctness
  + performance regression tests, not just test-pass/fail.
- Agent tools: kernel tasks require a compiler and profiler in the sandbox, not
  just Bash/Read/Write.
Source: inferred from LearningToCommit design; not empirically tested on kernel repos.

## Scoped historical lessons

For each lesson, record parent snapshot, task intent, accepted change, the agent's
specific discrepancy and the narrow applicability condition. Separate file-local
habits, subsystem invariants and repository-wide conventions. Accepted historical
code is a contrastive reference, not the unique correct solution or an eternal
rule. Revise or retire lessons when later accepted evidence contradicts them.

Freeze adaptation inputs before future-task evaluation; audit issue synthesis and
source access independently. Report correctness, localization, patch size, style
and resource use separately. The
[Learning to Commit paper ledger](../../workflows/npu-skill-factory/references/papers-20261015/references/learning-to-commit.md)
and [convention-expiry counterexample](../../workflows/npu-skill-factory/references/papers-20261015/cases/methodology-counterexamples.md#e-c2--better-repository-familiarity-can-produce-unnecessary-caution)
extend the existing temporal-split method. These methodology papers do not verify
Magpie's actual development coordination or authorize another history scan.

## Constructing the capability evolution graph

For a new repository, build the graph with this procedure:

1. Run coupling analysis on the commit log to find co-changed file sets.
2. For the top 5-10 file clusters, trace the commit sequence on those files
   with `git log --follow --numstat -- <path>`.
3. For each cluster, read the first, largest, and most recent 2-3 commits.
   Record for each:
   ```
   intent:    (what the commit message says it does)
   subsystem: (top-level directory or component name)
   before:    (concrete: what was the state/API before this commit)
   after:     (concrete: what changed in behavior/interface)
   files:     (list of changed files)
   validation: (were tests added? in the same commit or a later one?)
   followups: (SHA of the next commit in the same family, if traceable)
   rework:    (was this commit later reverted or significantly amended?)
   ```
4. Connect nodes with edges only where a commit SHA directly establishes the
   connection (not where you infer it from timing alone).

INCONCLUSIVE: if the repository history has gaps (shallow clone, squash merges,
or missing files), report which capability families cannot be reconstructed and
why.

## What this skill does not do

- It does not analyse the current source to determine correctness.
- It does not produce a performance measurement.
- It does not decide whether a proposed change is safe to make.
- It does not automatically select which tasks to include in a benchmark.

All of those require separate evidence.
