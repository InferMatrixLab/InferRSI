# Model-aware engine research implementation plan

**Goal:** Make engine preparation discover model, framework, task, modality and
mechanism knowledge before selecting a source reference or assessing hardware.

**Architecture:** Preserve exact `knowledge search` and `context` contracts.
Add an explicit, read-only `knowledge research` operation that runs separate
queries and returns a bounded, deduplicated union with match attribution. A
small packaged MiniMax-H3 profile grounds its diffusion/video/audio identity;
the canonical research skill owns source selection and full-pipeline feasibility
procedures, including a pinned Apple Silicon worked example.

**Tech stack:** Python standard library, argparse, package resources and pytest.

## Assumptions and constraints

- This implements research/preparation, not an H3 engine, Metal adapter, model
  downloader, crawler or autonomous optimizer. User authorization covers this
  implementation; no additional execution session is needed.
- Repository/tier/backend/scenario filters remain hard filters. A caller's target
  device/backend/memory describe intent and do not certify execution support.
- Search terms within one query retain AND semantics; independent research
  queries broaden discovery. Unknown models require explicit task/modality
  inputs instead of invented architecture facts.
- Stars rank only a declared candidate set at an observation time. The selected
  implementation reference still needs license, model, format and quality checks.
- Count all selected components, avoid counting alternative checkpoints twice,
  and distinguish checkpoint bytes, logical parameters and phase residency.
  Parameter totals and 64 GiB feasibility remain unverified where sources cannot
  establish them. Imported reports cannot establish a campaign PASS.

## Implementation and verification

1. Add regression tests for separate query groups, a diverse deduplicated union,
   existing filter boundaries, unknown model behavior and unchanged exact
   search. Verify failures against the existing public CLI/API.
2. Add the minimal research helper, packaged model profile and CLI branch. Test
   the public `knowledge research MiniMax-H3 --framework mlx` path, target
   annotation validation and absence of accelerator imports or network effects.
3. Update `workflows/inference-engine-research/SKILL.md` and owner-local resources
   with the ordered preparation procedure and pinned H3 example. Check source
   metadata, full component/quantization coverage, local links and resource
   packaging. Registered skill bodies/registry are unchanged, so no generated
   skill abstract is refreshed unless inspection finds an affected input.
4. Document working commands and the exact-search/research boundary in the
   operation guide. Run focused tests, ruff and the ordinary CPU suite; exercise
   a noneditable wheel from outside this checkout with package resources.
5. Review the actual diff for scope, source fidelity, privacy and truthful
   authorship. Report local checks separately from unrun Apple hardware,
   full-model quality and service acceptance. The parent coordinates independent
   review and the PR; commits use DCO and actual model attribution.

## Design choice

Changing default search semantics would break callers that rely on token AND
and existing filters. Documentation alone would not fix discovery. The explicit
operation provides working retrieval while retaining both contracts and avoiding
an open-ended planning framework.
