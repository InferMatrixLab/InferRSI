# Contributing

InferRSI connects optimization conditions, measurements and verdicts. Start with
[quickstart](quickstart.md), the [module boundaries](architecture.md), and the
[Qwen B300](qwen-image-2.1-turbo-b300.md) or
[Qwen Ascend](qwen-image-2.1-turbo-ascend.md) case that matches your hardware.

## Development

Use a task branch and keep each change reviewable. Sign commits with DCO:

```bash
python -m pip install -e '.[dev,image]'
ruff check src tests tools
pytest
git commit -s
```

Issue-led ownership, review and completion conventions for humans and agents
are in [agent collaboration](agent-collaboration.md).

Apply [privacy and security rules](privacy-security.md) before capturing logs,
recording evidence or sharing changes. Use placeholders for private connection
details, inject credentials securely at runtime and review artifacts for leaks.

`image` is optional for the control CLI and required to run PNG quality tests.
Synthetic benchmark scripts belong in `tests/fixtures/`; historical validator
snapshots in `tests/fixtures/legacy/` remain byte-for-byte frozen. Current runnable
examples are the three Qwen scripts under `examples/`.

Git treats recorded bundles under `evidence/` and `tests/fixtures/legacy/` as
exact bytes (`-text`), so checkout and add do not normalize their line endings.
The evidence README and reusable `_template/` remain ordinary LF text. This
policy does not renormalize existing blobs or authorize edits to frozen files.
Nightly checks cover Linux and Windows checkouts with `core.autocrlf` set to
`false`, `true` and `input`.

Use `harness/scenarios` and `model/protocols` / `model/validators` for new models,
`infra/targets` with `data/repo_packs` for repositories, and `infra/platforms` for
hardware. A backend is registered in `infra/platforms/__init__.py`; its probe
command is defined in the implementing module under `infra/platforms/`. That
module owns the command name and the discovery boundary. Reuse the common AB/BA loop,
cleanup and adjudication. See [extension contracts](architecture.md#where-to-extend).

For knowledge, edit one named JSON record under
`data/repo_packs/<repo>/knowledge/<backend>/<component>/` for contribution sources,
or `data/knowledge_packs/<dependency|peer>/<repo>/<backend>/<component>/` for
external sources, and add its navigation link to the owning README. See the
[three learning tiers](../src/inferrsi/data/knowledge_packs/README.md).
`data/repo_packs/inferrsi/knowledge/` is the exception: it is generated from
`data/skill_library/` and must be refreshed, never edited. Change the skill body,
sidecar or registry, commit, then run
`python tools/build_skill_index.py --source-revision <committed-revision>`; a
hand edit there is reverted by the next run and only `--check` reports it.
Do not maintain a second per-entry Markdown summary.
Keep IDs stable, omit PR links, retain source attribution and negative results,
and qualify new backends independently. See the
[knowledge maintenance guide](../src/inferrsi/data/repo_packs/vllm_omni/knowledge/README.md#maintaining-the-pack).

Protected changes also require a current-head
[knowledge authorship declaration](knowledge-model-policy.md). Every material AI
author must use an approved model at `xhigh` or `max`; human-only work is declared
explicitly. Mechanical/generated changes have no automatic exemption. The check
is a required status on `main`, so a failing declaration blocks merging; the
`protect-main` ruleset is the source of truth for that enforcement. A passing
check establishes declaration compliance only, not execution settings or results.

The [skill library](../src/inferrsi/data/skill_library/README.md) owns complete
procedures, metadata, references and cases. Place platform-specific skills under
`hardware/ascend`, `hardware/cuda` or `hardware/host`; use `frameworks/<name>`,
`repositories/<name>`, `methods` or `workflows` for other primary owners. Maintain
the registered stable IDs and their categorized paths in `skill-index.json`, then refresh
their generated abstracts with `tools/build_skill_index.py`. Keep all skill
content in the canonical library. Preserve source state and
`UNKNOWN` license declarations; moving content does not resolve licensing.

Keep all library content in English. Engine procedures belong under
`repositories/<engine>/` and the collection router under
`workflows/inference-engine-research/`, with their sub-skills and references.
Keep supporting Markdown and JSON with their owner; the library
root contains only `README.md` and `skill-index.json`.
Catalog abstracts link to packaged bodies via `skill_documents.original` for
migrated skills or `skill_documents.en` for engine procedures. Update
affected source content and catalog records together. Source snapshot revisions
identify research evidence, not campaign defaults. Check linked resources,
licenses, local links and reads from a noneditable wheel installation.

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

Run `python tools/validate_evidence.py` for a read-only check of every committed
evidence bundle. [The inventory](../tools/evidence_inventory.json) declares
campaign, template, source-import, review-summary and external-archive layouts;
new directories and recognizable manifests require an explicit classification.
The nightly lane runs this CPU-only check. It verifies available bytes using
existing bundle SHA-256 maps, historical file mappings or archive SHA-256/size
records. Historical mappings point only to preserved snapshots, never current
implementations. Do not invent hashes or update frozen manifests to silence a
failure.

The JSON result separates structural/hash errors (nonzero exit) from unavailable
external dependencies. Remote archives are not downloaded; if supplied at their
declared inventory paths, their recorded size and digest are checked. A missing
locally required hashed file is an error. Raw outputs and original source files
not committed here remain explicitly unavailable. Successful inventory checks
do not verify those external bytes, replay validators, qualify hardware, or
change any campaign verdict. This inventory is editable validation policy;
the evidence it describes remains frozen.

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
| [Merge](../.github/workflows/ci-merge.yml) | Manifest check and lightweight CPU smoke on main |
| [Nightly](../.github/workflows/ci-nightly.yml) | Scheduled lint/tests and evidence layout |

Ready CI also builds the source distribution and wheel, installs the wheel with
the optional `skills` parser in a fresh virtual environment, and runs
`tests/check_installed.py` outside the checkout with `PYTHONPATH` unset and Python
isolated mode enabled. This checks packaged knowledge, skill bodies, licenses,
helpers and CLI reads without installing any inference engine.
The ready test and installed-package jobs cover the declared minimum Python
3.10 alongside Python 3.11. This matrix does not certify later Python releases
or accelerator runtime compatibility.

The merge lane runs the same small smoke selection as draft on every main push,
including direct pushes. It is a post-push safety check, not a branch-protection
rule or a substitute for the full ready checks before merging. Required checks
and permission to push directly remain repository-owner settings.

Do not add default model downloads, GPU jobs or campaign thresholds to these
lanes. Dependency drift and hardware qualification require their own evidence.

When copying the repository, rename `src/inferrsi`, update package metadata,
imports and tests, and keep the three module boundaries explicit. Copy the
[evidence template](../evidence/_template/) for each campaign. Reuse portable
[workflows](../src/inferrsi/data/skill_library/workflows/) as workflow guidance; keep campaign pins out of them.

For a standalone engine delivery, start with the
[engine delivery template](template/README.md) in `docs/template/` instead of
copying the entire InferRSI runtime. It covers language-specific adaptation,
approved local brand assets, the four evidence segments and schema-v1 source
recipes for [InferMatrixLab/recipe](https://github.com/InferMatrixLab/recipe).
The engine owns implementation and recipes; catalog maintainers own collection,
schema and website; the acceptance owner owns performance verdicts. Follow the
template's copy, validation and catalog-registration steps. Missing hardware
verification remains explicit. Workbench experiments use the
[quickstart](quickstart.md) and [evidence template](../evidence/_template/);
the four CI lanes retain their current roles.
