# Apple silicon playbook: measured lessons for inference engines

**The Apple entries in the InferRSI skill library are source-derived; their
native, memory and performance checks are recorded as `not_run`. This page adds
on-device observations from one Apple M5 Max (40-core GPU, 128 GB) running a
MiniMax-H3 video engine, written so they apply to any Metal or MLX engine.**

The engine-specific story, results table and search-loop lessons are in
[h3-metal lessons](h3-metal-apple-silicon-lessons.md). This page keeps only what
should transfer to another model or engine. Nothing here is an InferRSI
acceptance result.

## Sources and labels

| Label | Meaning |
| --- | --- |
| **public** | In the [h3-metal](https://github.com/zuiho-kai/h3-metal) repository at the commit named in the row. |
| **upstream** | Reported by the [antirez/h3.c](https://github.com/antirez/h3.c) authors in the usage manual carried at h3-metal [`4ba47a3`](https://github.com/zuiho-kai/h3-metal/blob/4ba47a3/docs/USAGE.md); measured on their M3 Max and M5 Max machines. |
| **ledger** | From the h3-metal maintainers' unpublished run ledger; not reproducible from this page. |
| **unverified** | Analysis or estimate made during the work and not re-measured. |

## Where this fills a gap

| Existing source-derived guidance | What it leaves open | Measured observation here |
| --- | --- | --- |
| [h3.c runtime audit](../src/inferrsi/data/skill_library/repositories/h3-c/audit-h3-runtime-residency/SKILL.md), [64 GiB worked preparation](../src/inferrsi/data/skill_library/repositories/h3-c/audit-h3-runtime-residency/references/minimax-h3-apple.md) | Target execution and peak memory unverified; tensor counters are not physical footprint | Process peaks for three configurations, the component that sets the memory floor, and cold-load cost ([Unified memory](#unified-memory)) |
| [MLX lazy evaluation and stream lifetimes](../src/inferrsi/data/skill_library/frameworks/mlx/lazy-evaluation-stream-lifetimes/SKILL.md) | Submission versus completion stated from source; no device timing | CPU encoding and GPU wait measured separately; a large encode cost that did not move wall time ([Metal execution](#metal-execution)) |
| [vLLM Metal cache lifecycle](../src/inferrsi/data/skill_library/repositories/vllm-metal/sub-skills/cache-lifecycle/SKILL.md) | One physical unified pool stated from source; memory pressure not measured | Resident weights evicting other weights from the page cache, with the cold-start cost |
| [Quickstart A/B experiments](quickstart.md) | Generic; no Apple-specific interference sources | Interference seen on a shared Mac and how each was detected ([Benchmarking a shared Mac](#benchmarking-a-shared-mac)) |

## Unified memory

| Observation | Cause | Action | Source |
| --- | --- | --- | --- |
| Peak memory per configuration was needed to tell users which Mac can run which setup. | GPU allocations and the page cache share one physical pool; engine tensor counters do not show the whole process. | Measure each published setup with `/usr/bin/time -l` and read *peak memory footprint*. Publish the peak next to the command. | public ([`dd82d1f`](https://github.com/zuiho-kai/h3-metal/commit/dd82d1fae4814c76a3a29f13d56cb08a7bc6bbd6)) |
| 16–24, 32–36 and 48+ GB tiers were derived from 10.6, 22.9 and 35.1 GB peaks on the 128 GB machine. | No smaller Mac was available. | Label such tiers *inferred* until run on the target size. | public (`dd82d1f`) |
| The memory floor did not fall with resolution. | The video decoder alone needs 9.37 GiB. | Find the largest fixed-size component before promising a low-memory tier; 8 GB machines need a smaller decoder, not a smaller frame. | public (`dd82d1f`) |
| A precision switch that halved decoder time added about 3 GB of peak. | BF16 decoder copies are kept beside the original weights. | Treat speed switches as memory decisions too; the smallest tier leaves the switch off. | public ([`0874042`](https://github.com/zuiho-kai/h3-metal/commit/0874042579f74a4e9ebbaef0056495d5e92322e4)) |
| Keeping the 47 GB text encoder resident made a new-prompt warm clip 2.6 s faster and cold start 3.6 s slower. | The extra resident memory pushed DiT weights out of the page cache. | On unified memory, residency of one model part competes with the file cache of another. Ship such a trade-off as a named profile. | ledger |
| Cold DiT load took about 23 s while GPU work in that phase was 0.61 s. Prefetching all 65.3 GiB of shards with six threads finished in 7.6 s, yet the load still took 24.3 s. | CPU cost of page faults and wiring (about 25 s system time, roughly 3–4 million faults), not SSD throughput. | Before optimizing I/O, record system time and the fault count of the load phase. Prefetch and parallel `pread` into Metal buffers were both tried, gave no gain and were reverted. | ledger |
| The SSD can sustain about 13–14.6 GiB/s for streamed DiT blocks. | Two-slot streaming with uncached reads, overlapped with the current command buffer. | Streaming weights from SSD is a valid low-memory mode; report the read wait not hidden by GPU work. | upstream |
| On M5 the large weights are mapped file-backed (reclaimable); on M3 a copied-buffer path is faster and stays the default there. | Chip-dependent cost of zero-copy weights. | Choose the weight-residency path per chip generation and keep a switch for A/B. | upstream |
| A watchdog reboot occurred when an MLX run at 1344x768, 124 frames used about 66 GB beside other large processes. | Unified memory exhausted; nothing stopped the run. | Wrap every benchmark in a memory guard and start at a small shape. | ledger |
| A guard that killed on *any* swap growth killed two valid runs; one that killed at the *warning* pressure level killed the MLX port during weight loading. | Swap growth and warning-level pressure both occur during normal large loads. | Kill on the critical pressure level or on free memory below half its pre-run value, and record which rule fired. | ledger |

## Metal execution

| Observation | Cause | Action | Source |
| --- | --- | --- | --- |
| CPU encoding of a denoising run was 8.67 s, about 20 ms per MPSGraph BF16 linear call. Replacing those calls with native int8 kernels cut encoding to 0.019 s, but wall time barely changed. | Encoding had already overlapped GPU execution. | Report CPU encode time and commit-to-completion wait separately. Remove encode cost only when it is on the critical path. | ledger |
| Splitting each DiT pass into two ordered command buffers gave 0.5–1.8% on M5. | GPU execution of the first part overlaps CPU encoding of the second. | When encoding is on the critical path, split at a depth chosen by balanced A/B, per chip. | upstream |
| Video decoding took 8.4 s per clip, of which GPU wait was 8.2 s (97%). Parallel CPU unpacking was tried and gave nothing. | The phase is GPU-bound. | Compute the GPU-wait share of a phase before trying host-side overlap or driver tweaks. | ledger |
| A profiler line reported 33 s of decoder time. | It covered the decoder's whole lifetime, including DiT work between clips. Its GPU timestamp counted only the root command buffer and omitted child buffers that MPSGraph schedules. | Use commit-to-completion wait as the GPU-side measure; treat root-buffer timestamps as partial. | ledger, upstream |
| Measured peaks on M5 Max: int8 119.3 TOPS, BF16 61.6 TFLOPS. MPSGraph SDPA reached 92% of the BF16 bound; DiT linear layers 85–99%. | Framework kernels were already near the hardware limit for these shapes. | Run a roofline per kernel before writing custom kernels. Here the estimate was at most 1.14× end-to-end from kernel work, so effort moved to step count and sparsity. | public (README), ledger; 1.14× unverified |
| Metal 4 TensorOps with dynamic symmetric int8 activations and per-channel weight scales: a fixed 512x512 render went from 36.30 s (BF16) to 25.80 s. | TensorOps int8 throughput is about twice BF16 on M5. | int8 TensorOps is the first matmul lever on M5. A coarser variant (one scale per FC2 row) is faster but less conservative, so keep it opt-in. | upstream; public (`9186baa`) |
| A Metal 4 MLP path was 1.3–2.0% faster in isolated real-weight runs but 1–3% slower in a full 50-block pass on macOS 26.5.2; an otherwise identical M5 Max on macOS 26.5 gained 1.4%. | GPU scheduling depends on the OS GPU stack. | Record the macOS build with every result. Accept only on the full pipeline, not on a microbenchmark. | upstream |
| Several switches are on by default on one chip and off on the other (for example a command-buffer wrapper reuse: +1.0–1.6% on M3 Max, neutral on M5). | Different GPU generations reward different scheduling. | Do not carry a tuning decision across chip generations without re-measuring. | upstream |
| A candidate kernel used 42,240 bytes of threadgroup memory and failed only at run time. | The limit is 32 KB. | Build every Metal pipeline before timing so the failure is a build failure. | ledger |
| PyTorch/diffusers could not run the model on MPS. | `aten::_int_mm` is not implemented for MPS. | Check the int8 operator set before choosing PyTorch MPS as a baseline. | ledger (2026-10-24) |

## Benchmarking a shared Mac

| Observation | Cause | Action | Source |
| --- | --- | --- | --- |
| Results drift as the machine warms up. | Thermal throttling. | Alternate variants A/B/B/A so drift cancels; report cold (fresh process) and warm (later clip, same process) separately. | upstream, public |
| A denoise phase ran about 30% slower than usual. | Another user's GPU job (voice conversion) ran at the same time. | Check for other GPU processes before and after each pass; void the run if one appeared. | ledger |
| A pass slowed although the patch did not touch it. | A headless browser and a search process used CPU. See [h3-metal lessons](h3-metal-apple-silicon-lessons.md#measurement-lessons). | If an untouched stage slows clearly, mark the trial interfered and re-run. | ledger |
| A ratio of 3.05× was first reported against the MLX port. | It compared our warm time with the rival's cold time. | Compare cold with cold and warm with warm; the claim was withdrawn. | ledger |
| An auto-filled results table took a cell from an earlier run. | The script cited a log line beyond the end of the file. | Check each published number against its log line. | ledger |

## What we did not establish

- The gap to the MLX port (134.6 s against 29.89 s warm at 20 steps, public)
  was not attributed: the MLX port was not profiled. Do not read the ratio as a
  verdict on MLX.
- All observations come from one M5 Max with 128 GB; M3 rows are the upstream
  authors' reports. No result on 16–64 GB machines.
- No serving load, concurrency, tail latency or long-run thermal steady state.
- Ledger and unverified rows cannot be reproduced from public artifacts.
