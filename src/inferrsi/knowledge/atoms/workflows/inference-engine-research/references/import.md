# Import scope and verification

This library retains the English editions of the five portable skill sets
originally constructed in English and Chinese on 2026-10-14. The method was
AREX-Skill's direct `distill-ml-knowledge` workflow: scope, source grounding,
construction and verification. The five engine source
snapshots and method revision are recorded in [source-manifest.json](source-manifest.json).
They are independent knowledge snapshots, not a tested dependency matrix.

## Included material

- Complete English repository entries, sub-skills, source references,
  routing/provenance metadata and the Strata offline CSV summarizer.
- Strata's design-space analysis and the cross-engine overview in English.
- A collection router extended to include Strata alongside the other four engines.
- Repository license texts: MIT for Strata; Apache-2.0 for the other four.
- Catalog abstracts with repository/backend/scenario boundaries and pointers to
  the English documents. Prior vLLM-Omni experience records are retained.

Source clones, model weights, build environments, construction scripts, archives
and machine-specific raw construction reports are not package resources. Native
test commands in the skills require a separately supplied matching source tree.
The summarizer is an offline helper, never an engine or automatic quality gate.
Its formatting is adapted to InferRSI's line-length rules; its parsed Python AST
is unchanged from the original delivery.

## Earlier construction evidence

The original construction runs reported the following limited checks. These are
historical extraction evidence, **not rerun accelerator qualification in InferRSI**:

| Repository | Executed during original extraction | Limit |
| --- | --- | --- |
| Strata | 141 selected Python setup/source/benchmark/calibration tests; offline helper cases | Includes mocked behavior; no native C++/GPU build or model execution |
| vLLM | Source/AST, option and test-selector inspection | Native metadata test collection blocked by missing `regex`; no test body passed |
| SGLang | Registration linter over 2360 Python files and negative/repaired fixture | File scanning is not 2360 runtime tests |
| SGLang-Omni | 84 configuration and prepared-queue CPU tests | Pipeline-schema collection blocked by missing `pytest_asyncio`; no transport/model certification |
| vLLM-Omni | 5 narrow stdlib enum/deployment-shape probes | Not a complete native engine test suite |

Both original packages also underwent local-link, bilingual contract and
independent document-use reviews. Per-repository source references retain the
specific evidence and refresh boundaries. Original reports are not bundled as
new execution evidence; no performance measurements are introduced by this import.

## Qualification boundary

Every new catalog entry is imported guidance with `locally_verified=false`.
Catalog tests, wheel resource checks, parsing and CPU probes do not establish
accelerator correctness, native distributed transport, real-model quality,
concurrency stability, capacity or speedup. No DisCo managed import or global
agent-skill installation is claimed.

Before a performance claim, use InferRSI's normal acceptance process: freeze the
actual source/model/environment tuple, workload and quality gates; run the
required backend, model and service levels; preserve failures and raw artifacts.
Research-source SHAs here are provenance and do not set shared campaign defaults.
