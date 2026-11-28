# Validation cookbook

Source snapshot: [Niko1221/Strata at 296b59d2f73c8f04a805df29c2fa97655adace78](https://github.com/Niko1221/Strata/tree/296b59d2f73c8f04a805df29c2fa97655adace78). Commands below run from that checkout's root. Replace example configs and executable paths with existing local ones. The examples are source-checked command recipes; they do not assert that a particular machine has passed them.

## 1. Establish the environment without installing the engine

Python scripts need Python 3.10+; `requirements.txt:1-22` pins environment dependencies. `setup.py:1-21` installs packages, retrieves/builds the engine, downloads models, prepares packs and starts the server. It is not a Python package's build entry point. Do not infer `pip install .`, `pip install -e .`, or a `strata` Python import from its name.

For an existing environment, record:

```text
git rev-parse HEAD
git status --short
python --version
cmake --version
```

Check installed Python dependencies before choosing tests. Installation is a separate preparation step, normally `python -m pip install -r requirements.txt` inside a dedicated environment. The runtime/build packages in that file are unnecessary for the standard-library-only candidates below. Do not install the entire environment merely to run them.

## 2. No-GPU Python checks

```text
python tools/test_source_nul_bytes.py
python tools/test_setup_amd.py
python tools/test_setup_choices.py
python tools/test_setup_pins.py
python tools/test_strata_bench.py
```

These use the Python standard library and repository modules. Setup tests mock hardware/network; the benchmark test uses a temporary loopback HTTP server. They need no model or GPU. They cover source integrity, setup decisions and pinning, and the measurement harness, not GPU inference. Evidence: `AGENTS.md:20-21`, `tools/test_setup_amd.py:1-17`, `tools/test_setup_pins.py:1-25`, `tools/test_strata_bench.py:1-18`.

On Windows with a GBK or other non-UTF-8 default locale, repository code using `Path.read_text()` without an encoding can fail while reading UTF-8 sources. Use UTF-8 interpreter mode for these commands, for example `python -X utf8 tools/test_strata_bench.py`. Preserve the original failure log and distinguish this environment workaround from an upstream source fix.

Server boundary tests add `jinja2` and use mock engines plus a byte tokenizer:

```text
python -m unittest serve.test_request_accounting serve.test_context_overflow serve.test_security
```

`serve/frontend.py:28-29` imports Jinja2; `serve/test_request_accounting.py:11-13`, `serve/test_context_overflow.py:11-12`, and `serve/test_security.py:19-20` identify the mock/test paths. A mock-server pass does not validate tokenization or native generation with real model weights.

The calibration harness also has CPU tests: `python -X utf8 -m unittest tools.test_calibrate`. These use a fake engine, but their server-argument integration branches import `serve.server` and therefore require `jinja2`; they are not entirely standard-library-only. Running the actual `tools/calibrate.py CONFIG` additionally needs `regex`, tokenizer artifacts, the native GPU runtime, engine and real model. See the [calibration procedure](../../tune-execution/references/tuning.md).

## 3. Native CPU checks without a network fetch

Prerequisites: CMake >= 3.24, a C++20 compiler, a build generator, and the checkout. On Windows use a configured MSVC developer shell. `STRATA_NATIVE_EXPERTS=ON` otherwise fetches pinned llama.cpp unless `STRATA_GGML_DIR` points at a prepared llama.cpp source root; turn it off for this narrow CPU lane. The default test switch can be OFF when the published checkout lacks `tests/CMakeLists.txt`, so enable it explicitly.

```text
cmake -S . -B build-skill-cpu -DCMAKE_BUILD_TYPE=Release -DSTRATA_ENABLE_CUDA=OFF -DSTRATA_ENABLE_HIP=OFF -DSTRATA_ENABLE_SYCL=OFF -DSTRATA_NATIVE_EXPERTS=OFF -DSTRATA_BUILD_TESTS=ON -DSTRATA_BUILD_CONVERSATION_TESTS=ON
cmake --build build-skill-cpu --config Release --target logit_bias_test gguf_reader_test model_family_test split_rules_test share_rules_test arch_defaults_test controller_test draft_policy_test conversation_cache_test conversation_split_failure_test message_boundary_test batch_groups_test --parallel 2
ctest --test-dir build-skill-cpu -C Release --output-on-failure -R "^(logit_bias_test|gguf_reader_test|model_family_test|split_rules_test|share_rules_test|arch_defaults_test|controller_test|draft_policy_test|conversation_cache_test|conversation_split_failure_test|message_boundary_test|batch_groups_test)$"
```

Evidence: `CMakeLists.txt:10-11,48-50,97-125,247-291,1161-1210,1303-1315`. This lane intentionally omits native quantized expert kernels. `expert_multi_test` can skip without AVX-512; `expert_parity` requires a real pack (`CMakeLists.txt:1694-1712`). Avoid treating an unfiltered `ctest` with absent fixtures as a useful first smoke test. `bf16_bits_test` enumerates every FP32 bit pattern, and `spec_prob_test` runs millions of trials (`1195-1202`), so neither belongs in the smallest quick lane.

## 4. CUDA build and GPU operators

Prerequisites: matching NVIDIA driver/toolkit, a C++20 toolchain, available GPU, and llama.cpp sources at the pinned revision `3cf03257f219afbe7334045ff7c6a06ac68c627d`. The example targets SM 89 (RTX 40); replace it with the actual device architecture. Default CUDA architecture is 120 if omitted. Pre-SM75 requires the experimental flag and CUDA 12.x; SM120 builds should use CUDA 13+ (`CMakeLists.txt:159-201`). Do not silently apply one GPU's build to another.

```text
cmake -S . -B build-skill-cuda -DCMAKE_BUILD_TYPE=Release -DSTRATA_ENABLE_CUDA=ON -DSTRATA_ENABLE_HIP=OFF -DCMAKE_CUDA_ARCHITECTURES=89 -DSTRATA_BUILD_TESTS=ON -DSTRATA_GGML_DIR=/path/to/pinned-llama.cpp
cmake --build build-skill-cuda --config Release --target strata strata-device native_expert_parity kv_q8_parity kv_q4_parity kv_hybrid_parity route_window_parity verify_batch_parity --parallel 2
ctest --test-dir build-skill-cuda -C Release --output-on-failure --timeout 180 -R "^(cuda_device_selftest|native_expert_parity_.*|kv_q8_parity|kv_q4_parity|kv_hybrid_parity|route_window_parity|verify_batch_parity)$"
```

Use a native local path for `STRATA_GGML_DIR`, including its drive on Windows. Omitting it permits CMake's network fetch; do not confuse a download failure with a kernel failure. Native expert synthetic pairs exercise Q4_K/Q5_1, Q4_K/Q8_0, Q5_K/Q8_0, Q8_0/Q8_0, Q4_K/Q5_0, Q5_0/Q8_0, Q4_0/Q4_0, Q4_0/Q4_1 and, when built, Q6_K/Q8_0. The harness's float-reference threshold is not a universal quality guarantee; one double-Q5_0 pair is deliberately excluded for quantization noise. Evidence: `CMakeLists.txt:950-953,1044-1070,1111-1114,1620-1655`.

For HIP, choose the actual architecture (example `gfx1100`), use a separate build directory, and prepare ROCm/HIP/hipBLAS development files:

```text
cmake -S . -B build-skill-hip -DCMAKE_BUILD_TYPE=Release -DSTRATA_ENABLE_HIP=ON -DSTRATA_ENABLE_CUDA=OFF -DCMAKE_HIP_ARCHITECTURES=gfx1100 -DSTRATA_BUILD_TESTS=ON -DSTRATA_GGML_DIR=/path/to/pinned-llama.cpp
cmake --build build-skill-hip --config Release --target strata strata-device gr_parity gdn_parity kv_q8_parity kv_q4_parity --parallel 2
ctest --test-dir build-skill-hip -C Release --output-on-failure --timeout 180 -R "^(hip_device_selftest|gr_parity|gdn_parity|kv_q8_parity|kv_q4_parity)$"
```

HIP wave64 gfx906 uses the distinct `STRATA_HIP_GFX906=ON` route, not wave32 HIP (`CMakeLists.txt:56-95`). SYCL uses a separate project and oneAPI (`docs/INTEL_ARC.md:105-118`):

```text
cmake -S . -B build-skill-sycl -G Ninja -DCMAKE_C_COMPILER=icx -DCMAKE_CXX_COMPILER=icpx -DSTRATA_ENABLE_SYCL=ON
cmake --build build-skill-sycl --target strata
ctest --test-dir build-skill-sycl -N
```

The last command lists checks; it does not run them. Select existing SYCL tests and run them on the card before claiming validation. Metal, gfx906, old NVIDIA architectures, vision and other optional routes each need their own actual backend evidence; the CUDA/HIP recipes do not certify them.

`ple_parity` needs an external fixture; `platform_memory_test` requests 256 MiB of locked memory. `docs/AMD_HIP.md:669-680` explicitly excludes them on one low-memlock test host. Record this reason for that host rather than copying blanket exclusions or counting them as passes. Verify all backend implementations a changed shared file affects.

## 5. Real-model API and state checks

Prerequisites: an existing compatible model pack, tokenizer, built engine, and config with correct `exe`, `args`, `cwd`, and tokenizer paths. Keep the server on loopback; if exposing it elsewhere, supply `--api-key` as required by the repository. Run in a dedicated terminal:

```text
python -m serve.server --engine strata --config strata-iq2_xs.json --host 127.0.0.1 --port 8080
```

Read `/health`, verify `loaded: true`, then `/v1/models`. Send a deterministic short request to `/v1/chat/completions` with `temperature: 0`, `max_tokens: 64`, `reasoning_effort: "none"`, and a fixed user prompt; save the complete response and timings. For key-protected endpoints provide the configured bearer key without writing it into reports. Source: `serve/server.py:6623-6646`, `docs/AI_SETUP.md:147-164`.

Cache parity tests run the engine themselves; create the `results/` parent first, use a new output directory, and inspect the default dry plan before `--run`:

```text
python tools/conversation_cache_parity.py --config strata-iq2_xs.json --engine build-skill-cuda/strata --output results/cache-reuse --scenario reuse
python tools/conversation_cache_parity.py --config strata-iq2_xs.json --engine build-skill-cuda/strata --output results/cache-reuse --scenario reuse --run
```

Select an existing executable path; Windows multi-config generators often put `strata.exe` under `Release/`. Other scenarios are `pressure`, `oversized`, `exchange`, and `admission`; budget the default 8192 MiB cache and the minimum-free-memory check before choosing them (`tools/conversation_cache_parity.py:153-166`). Never run memory-pressure tests on an undersized host merely to fill a matrix.

Cancellation on a running test server:

```text
python tools/early_close_test.py http://127.0.0.1:8080
```

This closes a stream early, then checks that the next response has no stale tokens, in solo and background-request cases. It is a semantic smoke check, not full token equivalence; for API-key auth the script reads `STRATA_KEY` (`tools/early_close_test.py:1-47`).

Native concurrent-slot checks:

```text
python tools/batch_test.py --exe build-skill-cuda/strata --config strata-iq2_xs.json --batch 4 --n 4 --max-new 64 --extra "--pcie-frac 0 --adapt-every 1000000 --no-prefill-borrow" --dump results/batch-tokens.json
python tools/batch_interleave_test.py --exe build-skill-cuda/strata --config strata-iq2_xs.json --max-new 200 --long 5000 --extra "--pcie-frac 0 --adapt-every 1000000 --no-prefill-borrow"
```

Create the output parent directory first. These launch their own engine and need enough memory for batch slots. The scripts set `STRATA_IQ_MT_MIN=1`; disabling prompt borrowing and transfers stabilizes CPU/GPU placement for exact comparisons. Production routing can round differently (`tools/batch_interleave_test.py:17-21`), so follow exact-path checks with production-config task checks.

## 6. Performance and quality are separate measurements

```text
python tools/strata_bench.py --config strata-iq2_xs.json --runs 3 --out results/baseline
python tools/strata_bench.py --url http://127.0.0.1:8080 --runs 3 --long --out results/candidate
python tools/strata_bench.py --compare BASELINE_RUN_FOLDER --compare-only CANDIDATE_RUN_FOLDER
python tools/ab_engine.py strata-iq2_xs.json "A:exe=/path/to/baseline" "B:exe=/path/to/candidate" --rounds 4 --max-new 256 --long-words 6000 --log results/ab.jsonl
```

`--out` selects a parent directory: the tool creates a dated machine/model subfolder beneath it. Replace `BASELINE_RUN_FOLDER` and `CANDIDATE_RUN_FOLDER` with the actual printed subfolders containing `results.json`, not the parent paths. The first command may start a server, or reuse one on the configured port; establish which engine is actually running. The URL form explicitly uses the running server. `--long` is a boolean flag for approximately 32K prompt tokens, **not** `--long 32K`. `--clients 4` adds four simultaneous requests; actual simultaneous engine execution requires `--batch` in the engine config. Do not pass `--batch` to `serve.server`, whose CLI has no such argument.

Built-in metrics: prompt/decode tok/s from engine timings, client TTFT and wall latency, actual prompt/generated/reused/read tokens, draft offered/accepted counts, errors, medians and ranges; client mode adds aggregate tok/s and p50/p95 latency. The digest can fall back to client-derived decode speed and even streaming-piece count when completion tokens are absent: preserve `decode_tps_source` and raw usage (`tools/strata_bench.py:178-201`). Do not compare stream chunks with model tokens as if equivalent.

The speed suite discards a warm-up, tags fresh prompts uniquely, disables thinking unless `--think` is selected, and measures cache reuse in a separate agent session. It is not an answer-quality benchmark (`tools/strata_bench.py:1-26`, `docs/COMMUNITY_BENCHMARKS.md:70-113`). Three repeated runs are a smoke-level comparison; do not present a p95 from a handful of burst samples as a stable tail-SLO estimate. Record CPU/GPU clocks, power/thermal limits, background load, storage, peak RAM/VRAM, swap/page faults and cold-load time separately.

Long-context recall:

```text
python tools/needle_bench.py --url http://127.0.0.1:8080 --lengths 32k,128k --depths 10,50,90 --out results/needles.json
```

The script estimates text length by characters and reports actual server token counts; oversized cases are skipped (`tools/needle_bench.py:1-12`). Count attempted/passed/skipped cases. A recall pass does not establish reasoning, coding, language, vision or broad quality parity. For quantization/RoPE/pruning changes, add representative held-out tasks and, when available, teacher-forced loss/logit divergence against a reference. Define tolerances before experiments rather than selecting them after seeing a favorable result.

## 7. Twelve experiment and recovery actions

| Trigger or experiment | Evidence to gather | Recovery or decision |
| --- | --- | --- |
| CPU setup/harness change | Named stdlib tests and exit codes | Fix the failing decision/harness first; do not load a model to debug it. |
| CMake unexpectedly accesses network | `STRATA_NATIVE_EXPERTS`, `STRATA_GGML_DIR`, pinned llama.cpp commit | Use native-experts OFF for the CPU lane or prepare the exact source dependency. |
| Quantized kernel changes | Synthetic dequant/GEMV/MoE reference errors per dtype and real-model results | Restore the baseline kernel for failing formats; narrow dispatch to proven shapes/devices. |
| KV precision or streaming changes | KV parity plus long-context recall and memory peak | Revert the KV format/streaming setting when tolerance or memory constraints fail. |
| Prefill chunk changes | Fresh prompt 4K/16K/32K TTFT, actual tokens, CPU/GPU memory | Reduce chunk size on pressure or paging; distinguish prompt and decode regressions. |
| Expert placement/PCIe overlap changes | Decode, cache hit/reuse, bytes transferred, memory and PCIe conditions | Restore one placement/overlap setting; compare with the same adaptive/cache state. |
| MTP/speculation changes | Offered/accepted drafts, verified output contract, accepted tokens per wall second | Reduce/disable the candidate speculation setting when verify overhead dominates. |
| Multi-GPU split changes | Device order, per-device VRAM, deterministic response, traffic, latency | Return to the known single-card/split baseline; validate ordering and allocation first. |
| Concurrency change | Batch versus solo tokens under controlled settings, then production throughput/tails | Reproduce with stable rounding before blaming scheduling; shrink slots on pressure. |
| Cancellation or restore change | Early-close next-request response, reuse/pressure/exchange checks | Quarantine the candidate if stale tokens or cross-session state appears. |
| Apparent speedup within run-to-run spread | Alternating same-day A/B, enough generated tokens, full per-request data | Increase paired repeats or workload length; label inconclusive if noise persists. |
| Long-context or approximate algorithm change | Multiple lengths/depths plus held-out task score/loss divergence | Reject accuracy regressions beyond the declared tolerance even if speed improves. |

Archive the baseline, config and logs; roll back only the candidate settings or executable under test. Do not overwrite model artifacts or destroy the previous working environment as a recovery step.
