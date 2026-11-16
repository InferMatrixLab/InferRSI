# Qwen3.8 FP8 single-request evidence

Acceptance: [#67](https://github.com/InferMatrixLab/InferRSI/issues/67).
**Campaign verdict remains INCONCLUSIVE.** Both frozen paired performance parity gates failed; task quality, retrieval and final acceptance remain incomplete.

This explicitly requested cleanup preserves the 413 previously public
files (5,205,664 bytes) at `6c7e237935a22cc5e90e954d4f397376e753e7d8` unchanged in a
versioned archive. It moves cumulative checkpoints, repeated diagnostic source
copies and generated details out of the current tree. The original README,
failed/interrupted attempts, superseded observations, all patches and frozen
validators remain at their original paths inside the archive. No model run,
historical gate, result or original byte was changed.

## Retained evidence

- [Summary](results/summary.json): key recorded conclusions, sample distributions
  recomputed from published samples, and explicit coverage/availability limits.
- [Index](results/trials.jsonl): 130 published record/attempt observations;
  every row has configuration references, status, conclusion, archive identity
  and an archive-relative JSON Pointer. These are not independent trial counts.
- [Archive authority](results/artifacts.json): v2 URL/hash/size/source/retention
  and pinned replay inputs. The inventory references this document.
- [Plan](plan/README.md), [patch](patch/README.md) and [validator](validator/README.md).

Identical observations of the same named attempt collapse to one row with all
`source_records`. Different observations of that attempt, retries and anonymous
records remain separate. Historical revisions are not replaced by the latest
checkpoint. Unpublished attempts cannot be reconstructed; Markdown-only history
and per-request JSONL remain in the original archive. Passing archive checks
does not complete the campaign or turn individual engineering results into PASS.

The [original tree](https://github.com/InferMatrixLab/InferRSI/tree/6c7e237935a22cc5e90e954d4f397376e753e7d8/evidence/qwen38-h20-fp8-single-request-vllm032/)
is another immutable reference. This change does not rewrite Git history.
