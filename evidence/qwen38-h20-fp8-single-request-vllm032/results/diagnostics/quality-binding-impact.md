# Prospective evaluator provenance binding

Refs [Issue67](https://github.com/InferMatrixLab/InferRSI/issues/67).
**INCONCLUSIVE — reviewed harness repair; no acceptance activation or E2E gain.**

The previous comparator returned task-quality PASS for three fabricated count
summaries with absent or different runtime/qualification identities. These were
direct comparator fixtures, not model answers or real sandbox results; they do
not establish that the complete scorer accepted a mismatched real execution.
The previous scorer also omitted sandbox identity from its summary.

Version5 requires a separately frozen evaluator protocol and qualification
artifact for completed HumanEval+ scoring and comparison. The protocol identifies
the readonly bind set (not an invented OCI image), evaluator revision, executor,
driver, sandbox binary, policy and qualification. Each side retains its own
execution and result hashes; samples/results may differ. Both sides must match
the independently supplied expected protocol. Pairwise equality alone is
insufficient. Export without evaluation remains possible and incomplete.

Protocol, qualification, execution record, HumanEval results and comparison
summaries are parsed and authenticated from the same byte snapshot. Duplicate
provenance keys are rejected. The comparator requires seven correctly formed
per-arm evidence digests. The source preparation inventory and validator identity
also authenticate the new provenance module. Prompt construction, natural EOS,
task counts and accepted quality thresholds are unchanged.

Independent review rejected the initial version for three P2 issues: the new
module was missing from the preparation manifest, authentication and parsing
reread the protocol/qualification files, and comparison allowed absent execution
and result digests. All three were corrected and the exact four changed source
files reviewed again. Rejected source identities and control results are retained;
older validators and historical evidence remain unchanged.

Local validation:117 provenance controls and6 full synthetic export/score controls
passed under optimized Python;35 existing protocol,7 preparation guard and3 new
manifest tests passed under pytest. The19 EOS controls and30 retained retrieval
streams also passed. The new repeated-read control initially reused an exclusive
output pathname and failed with FileExistsError; a distinct output fixed the
fixture. Targeted source/control Ruff checks passed after import/format cleanup.
No full-directory lint claim is made for unchanged legacy diagnostics.

The control scripts are retained under patch/diagnostics. Set QUALITY_SOURCE_DIR
to the reconstructed v5 directory for both standalone check scripts and guard
pytest. For the guard test, set QUALITY_REFERENCE_TEST_DIR to the authenticated
original test_prepare_guard.py directory; its digest is recorded in the inventory.
The controls use fabricated data and never execute generated code. Qualification
fixture PASS values are not qualification artifacts.

This repair authenticates selected identities and report scope; it does not by
itself establish host isolation, anti-cheating, aggregate resource limits or
cleanup. No actual qualified generated-code executor report exists. It must be
independently reviewed before its bytes are accepted into the eventual freeze.
The complete runtime, commands and validator bundle still need freeze, alongside
the owner's pending statistical/retrieval decisions. No GPU work, held-out task
reading, evaluator execution or measurable service performance change occurred.

KnowledgeStore candidate `case.qwen38-quality-activation-gaps-cand`: `sha256:bb6879aead15810a26d83fa05ff4f6332011bd9c911a4c85962e00bfc114da9f`; readback verified, previous attempts retained.
