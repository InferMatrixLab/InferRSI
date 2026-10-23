# Optimization and instrumentation provenance

Existing mechanisms remain credited to their upstream implementation. This campaign evaluates deployment adaptations; source availability alone does not establish measured gain.

| Mechanism | Source | Campaign contribution |
| --- | --- | --- |
| MRv2 sampled-token embedding handoff, first-frame delivery, codec chunk ramp, grouped codec graphs, fused Snake | [upstream d93e1a8 / PR #8223](https://github.com/vllm-project/vllm-omni/commit/d93e1a8e09d2a0d386c4a58424470d685ee7743c) | Evaluate unchanged bundled profile on two L20X GPUs |
| Incremental code-predictor KV and optional short-KV attention | [upstream d93e1a8 / PR #8223](https://github.com/vllm-project/vllm-omni/commit/d93e1a8e09d2a0d386c4a58424470d685ee7743c) | Separate two-GPU deployment overlays and retained screening evidence |
| Conservative sampling fusion and bounded cuDNN algorithm search | [upstream d93e1a8 / PR #8223](https://github.com/vllm-project/vllm-omni/commit/d93e1a8e09d2a0d386c4a58424470d685ee7743c) | Adapt the existing H200 bundle to two-GPU placement for screening; combined results do not isolate either mechanism |
| Private MPS lifecycle and stage placement integration | [initial e1303e5 / PR #8163](https://github.com/vllm-project/vllm-omni/commit/e1303e5067bb5617eb12d4cb291aef6eb8b42634), [later compatibility changes 717f8a3 / PR #9188](https://github.com/vllm-project/vllm-omni/commit/717f8a3499fb7dc6b3128b58a8baeacded1a7bbb) | Evaluate MPS with full Omni stages on exactly two GPUs; no new MPS algorithm |
| Valid-audio TTFA and per-request audio evidence | [campaign PR #9278](https://github.com/vllm-project/vllm-omni/pull/9278) | New benchmark correctness and evidence retention fixes, backed by deterministic regressions; no inference speedup |
| Exact overlapping-request peak concurrency | [campaign PR #9279](https://github.com/vllm-project/vllm-omni/pull/9279) | New correction for one-second bucket overcount observed in this campaign; no inference speedup |
| Text readback workload and paired quality gates | Native Seed-TTS benchmark at the frozen source revision; campaign `benchmark_readback.py` and `check_results_v3.py` | Explicit user-side readback while preserving original WER references; complete raw coverage and paired scorer/utterance identity |
| Conditioning and warmup rules | Retained MRv2/KV screening JIT evidence and independent protocol review | Equal baseline/candidate conditioning, explicit retry limits and retained invalid attempts; no post-hoc removal of slow requests |
| Verbose JIT monitor configuration forwarding | [campaign PR #9281](https://github.com/vllm-project/vllm-omni/pull/9281) | New configuration-owner forwarding fix, discovered when enabling identical compilation observation for both arms; no inference speedup |
| Code2Wav placement beside Thinker on two GPUs | Campaign baseline trace interval analysis; upstream stage placement mechanism | New deployment hypothesis to redistribute measured work; no algorithm change or verified gain yet |
