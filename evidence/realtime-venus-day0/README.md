# Realtime-Venus day-0 adaptation

- Governing [acceptance issue](https://github.com/InferMatrixLab/InferRSI/issues/593).
- [Experience and limitations](../../docs/realtime-venus-vllm-omni.md).
- [Frozen task](plan/TASK.md), [validator](validator/README.md),
  [source pointer](patch/README.md), [results](results/summary.json) and the
  complete managed-round [step index](results/trials.jsonl).
- The [full-duplex follow-up](plan/duplex-followup.md) has separate
  [functional results](results/duplex-functional.json) and a public
  [archived lifecycle probe](validator/duplex_lifecycle.py). For new runs, use
  the [revised probe and replay prerequisites](validator/README.md), which
  document the archived gate's limitations. These checks do not change
  the frozen HTTP performance experiment or establish a duplex speedup.
- Overall verdict: **INCONCLUSIVE**. This compact bundle does not establish
  full model parity, perceptual speech quality or a general performance claim.
- The operator retains original logs, media and managed snapshots locally.
  No public archive is available. The public scripts and compact results permit
  inspection of the protocol, but exact original execution is not independently
  replayable from this bundle. No archive URL or verification is invented.
