# OmniRSI (portable RSI scaffold)

This repository is the **ThinkFlowLab RSI Team** canonical home for OmniRSI and a **copyable scaffold** for new evidence-driven repos. The playbook lives in [docs/repo-template.md](docs/repo-template.md); this tree is the concrete skeleton that implements it without baking campaign-specific revision pins into CI or skills.

## Copy this scaffold to a new repo

1. Copy the top-level layout (or use GitHub’s “Use this template” once enabled): `docs/`, `recipes/`, `benchmarks/`, `evidence/`, `src/`, `tests/`, `skills/`, `.github/workflows/`, `pyproject.toml`, and this `README.md`.
2. Rename the Python package under `src/rsi_scaffold/` to your project name (e.g. `src/my_inference_lab/`). Update `pyproject.toml` `[project].name` and any workflow `paths` filters if you rename directories.
3. Read [docs/using-the-scaffold.md](docs/using-the-scaffold.md) and keep [docs/repo-template.md](docs/repo-template.md) as the chapter playbook (PM, Arch, RSI, CI, Ops).
4. Use Research fill-ins: [positioning](docs/positioning.md), [claims](docs/claims.md), [downstream](docs/downstream.md), [demo gate](docs/demo-gate.md). Open campaigns via [acceptance checklist](docs/issues-acceptance-checklist.md) or the GitHub issue template (pinned SHAs in the issue only—not workflow defaults).
5. Wire your four CI lanes (draft → ready → merge → nightly) as documented in [docs/scaffold-architecture.md](docs/scaffold-architecture.md).

## Layout

| Path | Purpose |
| --- | --- |
| `docs/` | Playbook + scaffold PRD / architecture / test design |
| `recipes/` | Runnable scenario recipes (RunSpec-oriented) |
| `benchmarks/` | Campaign and bench harness stubs (no pinned upstream SHAs here) |
| `evidence/` | First-class evidence tree: `plan/`, `results/`, `patch/`, `validator/` |
| `src/rsi_scaffold/` | Minimal package; **SIAS** seams: `harness/`, `model/`, `infra/` |
| `tests/` | CPU smoke tests for CI |
| `skills/` | Portable agent skills (generic RSI / evidence guidance) |

## Claim contract (rules only)

Verdicts are **`PASS`**, **`FAIL`**, or **`INCONCLUSIVE`**. A public `PASS` requires pinned baseline and candidate revisions, frozen validators, and a complete evidence tree—documented in the playbook, not hardcoded in this template.

## Development

```bash
python -m pip install -e ".[dev]"
pytest
ruff check src tests
```

## References

- [Repository template playbook](docs/repo-template.md)
- [Issue #1 — design](https://github.com/ThinkFlowLab/OmniRSI/issues/1)
- Campaign acceptance issues own SHAs and gates (see playbook § PM / Test design).
