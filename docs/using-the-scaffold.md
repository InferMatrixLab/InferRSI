# Using the portable scaffold

Short guide for teams copying this tree into a new repository.

## 1. Start from the playbook

[repo-template.md](repo-template.md) defines **how** RSI repos are run (Now board, claim contract, SIAS, four CI lanes). This directory’s sibling folders are **what** to copy.

## 2. Rename the package

Default import path: `rsi_scaffold`. After copy:

- Rename `src/rsi_scaffold/` → `src/<your_package>/`.
- Update `pyproject.toml` project name and setuptools discovery.
- Search-replace `rsi_scaffold` in `tests/` and docs.

## 3. Evidence-first campaigns

Per campaign, populate under `evidence/<campaign-id>/` (or a path your issue specifies):

- `plan/` — hypothesis, RunSpec snapshot, gate checklist  
- `results/` — metrics, logs, verdict rationale  
- `patch/` — candidate diff or revision pointer  
- `validator/` — frozen validator definition  

Verdict labels: `PASS` / `FAIL` / `INCONCLUSIVE` only.

## 4. SIAS placement

This scaffold keeps **harness**, **model**, and **infra** under `src/<package>/` for a single installable unit. Top-level `benchmarks/` and `recipes/` stay orchestration-facing. If you prefer top-level `harness/` folders, split them—but document the choice in your README and keep cross-plane imports explicit.

## 5. CI lanes

| Lane | Workflow file | Intent |
| --- | --- | --- |
| Draft | `ci-draft.yml` | Lint + smoke on every push to feature branches |
| Ready | `ci-ready.yml` | Fuller checks on pull requests |
| Merge | `ci-merge.yml` | Lightweight main push (no full campaign re-run) |
| Nightly | `ci-nightly.yml` | Scheduled safety net on `main` |

Campaign SHAs belong in **acceptance issues** or parameterized workflow runs—not in these default workflows.

## 6. Research + PM stubs

- [positioning.md](positioning.md), [claims.md](claims.md), [downstream.md](downstream.md), [demo-gate.md](demo-gate.md)  
- [issues-acceptance-checklist.md](issues-acceptance-checklist.md) and `.github/ISSUE_TEMPLATE/campaign-acceptance.yml`  

## 7. Skills

Copy `skills/` into your agent environment or Cursor skills path. Operators are generic (draft acceptance issue, competitor scan, cite-check downstream PR)—no campaign SHAs in skill bodies.
