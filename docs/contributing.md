# Contributing

OmniRSI connects optimization conditions, measurements and verdicts. Start with
[quickstart](quickstart.md), the [module boundaries](architecture.md), and the
[Qwen B300](qwen-image-2.1-turbo-b300.md) or
[Qwen Ascend](qwen-image-2.1-turbo-ascend.md) case that matches your hardware.

## Development

Use a task branch and keep each change reviewable. Sign commits with DCO:

```bash
python -m pip install -e '.[dev,image]'
ruff check src tests benchmarks/harness
pytest
git commit -s
```

`image` is optional for the control CLI and required to run PNG quality tests.
Synthetic benchmark scripts belong in `tests/fixtures/`; historical validator
snapshots in `tests/fixtures/legacy/` remain byte-for-byte frozen. Current runnable
examples are the three Qwen scripts under `examples/`.

Use `harness/scenarios` and `model/protocols` / `model/validators` for new models,
`infra/targets` with `data/repo_packs` for repositories, and `infra/platforms` with
`data/platform_packs` for hardware. Reuse the common AB/BA loop, cleanup and
adjudication. See [extension contracts](architecture.md#where-to-extend).

For knowledge, edit one named JSON record under
`data/repo_packs/<repo>/knowledge/<backend>/<component>/` and add its navigation
link to the pack README. Do not maintain a second per-entry Markdown summary.
Keep IDs stable, omit PR links, retain source attribution and negative results,
and qualify new backends independently. See the
[knowledge maintenance guide](../src/omnirsi/data/repo_packs/vllm_omni/knowledge/README.md#maintaining-the-pack).

## Acceptance checklist

Open an issue using the [acceptance form](../.github/ISSUE_TEMPLATE/campaign-acceptance.yml)
before claiming a result. Record:

1. Campaign name, owner, goal/non-goals and stop condition.
2. Pinned baseline/candidate revisions and the immutable RunSpec: repository,
   revision, backend, devices, model, scenario, execution environment and budget.
3. Workload, required validation levels, numeric gates and validator/input hashes
   frozen **before** candidate search.
4. One hypothesis and one declared Harness/Model/Infra plane per iteration.
5. Preparation, startup/readiness, warmups and measured work separately; identical
   controls and no unreported resource contention.
6. All attempted configurations, rejected changes, raw samples, quality outputs,
   source checks and process cleanup records. Keep slow and failed trials.
7. Evidence paths, verdict rationale and the exact downstream citation.

Keep campaign revisions and thresholds in the acceptance issue and frozen
campaign evidence, not workflow defaults, generic skills or reusable recipes.
Prioritize acceptance campaigns, blocking infrastructure, merge-ready work, then
research spikes.

## Evidence and claims

```text
evidence/<campaign-id>/
  plan/        Hypothesis, RunSpec, frozen gates and environment
  results/     Raw measurements, outputs, profiler data and verdict rationale
  patch/       Candidate diff or exact revision pointer
  validator/   Frozen validation code, versions and inputs
```

| Verdict | Meaning |
| --- | --- |
| PASS | Pinned comparison, complete evidence and every required gate met |
| FAIL | Complete enough evidence shows a gate was not met |
| INCONCLUSIVE | Missing freeze, incomplete runs or unqualified/mismatched environment |

A public performance claim needs campaign-defined E2E evidence. Microbenchmarks,
operator parity and green CI do not establish service latency or image quality.
Use “on candidate versus baseline, under this RunSpec, we observed …” and link
the acceptance issue, exact revisions and artifacts. Preserve the distinction
between code-only comparisons and recipes that also change configuration.

Downstream PRs cite the same gates and evidence. Mark missing or stale results
unverified; never invent a new threshold. Label each repository/revision/backend/
device/model/scenario combination independently as validated, unsupported or
unverified. Imported reports do not become locally validated through CPU tests.
External demos or production-readiness claims require a completed acceptance
PASS and published evidence for the scope being claimed.

Execution status and campaign verdict answer different questions. A crashed or
interrupted measurement/validator leaves its execution status and error reason,
but incomplete comparison evidence is **INCONCLUSIVE**, including when the
available samples show a regression. A completed quality command rejecting its
gate, or a complete comparison missing the frozen gain threshold, remains FAIL.

Model integrity requires reading actual file bytes and comparing their SHA-256
with the frozen manifest. Equal size/mtime is only a metadata check. Validate
positive measured-image group coverage before accepting first-request quality;
a retained warmup image cannot substitute for the measured workload.

## Validation levels

| Level | Evidence | Scope |
| --- | --- | --- |
| L0 | Operator correctness | Numerical contracts, edge cases and fallbacks |
| L1 | Microbenchmark | Fixed inputs, shapes, warmups and timing |
| L2 | Isolated scenario | Stage behavior and integration |
| L3 | Model/modality quality | Complete outputs under the frozen quality protocol |
| L4 | End-to-end service | Complete workload, latency/throughput/SLO and stability |

The issue specifies the required levels. Missing required evidence means
INCONCLUSIVE. Numeric bars belong to the campaign, not this ladder. Ordinary
repository tests check framework behavior; GPU/NPU acceptance runs remain
explicit, separately budgeted experiments.

## Shared-component review

- Keep framework dispatch generic. Model/backend policy belongs to its adapter;
  reuse existing configuration rather than duplicating selection knobs.
- Enumerate all direct and transitive consumers, including other models. Map
  dtype/layout, fast/fallback, hooks, gradients and encoder/decoder contracts to
  tests. One successful Qwen image run does not validate every shared consumer.
- Prefer ordinary imports at module scope. Keep imports lazy where a module's
  transitive optional backend dependencies would otherwise break unsupported
  platforms; document and test that exception.
- Reuse the owning shared helper for identical kernel eligibility predicates.
  Colocate a small ownership-only type with its consumer rather than creating a
  module for possible future members.
- Preserve eager rounding and reduction order in exact kernels. Operator checks
  must be followed by full-model output comparison before promotion. Explain
  BF16-to-FP32 round trips when they preserve materialized eager intermediates;
  removing those casts can change output despite equivalent real arithmetic.
- Record baseline failures and untested hardware honestly. Do not mark a failing
  suite green because the same failure also occurs on the baseline.
- Freeze new references when helpers change; replay historical evidence with its
  original bundle. Never rewrite old manifests to fit a new validator.

The [B300 guide](qwen-image-2.1-turbo-b300.md#review-lessons-and-evidence) links the
review history and source-pinned evidence behind these rules.

## CI and repository reuse

Keep the existing four lanes:

| Lane | Purpose |
| --- | --- |
| [Draft](../.github/workflows/ci-draft.yml) | Lint and lightweight CPU smoke |
| [Ready](../.github/workflows/ci-ready.yml) | Full repository checks for PRs |
| [Merge](../.github/workflows/ci-merge.yml) | Lightweight manifest check on main |
| [Nightly](../.github/workflows/ci-nightly.yml) | Scheduled lint/tests and evidence layout |

Do not add default model downloads, GPU jobs or campaign thresholds to these
lanes. Dependency drift and hardware qualification require their own evidence.

When copying the repository, rename `src/omnirsi`, update package metadata,
imports and tests, and keep the three module boundaries explicit. Copy the
[evidence template](../evidence/_template/) for each campaign. Reuse portable
[skills](../skills/) as workflow guidance; keep campaign pins out of them.
