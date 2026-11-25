The source campaign retains frozen snapshots, per-invocation logs, quality PNGs and assessment records locally. The public trial export uses timestamp-free step names, decoded RGB hashes, stage durations and scoped verdicts. Model weights and host-specific logs are retained outside the repository.

Measurement invocations check the three frozen RGB hashes. They record empty per-pixel comparisons because the four-image array comparison and changed-seed control run in the two quality invocations. The trial envelope names the invocation or marks the direct timing phase explicitly.
