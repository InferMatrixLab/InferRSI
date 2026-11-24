# Matched VATS and GVO deployment on one Ascend 910B1

This Engine diagnostic for [InferRSI #363](https://github.com/InferMatrixLab/InferRSI/issues/363)
compares a fixed-order serial control, frozen VATS and VATS after one GVO update
on the packaged Qwen-Image 2.1 denoiser. The underlying search and task code was
[f5b9a18](https://github.com/InferMatrixLab/InferRSI/tree/f5b9a1819d387e0a0a1a219da6dcc0f5504c4069).
The [design document](../../docs/speculative-search.md#measuring-the-contribution-of-gvo)
explains the comparison and reports the independent-final results.

- [Frozen plan](plan/plan.json), [driver](plan/run.py) and [RunSpec](plan/runspec.json) identify the exact edits, weights, workload, ordered seeds, evaluation caps, runtime and task file hashes.
- [Summary](results/summary.json) contains every online result, the shared root and training durations, the before/after weights, group returns and paired aggregates.
- [Trial index](results/trials.jsonl) records every physical task evaluation, its selected source hash, verdict, task-result hash and path inside its attempt directory.
- [Local archive metadata](results/local-archive.json) gives the size and SHA-256 of the 725-file raw bundle retained in the shared experiment workspace. The public PR provides the compact inputs and results.
- [Candidate sources](patch/README.md) and [verification instructions](validator/README.md) explain how to regenerate the experiment and re-assess its retained measurements.

The task uses random BF16 weights, five numerical cases, three latency cases and
fixed workload seeds. Each complete evaluation runs two paired AB/BA blocks
with two timed samples per block and one warmup per arm and case. The score
is the geometric mean of the three original-baseline/candidate median latency
ratios. The frozen quality gate checks trajectory steps and weight updates.

Before successful qualification, the first container could not initialize its
allocated device. That root attempt produced an infrastructure failure with
verified cleanup and no score. All methods and input hashes were retained when
the job was relaunched with the known working allocator/container mapping.
The initial failure, queueing, container startup and experimental setup sit
outside the reported online arm times. Root acquisition and GVO collection plus
the gradient update have separate measured costs. Each online arm includes its
own independent final. The final repeats the same workload. Transfer to new prompts or tasks and
variability across independent training runs remain unmeasured.
