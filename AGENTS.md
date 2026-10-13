# Agent guide (read first)

Coding agents (Cursor, Codex, Claude, etc.) should treat this file as the **entry contract** for this repository. It is **portable**: copy it with the scaffold; do not embed campaign revision pins, model names, or hardware-specific constants here.

## What this repo is

**OmniRSI** is ThinkFlowLab’s canonical home for a **portable RSI / evidence-driven scaffold**. Work is organized as **SIAS**: harness × model × infra seams under `src/omnirsi/` (rename on copy), with recipes, benchmarks, and a first-class `evidence/` tree.

| Start here | Purpose |
| --- | --- |
| [README.md](README.md) | Layout, dev smoke, copy checklist |
| [docs/contributing.md](docs/contributing.md) | Development, acceptance, evidence and CI |
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

Parameterized or manual acceptance runs are issue-scoped; they are not the default merge lane.

## RSI contract

- **Freeze gates before search** — checklist and `validator/` locked in `plan/` before Phase 3 candidate experiments ([validation levels](docs/contributing.md#validation-levels)).
- **One plane per campaign step** — change only the declared SIAS plane per step: `harness` | `model` | `infra` (under `src/omnirsi/`).
- **Emit RunSpec snapshots** — record repo × revision × backend × device × model × scenario (`runspec.py`, campaign `plan/`).
- **Evaluator + evidence win** — never treat agent narrative as `PASS`; verdicts follow frozen gates and `evidence/<campaign-id>/` artifacts.

## Issues and claims (PM)

- Open or update an **acceptance issue before claiming `PASS`** (or publishing numbers).
- Do **not** invent thresholds in the tree; pins and numeric gates stay **issue-scoped** only.
- Public wording: [evidence and claim rules](docs/contributing.md#evidence-and-claims).

## Research lock

- Cite **acceptance issues + pinned SHAs** in downstream text; do not invent gain or quality bars.
- **Public wording only after `PASS`** — follow [evidence and claim rules](docs/contributing.md#evidence-and-claims); until then, label unverified or `INCONCLUSIVE`.
- Use [skills/cite-check-downstream-pr](skills/cite-check-downstream-pr/SKILL.md) and [skills/competitor-scan](skills/competitor-scan/SKILL.md) as **operators**, not campaign scripts (no pins in skill bodies).

## Evidence and clearing the bar

Verdicts are **`PASS`**, **`FAIL`**, or **`INCONCLUSIVE`** only (`src/omnirsi/claim.py`).

A public **`PASS`** requires:

1. Pinned baseline and candidate revisions (in the issue, cited in results)
2. Validators **frozen** before candidate search (`validator/` + gate checklist in `plan/`)
3. A complete evidence tree under `evidence/<campaign-id>/`: `plan/`, `results/`, `patch/`, `validator/`

Agents and human reviewers **clear** work only with artifacts—not vibes. Green draft/ready CI does not imply campaign `PASS`.

| Topic | Doc |
| --- | --- |
| Claim wording and external demo scope | [evidence and claim rules](docs/contributing.md#evidence-and-claims) |
| Evidence layout | [evidence/README.md](evidence/README.md) |

## Skills

Portable operator guidance lives under [skills/](skills/) (draft acceptance issue, claim contract, RSI evidence, cite-check downstream PR, competitor scan). Keep **AGENTS.md** short; follow skill bodies for procedures—skills must remain free of campaign SHAs.

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
