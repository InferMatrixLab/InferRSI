# Agent guide (read first)

Coding agents (Cursor, Codex, Claude, etc.) should treat this file as the **entry contract** for this repository. It is **portable**: copy it with the scaffold; do not embed campaign revision pins, model names, or hardware-specific constants here.

## What this repo is

**InferRSI** is InferMatrixLab’s canonical home for a **portable RSI / evidence-driven scaffold**. Work is organized as **SIAS**: harness × model × infra planes of the system being optimized, with runnable examples and a first-class `evidence/` tree. InferRSI's own code lives under `src/inferrsi/` (rename on copy) in four cores: Knowledge, Harness, Benchmark and Apps.

This entry contract is portable for derived scaffolds. The repository itself is the maintained workbench: delivering an independent engine uses the [engine delivery template](docs/template/README.md) and does not copy or depend on this runtime. Route your task: modify InferRSI via [contributing](docs/contributing.md) and [agent collaboration](docs/agent-collaboration.md); run experiments via [quickstart](docs/quickstart.md); find any CLI/Python operation via the [operation guide](docs/operations.md).

| Start here | Purpose |
| --- | --- |
| [README.md](README.md) | Layout, dev smoke, copy checklist |
| [docs/operations.md](docs/operations.md) | Every CLI/Python operation: entry, effect class, boundary |
| [docs/contributing.md](docs/contributing.md) | Development, acceptance, evidence and CI |
| [docs/agent-collaboration.md](docs/agent-collaboration.md) | Issue-led human–agent collaboration |
| [docs/architecture.md](docs/architecture.md) | Module boundaries and extension contracts |

## Four-lane CI

Default automation is **draft → ready → merge → nightly**. Keep **draft** light (lint + CPU smoke); do **not** invent new workflow lanes or bake acceptance runs into merge defaults.

| Lane | Workflow |
| --- | --- |
| Draft | [.github/workflows/ci-draft.yml](.github/workflows/ci-draft.yml) |
| Ready | [.github/workflows/ci-ready.yml](.github/workflows/ci-ready.yml) |
| Merge | [.github/workflows/ci-merge.yml](.github/workflows/ci-merge.yml) |
| Nightly | [.github/workflows/ci-nightly.yml](.github/workflows/ci-nightly.yml) |

Architecture and cost profile: [docs/architecture.md](docs/architecture.md).

Ready's Windows/macOS `host-compatibility` checks are **advisory and non-blocking**.
Their failure, cancellation, queued or not-run status must not block PR approval
or merging, or require a successful rerun or equivalent host-validation artifact.
Keep them out of required checks; retain actual results and unverified host status.
See [CI policy](docs/contributing.md#ci-and-repository-reuse).

## Test ladder (L0–L4)

Validation levels are defined in [validation levels](docs/contributing.md#validation-levels):

| Level | Focus |
| --- | --- |
| **L0** | Operator correctness |
| **L1** | Microbench (fixed inputs, warmup policy) |
| **L2** | Isolated scenario |
| **L3** | Model / modality quality |
| **L4** | End-to-end service (load, SLO, stability) |

**Portable bars (do not weaken):**

- **Microbench ≠ service/E2E gain** — a `PASS` on latency/throughput/SLO wording requires **L4** (or campaign-defined e2e) in `results/`; L0–L2 alone cannot justify service claims.
- **Thresholds stay out of CI defaults** — numeric bars live in acceptance issues and frozen `plan/` / `validator/`, not in workflows, skills, or repo-wide constants.
- Missing levels, partial runs, or env mismatch → **`INCONCLUSIVE`**, never `PASS` on gaps.

Repo `tests/` are **scaffold smoke** (imports, layout, verdict enum); they are not the L1–L4 campaign ladder.

## Issue-scoped pins

**Baseline SHA**, **candidate SHA**, campaign IDs, and numeric gates belong in **acceptance issues** only (checklist: [acceptance checklist](docs/contributing.md#acceptance-checklist); GitHub form: `.github/ISSUE_TEMPLATE/campaign-acceptance.yml`; pattern like issue **#3** on this repo).

Use placeholders in docs and agent output, e.g. `<baseline_sha>`, `<candidate_sha>`, `<campaign-id>` — **never** commit real campaign SHAs into workflows, skills, recipes defaults, or this file.

Campaign parameters (baseline/candidate SHAs, numeric gates) are issue-scoped. Research source citations in knowledge records and skill references are different: they are immutable provenance, preserved with their content — see the [knowledge-base contract](docs/knowledge-base.md). Do not strip provenance under a blanket “no pins” rule.

Parameterized or manual acceptance runs are issue-scoped; they are not the default merge lane.

## RSI contract

- **Resolve acceptance criteria** — preserve user-supplied criteria; when absent, use [performance-ceiling-analysis](src/inferrsi/knowledge/data/skill_library/playbooks/measurement/performance-ceiling-analysis/references/acceptance-criteria.md) to derive evidence-backed campaign targets. Retain partial requirements and derive only missing fields; unresolved evidence stays explicit.
- **Freeze gates before search** — checklist and `validator/` locked in `plan/` before Phase 3 candidate experiments ([validation levels](docs/contributing.md#validation-levels)).
- **One plane per campaign step** — change only the declared SIAS plane of the target system per step: `harness` | `model` | `infra`. These planes are not InferRSI packages.
- **Emit RunSpec snapshots** — record repo × revision × backend × device × model × scenario (`contracts/runspec.py`, campaign `plan/`).
- **Evaluator + evidence win** — never treat agent narrative as `PASS`; verdicts follow frozen gates and `evidence/<campaign-id>/` artifacts.

## Issues, claims and evidence

- Open or update an **acceptance issue before claiming `PASS`** (or publishing numbers). Cite **acceptance issues + pinned SHAs** in downstream text.
- Do **not** invent thresholds, gain or quality bars in the tree; pins and numeric gates stay **issue-scoped** only.
- **Public wording only after `PASS`** — follow [evidence and claim rules](docs/contributing.md#evidence-and-claims) (including external demo scope); until then, label unverified or `INCONCLUSIVE`.
- Use [cite-check-downstream-pr](src/inferrsi/knowledge/data/skill_library/workflows/governance/cite-check-downstream-pr/SKILL.md) and [competitor-scan](src/inferrsi/knowledge/data/skill_library/workflows/research/competitor-scan/SKILL.md) as **operators**, not campaign scripts (no pins in skill bodies).

Verdicts are **`PASS`**, **`FAIL`**, or **`INCONCLUSIVE`** only (`src/inferrsi/contracts/claim.py`). A public **`PASS`** requires:

1. Pinned baseline and candidate revisions (in the issue, cited in results)
2. Validators **frozen** before candidate search (`validator/` + gate checklist in `plan/`)
3. A complete evidence tree under `evidence/<campaign-id>/` ([layout](evidence/README.md)): `plan/`, `results/`, `patch/`, `validator/`

Agents and human reviewers **clear** work only with artifacts—not vibes. Green draft/ready CI does not imply campaign `PASS`.

## Skills

For an inference task, first select one of the [seven required primary skills by deliverable](plugins/inferrsi/skills/inferrsi/SKILL.md#load-the-primary-inference-task). Run `inferrsi skills enter <primary-id>` and read the returned instructions before the first evidence search. For an accuracy regression, use `inferrsi skills enter task-accuracy`. If the required skill cannot load, report the blocker. Frozen evaluations follow their assigned entry and knowledge condition.

Portable operator guidance and candidate procedures live in the [skill library](src/inferrsi/knowledge/data/skill_library/README.md). Keep complete English instructions, metadata, references and cases with the owner. The [knowledge-base contract](docs/knowledge-base.md) and two matrices define ownership and coverage. Keep campaign SHAs out of skill bodies.

## Optimization requests

Benchmark comparisons, ordinary project optimization and packaged optimization
tasks each have one entry workflow; see
[optimization requests](docs/operations.md#optimization-requests).

## Dev smoke (local)

Same as [README.md](README.md)—do not expand scope unless an acceptance issue requires it:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check src tests
```

## Agent discipline

1. Read the contribution guide and validation levels before large code or CI changes.
2. Prefer minimal diffs; match existing layout and naming.
3. Do not reopen closed campaign work or add pins to shared automation without explicit human direction.

## Collaboration

Rules: [agent collaboration](docs/agent-collaboration.md). Agents may carry work end to end; humans set direction through Issues and stop work with `bot:stop`. One skill per step:

- Shape an Issue: [shape-issue](.agents/skills/shape-issue/SKILL.md) — record the owner's accepted direction, preserve prior text and split into bounded native sub-issues when needed.
- Claim before starting: [claim-work](.agents/skills/claim-work/SKILL.md) — confirm the Issue has an accountable owner and `status:accepted` and that you are its deciding agent or work under its delegation, search for duplicates, claim on the Issue with the next artifact time, release if nothing appears.
- Open a PR: [open-pr](.agents/skills/open-pr/SKILL.md) — a bounded slice with independent review, branched from current `main`, local checks run, AI declaration filled; report PR readiness and Issue completion separately.
- Review: [review-pr](.agents/skills/review-pr/SKILL.md) — use the review identity format, keep comments short, never approve your own PR; one formal reviewer agent per account.
- Merge: [merge-pr](.agents/skills/merge-pr/SKILL.md) — open and ready, authorized, expected base and dependencies merged, two independent approvals, required checks green, no `bot:stop` or unlifted stop comment, and on a high-risk PR (CI, releases, secrets, permissions) at least one approval from an account on the high-risk approver list in `.github/high-risk-approvers.json` that still has write access, verified at merge time.
- Red `main`: [red-main](.agents/skills/red-main/SKILL.md) — revert the merge that broke it, then fix forward in a new PR.

## Privacy and security

Follow [privacy and security rules](docs/privacy-security.md) for every new or
modified artifact, including logs, evidence and PR text. Use placeholders for
real addresses, IPs, hostnames, usernames and personal paths; never embed or
disclose credentials. Inject secrets at runtime, redact before capture/sharing,
and check artifacts before publication. Preserve evidence verdicts and public
source attribution. Required DCO identity remains valid. Existing sensitive
content is not permission to copy it; historical cleanup is separately scoped.
