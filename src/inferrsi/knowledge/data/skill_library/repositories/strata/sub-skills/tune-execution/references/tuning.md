# Controlled tuning procedure

## 1. Freeze the experiment

Use one source/build revision, model/pack checksum, tokenizer and template, hardware topology, driver/toolchain, power policy, workload set, sampling policy and quality gate. Separate cold startup, cold prompt, reused prompt and steady-state decode. Treat expert-cache warmup, OS page cache, MTP acceptance and language mix as experimental state. Fix requested and actual output length or report the difference.

Record VRAM and RAM budgets, including driver allocations, graph captures, scratch buffers, conversation state and pinned pages. SSD-backed mappings reduce committed RAM but do not eliminate the working set or page-fault cost. A long-context or concurrent workload needs its own memory check.

## 2. Select the bottleneck and branch

| Observation | Candidate change | What to measure |
|---|---|---|
| CPU experts dominate the critical path | `--pool-workers`, `--pool-tasks`, `--pool-affinity`; then `--pcie-frac` | CPU task time, H2D bytes/time, window latency; more workers can contend for memory |
| Frequent expert misses | Cache capacity/reserve, placement/profile and adaptation parameters | Actual resident slots, misses, CPU versus transferred misses, swap overhead |
| Long prompt stalls | `--prefill`, quantized matrix path where supported, staged transfers | TTFT, prompt throughput, peak scratch/host memory, decode fairness |
| Long context crowds out experts | `--kv-resident`, `--kv`, `--kv-grow` where supported | Attention/transfer time, expert capacity, context quality and peak memory |
| Drafting is expensive or often rejected | MTP on/off, `--spec`, `--spec-min-p`, draft vocabulary | Emitted tokens per verify window divided by full draft+verify cost |
| Several users queue | `parallel` / `--batch`, admission chunking and group pipeline | Aggregate throughput and p95 latency alongside per-request speed |
| Extra GPUs are available | Layer split versus helper/peer expert placement | Link traffic, stage imbalance, memory duplication and actual overlap |

Raw cache hit rate is insufficient: a different PCIe share changes which misses enter CPU-side statistics. Check the accounting definition and end-to-end latency.

### Built-in hardware calibration

For an already prepared compatible model, run from the Strata checkout root:

```text
python -X utf8 tools/calibrate.py strata-iq2_xs.json
```

This CLI takes exactly one positional config path. It starts the configured native engine, measures candidates, and prints progress plus a final JSON object; it does not save the selected settings back into that config. It still performs real generation, restarts the engine for worker/adaptation candidates, and uses the config's log. Prerequisites are a working GPU/runtime and engine, existing model/pack, valid `exe`/`args`/`cwd`/`tokenizer` paths, Python with `jinja2` for server imports and `regex` for `strata_tokenizer`, and tokenizer `vocab.json`, `merges.txt`, `token_type.json`. Use a free test window and sufficient memory; this is not a no-GPU or short smoke command.

The current routine sweeps `--pcie-frac` (0, 0.2, 0.35, 0.55, 0.75, 0.9, 1 plus the detected default), `--spec-min-p` (0.3, 0.5, 0.7 plus the default), CPU worker counts, and adaptive-tier `(every, swaps, decay)` alternatives `(1,80,0.97)` and `(1,160,0.97)` against the engine default. PCIe/draft sweeps use three alternating rounds and an interleaved confirmation; worker/tier candidates require restarts. `MIN_GAIN=0.03` keeps a candidate only when its median decode rate beats the comparison default by more than 3%. This is a heuristic to screen noisy speed measurements, not statistical confidence, output-equivalence testing, or a quality bound. The objective is decode only; prompt TTFT, concurrency, long-context quality, and memory need separate validation. Its three prompts are in English, including one Python task; they do not represent Chinese or other target domains.

To deliberately persist calibration for an installed model, setup provides:

```text
python -X utf8 setup.py --calibrate --family qwen --model IQ2_XS --no-start
```

Select an actually installed family/model. Setup writes config `args` and remembers settings per hardware/model/context/vision identity; unchanged tuned flags return to product defaults, so save the previous config before applying it. `--no-start` prevents the final server launch, but this setup branch may update the installed engine before calibration. For an experiment that must preserve the exact engine revision, use the standalone tool and review its output first. `--calibrate` is ineffective together with `--setup` or `--check`, or before any model is installed. Evidence: `tools/calibrate.py:1-53,102-162,202-295,325-343`, `tools/strata_tokenizer.py:22`, `setup.py:4732-4773,5893-5918`. Keep this repo-coupled utility in the matching checkout rather than bundling a second copy into the skill.

## 3. Use a small conditional search

These are proposed starting experiments, not upstream defaults or guaranteed legal configurations. Inspect the chosen engine family's parser and resolved startup log before use.

- First hold weights, KV format, approximate expert skipping and all model semantics fixed. Compare the working baseline against one change at a time.
- For a single discrete GPU with RAM-resident experts, a coarse `--pcie-frac` trial set such as 0, 0.25, 0.5, 0.75 can diagnose the balance. Avoid a universal recommendation; PCIe topology and CPU bandwidth decide the result. An explicit value overrides automatic tuning.
- Sweep a few CPU pool sizes derived from physical/performance cores. The host may participate in work, so `--pool-workers N` is not necessarily the total thread count.
- Compare prefill chunk sizes such as 1024, 2048, 4096 and `auto` only when they fit. `auto` is platform-sensitive; Windows HIP may cap it and some gfx12 paths enlarge it. Decode and prefill should not share one objective blindly.
- With a compatible prepared MTP artifact, compare no MTP against verify-window budgets `--spec 2` and `--spec 4`; this value is not simply the number of draft tokens. Record suffix/prompt-lookup policy too, since it can alter effective windows. The engine option is `--mtp <path>`, not a bare switch.
- Explore KV `fp16`, `int8`, `k8v4` and `q4_0` only in the relevant backend/model path, with separate quality gates. Changing KV format defines a different numerical experiment.
- Add a second slot only after checking memory. It can reduce queueing while decreasing solo decode speed. Compare concurrency at the same offered load.
- Only after individual effects are understood, test coupled groups: KV residency × expert slots, MTP head × cache capacity, CPU threads × PCIe share, and batch groups × draft policy.

Prefer a staged random or Bayesian search over a flat Cartesian product. For code changes, constrain the AI to one mechanism/interface and use compile/parity gates before expensive end-to-end runs. These search algorithms are proposed methodology, not a Strata feature.

## 4. Preserve compatibility constraints

- Raw engine, installer and server configuration options differ. For example, installer `--parallel N` writes server `parallel`; the engine uses `--batch N`. Installer `--draft-vocab en` selects an artifact; the engine's `--mtp-draft-vocab` takes a file.
- A layer-split `--batch-groups G` requires G to divide the slot count. Pipelined groups can turn off batch MTP or asynchronous adaptation. Read `INFO batch_groups`, `INFO batch_slots` and explanatory logs; more requested slots can be reduced by memory or row limits.
- `--vram-elastic` is a restricted NVIDIA serving feature, not a general cross-backend allocator. Layer split, helper/peer configurations, resident modes and active batch work impose additional restrictions. A successful resize response can still miss the requested reserve; inspect returned free memory.
- Asynchronous adaptation must not overwrite cache slots still used by an in-flight window. Preserve copy-ready and consumer-complete events, pinned-buffer lifetimes and ownership mappings.
- `--mmap-experts` is not equivalent to all experts being in RAM. `--resident-experts` attempts to keep the complement of GPU residency in RAM; verify the actual mode and headroom.

## 5. Gate quality and measure

Run relevant parity/state checks, then interleave repeated baseline/candidate runs (for example ABBA), with warmup and cache state controlled. Keep a held-out prompt set, including Chinese and code when those are intended workloads. Report medians, dispersion, sample counts and p95 request latency where concurrency matters. A fast microbenchmark is only a screening signal.

For a stronger diagnostic baseline, consider explicitly disabling quality-sensitive paths such as `STRATA_ROUTE_TAIL_SKIP=0` and `STRATA_PREFILL_CPU_SHARE=0`; record that this is a different baseline from upstream defaults. Controls such as `STRATA_IQ_MT_MIN=1`, `--prompt-cache 0`, `--adapt-swaps 0` and `--pcie-frac 0` can reduce sources of repeat-to-repeat variation, but do not prove bitwise equivalence across devices or different arithmetic paths.

Use the [trial CSV contract](../../../references/trial-format.md) and [summarizer](../../../scripts/summarize_trials.py) only after the actual validator has assigned `quality_ok` and `valid`. Keep model, compiler and configuration metadata in the experiment manifest; do not turn a failed or truncated run into a winning throughput number.

## Recovery

- OOM: inspect actual slot/chunk/KV/cache allocations; reduce the responsible component and restore the baseline before continuing. Do not shrink output or context silently.
- Low acceptance: inspect token-language coverage and draft cost before increasing speculation.
- No gain from overlap: inspect synchronization and bus saturation; overlap only helps off the critical path.
- Quality regression: isolate approximate mechanisms and CPU/GPU arithmetic differences, save logits/counterexamples, and exclude the candidate until the agreed gate passes.
- Feature silently absent: use resolved startup logs and supported parser options; downgrade the conclusion to “requested but not active.”

## Pinned evidence

- [Engine parser and execution gates](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/src/program/generate.cpp): options near 1890–2230; tail-skip policy near 8618.
- [Batch group resolution](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/program/batch_groups.hpp).
- [Native benchmark client](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/tools/strata_bench.py): client TTFT versus engine timing, repeated tests and comparison options.
- [Hardware calibration routine](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/tools/calibrate.py): bounded decode sweeps, restarts, confirmation and 3% selection threshold.
- [Elastic VRAM contract](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/docs/VRAM_ELASTIC.md).
- [Asynchronous expert exchange ownership](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/core/expert_source.hpp).
