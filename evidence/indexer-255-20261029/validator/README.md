# Frozen evaluator

- Runner: `tools/evaluate_indexer.py`, SHA-256 `ea5b91ff17e80a422fd373621528dfe74ff144976bb55d6432501df452757ca5`.
- Development cases: `tests/fixtures/indexer/development.json`, SHA-256 `cdaa0f020281a689b38015cf33932c5681b46b84053c3f9666effb32914c96b2`.
- Independent held-out commitment: `10e13080cfb4d27de40dc92166c261cf6ccf47776d08111f2e85d7c8edc2d19f`; four cases created by a separate source reviewer without retrieval observations and withheld until candidate code freeze.
- Protocol: `../plan/protocol.json`, SHA-256 `e4964329a20e6752b8149ab270733c0bbb258d0f948bdca9e86da6fe8f028956`.

Protocol accepted prospectively in [Issue #255](https://github.com/InferMatrixLab/InferRSI/issues/255#issuecomment-6496822362). Runner/development hashes communicated to the coordinating reviewer before candidate edits. Baseline smoke checks all six contracts and exact API/CLI output equality. Smoke timings are diagnostic, **not** the controlled comparison.

One fixed efficiency candidate, no ranking changes and no held-out tuning. Contract/accuracy results remain separate from timing verdict. Partial labels cannot establish corpus Recall or exhaustive Precision. A miss is reported, not relabeled.

## Separate prospective confirmation

`confirm_cli_search.py` and `../plan/confirmation-v2.json` define one focused 120-pair CLI-search replication plus 40 baseline/baseline diagnostic pairs. It neither replaces nor pools with the original FAIL. Its hashes and approval receipt must precede execution; all results and uncertainty are reported separately.

Confirmation v2 protocol SHA-256 `40de4eefba8712d3d07f2e48049b0899c831f94bfcfa252c1f8841525a337fa4`; wrapper SHA-256 `b11b4cf08b6dceb43be447516d5abb740bb2de8c2fdfd7a9ee3f820a1174b55d`. Prospective receipt: https://github.com/InferMatrixLab/InferRSI/issues/255#issuecomment-6497690434. Exactly one run completed; point PASS is distinct from v1 FAIL and does not remove uncertainty.

`frozen_evaluate_indexer.py` is the byte-identical v1 evaluator snapshot (same `ea5b...` hash). It remains replayable if the generic runner later evolves; invoke it with the same arguments. The confirmation wrapper intentionally checks the exact v1 generic-runner hash and refuses a changed evaluator rather than silently replaying different logic. Restore the snapshot in an isolated reproduction checkout when replaying that wrapper.

`verify_raw_archives.py` validates the original and compressed hashes and can reconstruct every original JSON path under an explicit destination. `supplemental_required_audit.py` accepts plain/gzip inputs and is a portable post-run adaptation of the independent audit, not a prospectively frozen gate.
