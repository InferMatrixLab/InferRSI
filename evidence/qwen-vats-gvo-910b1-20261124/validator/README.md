# Frozen evaluation and replay

The [packaged task at the measured revision](https://github.com/InferMatrixLab/InferRSI/tree/f5b9a1819d387e0a0a1a219da6dcc0f5504c4069/src/inferrsi/benchmark/tasks/qwen21-denoise-npu)
owns every input, five correctness cases and the three timing cases. Its
`optimization.py` checks source identities, per-step trajectory error, sample
counts, timing medians and the geometric mean. Every candidate and final is
compared with the original denoiser. A final requires a fresh evaluation, a
complete numerical result and verified process cleanup.

Hardware replay uses the command and environment in the
[design document](../../../docs/speculative-search.md#measuring-the-contribution-of-gvo).
Supply a fresh directory. RunStore operation identities and hardware timings vary
between replays. The trial index records the actual files from this run.

For offline re-assessment with the original raw files, run the following from
the checkout with the directory produced by the hardware run and its retained
initialization failure. The checker repeats the packaged assessment, binds final
score and selected source to the run summary, and prints the compact trial index.

```bash
PYTHONPATH=src python evidence/qwen-vats-gvo-910b1-20261124/validator/check.py \
  <completed-trial-directory> <failed-initialization-trial-directory>
```
