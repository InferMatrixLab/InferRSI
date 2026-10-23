# Prior coverage and incremental delta

This file is a readset/crosswalk, not a new maintained matrix. Inventory-level statements describe supplied snapshots, not current repository verification.

## Earlier six-paper artifact inspected before mining

- `prior-foundation-pack/INTEGRATION_NOTES.md`
- `prior-foundation-pack/choose-prefill-decode-schedule/references/source-notes.md`
- `prior-foundation-pack/notes/scheduling.md`
- The bundle's file inventory and title/ID matches were checked for all four Pack A papers.

Vidur was an explicitly unread next gate in Sarathi-Serve's scheduling extraction. Pack A closes that paper-reading gate with calibration/simulation evidence; it does not reread or replace Sarathi/DistServe mechanisms. The other three Pack A titles/IDs had no prior extraction in those readsets.

**Verified prior artifact locators, outside this standalone pack:** `choose-prefill-decode-schedule/SKILL.md`, `choose-prefill-decode-schedule/references/source-notes.md`, and `notes/scheduling.md` within the earlier `inferrsi-paper-delivery` bundle. Link them during integration using the owner's actual artifact destination. Local scratch paths are locators, not assumed shareable URLs.

## Earlier implementation discovery inspected

`source-notes/inferrsi-engine-references.md` and `source-notes/inferrsi-npu-references.md` were searched/read for overlap. Their serving scheduler/connector and NPU implementation boundaries remain separate evidence. Pack A establishes no latest engine behavior, NPU compatibility, SSD coverage or network tuning mechanism. The separately present `inferrsi-candidate-bundles` inventory was checked; its vLLM and NPU lifecycle candidates are not replaced.

## Supplied matrix / handoff overlap

`prior-readsets/reference-matrix.md` is a supplied snapshot: branch `opus/meta-skill-bootstrap`, revision `4d61d2c`, date2026-10-15. Relevant Reference Matrix systems and methodology rows, HANDOFF Task1, and pasted handoff performance-ceiling entries were read. Existing inventory already includes:

- `performance-ceiling-analysis`: analytical, empirical and Amdahl levels; LLM-Viewer1893e4b, ERT0771fa9, TensorRT-LLMf33e0e5fd lineage. Missing target NPU/B300 measurement evidence stays missing.
- `optimization-search-policy`: SkillOpt/vllm-evolve/RRSI methodology.
- `inference-benchmark-design`, `dense-performance-evidence`, `kernel-writing-guide`, `inference-optimization-casebook`.
- `host-overhead-profiling`, `host-overhead-optimization`.

These names are merge destinations confirmed by the inventory, not proof the underlying current files were inspected. No live repository links/anchors are fabricated.

## P: incremental links to add, after reconciliation

Only two official matrix destinations are proposed: `docs/reference-matrix.md` and `docs/searchspace-matrix.md`. Add Pack A paper provenance/methodology to Reference Matrix §2. Link existing skills to this pack's [readset](../READSET.md), [mechanisms](../MECHANISMS.md), [bounds/predictions supplement](../knowledge/bounds-predictions-and-decisions.md) and [cases](../cases/decision-cases.md). SearchSpace can cross-link these gates where an existing mechanism needs them, without adding hardware coverage from a methodology paper.
