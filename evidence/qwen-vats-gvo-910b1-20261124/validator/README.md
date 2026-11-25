# Frozen evaluation and replay

The [packaged task at the measured revision](https://github.com/InferMatrixLab/InferRSI/tree/f5b9a1819d387e0a0a1a219da6dcc0f5504c4069/src/inferrsi/benchmark/tasks/qwen21-denoise-npu)
owns every input, five correctness cases and the three timing cases. Its
`optimization.py` checks source identities, per-step trajectory error, sample
counts, timing medians and the geometric mean. Every candidate and final is
compared with the original denoiser. A final requires a fresh evaluation, a
complete numerical result and verified process cleanup. The VATS final also
requires a durable overall PASS and promotion of the selected candidate.

Hardware replay uses the command and environment in the
[design document](../../../docs/speculative-search.md#measuring-the-contribution-of-gvo).
Supply a fresh directory. RunStore operation identities and hardware timings vary
between replays. The trial index records the actual files from this run.

For offline re-assessment with the original raw files, run the following from
the checkout with the directory produced by the hardware run and its retained
initialization failure. The checker verifies the frozen protocol hash before
running it in the isolated protocol process. It compares each VATS final claim,
promoted incumbent and settled receipt with the selected candidate and the
retained measurement, then checks all nine independent finals and paired ratios
before printing the trial index.

```bash
PYTHONPATH=src python evidence/qwen-vats-gvo-910b1-20261124/validator/check.py \
  <completed-trial-directory> <failed-initialization-trial-directory>
```

The original RunSpec pins the driver that produced the measurements. When using
the unpacked original archive, preserve its `config/run.py` next to the
`output-allocated/` and `output/` trees. If those directories have moved, pass
`--historical-driver /path/to/config/run.py`. The current driver retains its
own bytes in each new trial directory. Its summary also records incomplete
and unrun arms, which prevent publication of paired results.

For trials made with the current driver, each VATS claim and its settled final
operation must carry the same rule. It requires every check to pass with verified cleanup
and applies no additional score threshold. The checker also recognizes the pinned driver
from [the previous revision](https://github.com/InferMatrixLab/InferRSI/blob/b974554199cb10759da03a75f333e608c91d7395/evidence/qwen-vats-gvo-910b1-20261124/plan/run.py).
The recorded promotions from older drivers remain historical results.
