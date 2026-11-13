# Bounded tuning and validation

Read before comparing configurations or accepting a scheduler/cache/backend change. Commands are checked against this source snapshot; runtime commands require an already provisioned compatible environment. The candidate was not GPU-tested.

## Reproduction contract

Record commit, clean/dirty state and patch; installed package versions; model/tokenizer/draft revisions; accelerator count/model/memory, driver/toolkit and interconnect; dtype/quantization/KV layout; resolved flags and environment overrides; request dataset hash, lengths, shared-prefix and multimodal distributions; arrivals/concurrency; seed, output caps/EOS and sampling; warmup, cache state and repetitions.

Keep correctness thresholds, latency SLOs, failure allowance and a finite experiment budget explicit. Use completed requests/tokens when computing useful throughput; report errors/timeouts rather than silently removing them. Compare p50/p95/p99 TTFT, ITL/TPOT and end-to-end latency alongside queueing, throughput, memory and cache/speculation data. Client saturation and tokenization can cap the observed rate.

## Commands

Run from the repository root for source commands. For runtime examples, replace `/path/to/model` with the approved local model/tokenizer and choose a unique result path. Commands below are identical in the two language trees. Do not install the heavyweight stack just to run help.

Source identity and the reviewed CPU-only repository check:

```bash
git rev-parse HEAD
git status --short
python -B scripts/lint/check_registered_tests.py
```

The check scans test registrations/entry points without importing SGLang's runtime. It does not execute model tests. [E35](source-map.md#e35)

In a compatible installed environment, inspect command help and launch a one-device baseline:

```bash
sglang version
sglang serve --help
sglang serve --model-path /path/to/model --host 127.0.0.1 --port 30000 --tp-size 1
```

`sglang serve` is the current preferred entry point; `python -m sglang.launch_server` is retained with a deprecation warning. Field CLI names are derived from declarations. Resolve the model/backend compatibility before adding knobs. [E28](source-map.md#e28), [E29](source-map.md#e29), [E34](source-map.md#e34)

A bounded synthetic serving trial against that server:

```bash
python -m sglang.benchmark.serving --backend sglang --base-url http://127.0.0.1:30000 --model /path/to/model --dataset-name random --random-input-len 256 --random-output-len 64 --num-prompts 64 --request-rate 4 --max-concurrency 8 --seed 42 --warmup-requests 4 --output-file sglang-baseline.jsonl
```

This is an example load, not a recommended production load or a completed benchmark. The source caps concurrency separately from arrival rate; the achieved arrival rate may be lower under the cap. Its warmup/cache-flush behavior must be recorded when comparing cold versus prefix-reuse experiments. Use a representative request trace after a synthetic smoke run. The old `sglang.bench_serving` name is a deprecated wrapper. [E24](source-map.md#e24), [E25](source-map.md#e25), [E30](source-map.md#e30)

Kernel/model forward timing and a source-provided correctness entry point:

```bash
python -m sglang.benchmark.one_batch --model-path /path/to/model --batch-size 1 8 --input-len 256 --output-len 64
python -m sglang.benchmark.one_batch --model-path /path/to/model --correctness-test
```

These exercise a narrower boundary than online serving. The full `--correctness-test` spelling is in the parser; avoid depending on shortened argparse abbreviations in old examples. Compare to a matching numerical/model reference and do not treat printed output as a comprehensive pass. [E26](source-map.md#e26)

With development dependencies installed, a focused CPU inventory test can precede GPU tests:

```bash
python test/registered/unit/kernels/test_kernels_namespace.py
```

“CPU test” does not mean “no Python runtime dependencies”: package import may still require PyTorch and other dependencies. This test was not run in the extraction environment. [E36](source-map.md#e36)

## Search a small valid space

| Hypothesis | First controlled dimension | Required counter-observation |
|---|---|---|
| Long prefills disrupt decoding | Chunk size / prefill token budget | Decode tails, prefill TTFT, total completed throughput, workspace peak |
| Admission exceeds useful KV capacity | Running-request limit / static fraction | Queueing and OOM/retraction rate, fairness, peak memory |
| Prefix reuse is worthwhile | Cache policy and explicitly cold/warm traffic | Saved prefill versus transfer/wait cost, hit correctness |
| Speculation pays for its overhead | Compatible algorithm and draft budget | Accepted tokens versus draft+verify work, memory and end-to-end SLO |
| Communication limits scaling | One valid topology/backend dimension | Per-rank utilization, collective time, output equivalence, total-hardware baseline |

Start with a baseline and a few justified points, not a Cartesian product of every flag. Reject source-invalid combinations before launch. After the single-family effect is measured, test a small interaction set. Keep raw artifacts and failures, repeat promising pairs, rank only feasible candidates, and stop at the declared budget. New algorithms are research extensions with separate ablations and correctness arguments.

## Correctness gates and limits

| Gate | Check | Status for this candidate |
|---|---|---|
| Source/static | AST syntax, flag declarations, test registration, pinned evidence ranges, graph links and bilingual command parity | Performed during construction; see external report |
| CPU semantics | Current config/registry/cache unit tests in the proper environment | Only the standalone registration checker and a linter recovery fixture ran; runtime units remain unverified |
| Model and cache | Numerical/logit reference; miss/hit; partial prefix; eviction/abort; chunk boundaries; SWA/Mamba state | Requires intended runtime/model/hardware |
| Speculation | Baseline sampling/quality equivalence, acceptance/rejection state and target verification | Requires compatible target/draft and runtime |
| Distributed/PD | TP/DP/EP output parity; idle/uneven ranks; transfer/timeout/cancellation; both role settings | Requires actual group topology and transport |
| Performance | Repeated paired trials under the same hardware/workload/SLO; profiler evidence | Not measured; no speedup or best configuration claimed |

Prefill-versus-decode logprob/KL checks test state/functional consistency, while task accuracy measures a different property. Native helpers distinguish uncached, prefill-cache-hit and decode-cache-hit paths; numerical batch dependence can mask a restore bug. Use the native KL guide and model-specific baselines to set meaningful tolerances. [E27](source-map.md#e27)

## Failure recovery

If a command spelling fails, inspect the current parser and provenance rather than substituting a guessed flag. If startup fails, keep the first worker error and resolved configuration; reduce to a known model/backend and one device where appropriate. If correctness fails, freeze performance changes and minimize the input/lifecycle. If throughput varies widely, inspect client load generation, cache state, warmup and interference before increasing the search. Retain the last passing configuration and explicitly report every unexecuted gate.

## Reviewed attention-DP and cache experiment details

For this pin, attention DP must be positive; replica `dp_size > 1` combined with `attn_dp_size > 1` is rejected. TP must divide evenly by attention-DP size; with attention CP, TP must divide by `attn_dp_size * attn_cp_size`. Thus TP=4, attention-DP=2, replica-DP=1, attention-CP=1 passes these arithmetic checks, while TP=3/attention-DP=2 or replica-DP=2/attention-DP=2 does not. These are symbolic validator examples, not certified model/hardware configurations. The hook also divides the effective chunked-prefill budget by attention-DP size, so record post-resolution values. [Validator](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/sglang/srt/arg_groups/parallel_hook.py#L279-L321), [CP constraint](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/python/sglang/srt/arg_groups/parallel_hook.py#L152-L158).

For repeated-prefix/restore validation, use the native [unified-memory HiCache test](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/test/registered/e2e/hicache/test_hicache_unified_memory.py) as a concrete workload/schema reference: it submits `/generate` payloads with `text`, `sampling_params.temperature=0`, `sampling_params.max_new_tokens`, and requested output logprobs. Its sequence primes a target prefix, submits distinct filler prefixes to evict it from device cache, requires a host hit on reload, then compares text/logprobs with a resident-cache reference. Both servers use the same unified-memory mode to avoid changing attention reduction order. Follow its actual model cases and launch settings; it is a two-GPU-large CUDA CI workload that can launch servers/load weights, not a local CPU check.

For a performance adaptation, save exact token IDs/model/tokenizer and request order, measure a genuinely reset cold phase separately from warmed L1 reuse, then pressure L1 enough to require L2 restoration. A high aggregate cache hit rate is insufficient: verify the reported host hit and transfer/wait time. Test L3 only with a configured backend and observed storage hit. Keep output caps, EOS, concurrency and quality fixed. The native test provides correctness evidence when executed, not a ready general-purpose throughput benchmark; service timing and storage-specific instrumentation may need additional work.

Exact further candidates: [allocation/eviction](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/test/registered/unit/mem_cache/test_unified_radix_allocation_eviction.py) and [HiCache dispatch](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/test/registered/unit/mem_cache/test_unified_radix_hicache_dispatch.py) are CPU-registered tests with mocked allocator/cache components and normal SGLang/PyTorch dependencies. [Full-attention KL](https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/test/registered/radix_cache/unified_radix_tree/test_unified_radix_cache_kl_full.py) launches Qwen3-32B with TP2 and is registered for two large CUDA/AMD GPUs. Its threshold is model/test specific. Choose the corresponding SWA/Mamba/MLA suite for other layouts. None of these tests was executed during this refinement; they complement rather than inherit the passing registration linter.
