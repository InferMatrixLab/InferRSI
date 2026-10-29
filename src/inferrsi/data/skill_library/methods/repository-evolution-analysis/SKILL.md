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

Use historical tasks to separate earlier onboarding evidence from later test
changes. Keep three evidence classes distinct: the pinned public implementation
below, the paper's reported method/results, and proposed InferRSI safeguards.

### Observed public implementation

The following is a source inspection of
[LearningToCommit at `7e5a1d770eb9eb58e614db45f40b1b911529c6e7`](https://github.com/LearningToCommit/LearningToCommit/tree/7e5a1d770eb9eb58e614db45f40b1b911529c6e7),
not an executed benchmark or a claim of equivalence with every paper version.

1. **Scan and split**
   ([`s1_scan_commits.py`](https://github.com/LearningToCommit/LearningToCommit/blob/7e5a1d770eb9eb58e614db45f40b1b911529c6e7/data_construction/s1_scan_commits.py),
   [`utils.py`](https://github.com/LearningToCommit/LearningToCommit/blob/7e5a1d770eb9eb58e614db45f40b1b911529c6e7/data_construction/utils.py)):
   parse non-merge commit metadata/numstat, prefilter tiny or housekeeping
   changes, sort retained commits by the recorded date, keep the most recent
   requested count, then assign the oldest fraction to `learning` and the
   remainder to `test`. An LLM suitability scan follows that split; unavailable
   or oversized diffs are marked unsuitable. This stage, not S3, assigns the
   chronological split.
2. **Derive categories**
   ([`s2_cluster.py`](https://github.com/LearningToCommit/LearningToCommit/blob/7e5a1d770eb9eb58e614db45f40b1b911529c6e7/data_construction/s2_cluster.py)):
   ask a model to derive development categories from a sample of suitable
   commits' suitability rationales. This is not direct file-coupling clustering.
3. **Tag categories**
   ([`s3_tag.py`](https://github.com/LearningToCommit/LearningToCommit/blob/7e5a1d770eb9eb58e614db45f40b1b911529c6e7/data_construction/s3_tag.py)):
   classify each suitable commit using the categories, subject, rationale and
   diff; retain the existing split. The tag is a category, not a cutoff date.
4. **Sample separately**
   ([`s4_sample.py`](https://github.com/LearningToCommit/LearningToCommit/blob/7e5a1d770eb9eb58e614db45f40b1b911529c6e7/data_construction/s4_sample.py)):
   perform category-proportional sampling within the learning and test pools,
   excluding unsuitable and uncategorized commits. This does not promise equal
   category counts or coverage when the requested sample is too small.
5. **Build tasks**
   ([`s5_build.py`](https://github.com/LearningToCommit/LearningToCommit/blob/7e5a1d770eb9eb58e614db45f40b1b911529c6e7/data_construction/s5_build.py)):
   export each sampled change's oracle diff and parent-revision source archive;
   synthesize an issue-style query from subject, body and diff. The emitted
   `benchmark_tasks.jsonl` top-level fields are:
   ```text
   id, repo, category, synthetic_query, oracle_diff, snapshot_path,
   learning_commits
   ```
   Each learning record contains `sha, repo, title, category, synthetic_query,
   diff_path, snapshot_path`. Mode `all` shares all sampled learning commits
   with each test task; `by_category` selects the matching category. No
   `tier`, frozen `validator` or verification-command field is emitted here.

**Snapshot and access boundary.** S5's helper uses `git archive` at the sampled
commit's parent. [`modules/sandbox.py`](https://github.com/LearningToCommit/LearningToCommit/blob/7e5a1d770eb9eb58e614db45f40b1b911529c6e7/modules/sandbox.py)
extracts that archive and initializes a new Git repository with a base commit;
it does not give the agent the target repository's original history. These
inspected paths do not implement a `hidden_paths` filter or frozen external
validator. The phase directory is explicitly **not a security sandbox**:
agent tools run with host-user permissions. A parent snapshot alone does not
establish isolation from later source, oracle data or other host files.

**Skill conditioning.**
[`workflow/phases.py`](https://github.com/LearningToCommit/LearningToCommit/blob/7e5a1d770eb9eb58e614db45f40b1b911529c6e7/workflow/phases.py)
copies learned skill files into the phase's separate skills directory for the
with-skill solve; the baseline receives no skill directory.
[`modules/prompt_builder.py`](https://github.com/LearningToCommit/LearningToCommit/blob/7e5a1d770eb9eb58e614db45f40b1b911529c6e7/modules/prompt_builder.py)
substitutes workspace/skills paths and describes that directory in the user
context. The [with-skill template](https://github.com/LearningToCommit/LearningToCommit/blob/7e5a1d770eb9eb58e614db45f40b1b911529c6e7/system_prompts/solve_with_skill.txt)
points to it; the environment context asks the agent to read `SKILL.md` first.
This is directory-based access, not verbatim insertion of the skill body.

**Evaluation, not a correctness oracle.**

- [`evaluation/programmatic_metrics.py`](https://github.com/LearningToCommit/LearningToCommit/blob/7e5a1d770eb9eb58e614db45f40b1b911529c6e7/evaluation/programmatic_metrics.py)
  computes changed-file IoU, tool-using assistant-message counts from the
  trajectory, and signed/absolute line-count deviation from the oracle patch.
  It does not run a frozen validator or map validator exit codes to task
  correctness.
- [`evaluation/pairwise_judge.py`](https://github.com/LearningToCommit/LearningToCommit/blob/7e5a1d770eb9eb58e614db45f40b1b911529c6e7/evaluation/pairwise_judge.py)
  compares the with-skill and baseline **patches**, shown with the task query
  and oracle diff, on scope alignment, logic similarity, redundancy/hallucination
  and code style. Its default four rounds use ABBA presentation order. It is
  not an oracle-trajectory comparison or a fallback gated on ambiguous
  programmatic results. Patch similarity and judge preference do not establish
  functional correctness.

### Paper claims and version boundary

The [existing Learning to Commit paper ledger](../../workflows/npu-skill-factory/references/papers-20261015/references/learning-to-commit.md)
records the v1 method, author-reported pilot outcomes and limitations. Those
paper claims are separate from the public-code observations above; this source
reconciliation does not reproduce them or establish paper-to-code equivalence.
Do not combine versions or promote this candidate on the basis of reported
localization, patch-size or judge outcomes.

### Proposed InferRSI safeguards and portability questions

These are adaptations to evaluate, **not mechanisms attributed to the pinned
upstream implementation**:

- Freeze the learning inputs and skill revision before held-out evaluation;
  audit synthetic-query answer leakage independently of the chronological split.
- Enforce source/oracle separation in an actually isolated, least-privilege
  execution environment. If paths must be hidden, specify and verify that policy
  rather than assuming that an archive or phase directory enforces it.
- Define and freeze task-specific correctness/integrity validators outside the
  editable workspace, with explicit failure and incomplete-evidence handling.
  Report correctness separately from localization, style, patch size and cost.
- For NPU/kernel tasks, first check whether commit context supports an intent-only
  query and a reproducible parent environment. Compiler/runtime availability,
  numerical checks, profiler access and performance-regression gates require
  task-specific qualification; temporal sampling alone does not transfer them.
- Compare with-skill and baseline under declared matched model, harness, tool and
  budget controls, retaining failed attempts and deviations. No kernel-repository
  portability, agent-efficacy or performance result is established by this guide.

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
