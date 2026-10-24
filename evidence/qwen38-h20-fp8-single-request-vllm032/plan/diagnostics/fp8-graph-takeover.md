# FP8 dispatch and graph correctness diagnosis

Status: INCONCLUSIVE; diagnostic preparation, not an acceptance freeze.
Authority: owner continuation on 2026-10-22; governing acceptance Issue #67.
The owner requests actual FP8 path verification and graph correctness repair,
followed by a reviewable acceptance freeze and itemized GPU budget.

## Bounded first contrast

- Plane: harness-only observation; the engine remains unchanged.
- One physical H20-family GPU, one process, at most 20 minutes (0.333 allocated
  GPU-hours). No multi-GPU allocation, server, benchmark, dependency installation,
  quality scoring, or performance candidate search.
- Existing official FP8 checkpoint and candidate runtime; inspect source,
  model/config identities, installed versions, GPU identity and all cache paths.
- The three historical screening prompts with reported graph/eager divergence:
  GSM8K test 783, 1 and 424. At most 16 teacher-forced decode steps per prompt.
  All paths consume identical tokens selected from compact eager execution.
- Compare compact eager, fixed-capacity eager, and fixed-capacity CUDA Graph.
  Record prefill outputs, layer boundaries, live state, capture restoration,
  decode logits, greedy choices and exact equality; numerical distances remain
  diagnostics, not substitute acceptance thresholds.
- Identical fixed-capacity eager/replay results isolate shape/layout effects.
  A difference between them triggers capture/state/address investigation.
- Retain every partial result and failure. Timeout is INCONCLUSIVE. No changed
  threshold or post-result sample exclusion. Exit ends the Slurm allocation;
  no background child services are launched.

The full baseline/search/finalization budget and statistical/retrieval freeze
remain pending owner confirmation. This contrast cannot establish parity.

## Prospective correctness repair contrast (2026-10-23)

The owner approved the 20-minute single-GPU diagnostic cap. The metadata failure
and initial contrast used 6 + 82 allocated GPU-seconds. The initial contrast
found replay equal to fixed-capacity eager at all 48 steps; the prefill layout
changed outputs before capture. Preserve the first contrast and its limitations.

After CPU regression, spend at most another three allocated GPU-minutes on the
same three prompts / 16 forced steps, changing only the model plane: initial
prefill attends to its current K/V operands while populating fixed decode
storage. The capture and FP8 implementation remain unchanged. Retain all
numerical differences; neither exact equality on these samples nor successful
CPU tests establish full-service or task-quality acceptance.
