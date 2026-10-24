# Drama-3 (fish_omni) on two Ascend 910B1

Status: **INCONCLUSIVE** for the requested RTF targets. The decode FULL-graph
change is measured and repeatable; the RTF < 0.1 (C1) and RTF < 1 (C64) bars
are not met on this hardware.

## Provenance

Measurements by amy-why-3459 on a shared 8x910B1 host (cards 3/4), 2026-10-23/24.
Upstream change: vLLM-Omni PR "Replay Drama 3 decode steps as FULL graphs"
(branch `perf/ascend-drama3-full-decode-graphs`, based on `c829af4`). The
Drama-3 NPU runner path it builds on is
[vllm-omni#9106](https://github.com/vllm-project/vllm-omni/pull/9106) (merged).
Raw logs and the sweep JSON live in `/dataset/home/why/drama3-opt/evidence/`
and `runs/`; this document stores the summary, not the logs.

## RunSpec

| Field | Value |
| --- | --- |
| repo | vllm-project/vllm-omni @ `c829af4` + the FULL-graph commit |
| backend | vLLM-Omni 0.32.0 nightly image `quay.io/ascend/vllm-omni:nightly-20261022-6b35bca`, vLLM-Ascend 0.19.1rc2, CANN 9.1.0, torch_npu 2.10.0.post4 |
| device | 2 x Ascend 910B1 (A2), stage 0 TP2 + expert parallel (devices 0,1), stage 1 DAC on device 1 |
| model | `fishaudio/drama-3` (Qwen3.5 MoE 40 layers, 256 experts / 8 active, block-FP8; 13-layer codebook tower; 44.1 kHz DAC) |
| scenario | streaming `/v1/audio/speech`, Seed-TTS-Eval `en`, one fixed pre-encoded reference (85 frames x 10 codebooks), `max_tokens=500`, 64 prompts, 1 warmup |

Metrics: audio seconds counted from SSE PCM14 payloads at 44.1 kHz mono;
`frames/s = audio_s x 21.5 / wall`; per-request `RTF = (end - start) / audio_s`
so queueing and prefill are inside the number, as the target definition asks.

## Kept

| Change | C1 frames/s | C1 RTF mean | C1 RTF p95 | C1 TTFA p50 | Source |
| --- | ---: | ---: | ---: | ---: | --- |
| baseline: stage-0 PIECEWISE capture | 17.31 | 1.237 | 1.301 | 0.91 s | upstream `fish_omni.yaml` |
| decode `FULL_AND_PIECEWISE`, sizes to `max_num_seqs` | 22.4 | 0.962 | 1.141 | 0.80 s | this work, run 1 |
| same, repeat | 22.91 | 0.947 | 1.036 | 0.78 s | this work, run 2 |
| same, final sweep (host loaded) | 18.77 | 1.147 | 1.353 | 0.89 s | `runs/final/final-v2.json` |

The host is shared (load average 15–20 during runs); the two clean repeats
are the attribution, the loaded sweep is the conservative bound. The gain is
one graph replay per decode step instead of ~53 layers of eager launches.

Batching on the same build, best of repeats:
16 streams 133 frames/s, 32 streams 137, 64 streams 305 (best of three:
137 / 197 / 188, one later run 305); final sweep under load: 65 / 137 / 269.
Spreading inside the sweep is large enough that single readings of C8–C32
should not be compared across tables.

## Rejected

| Change | Result | Why it stays out |
| --- | --- | --- |
| bind `fla_npu.ops.ascendc.causal_conv1d_update` into vLLM's GDN update | C1 22.4–22.6 frames/s, RTF 0.95 — identical to the unbound build; FULL capture succeeds with the portable `causal_conv1d_update` bound | the vLLM-Ascend warning claims the fallback stalls decode-FULL capture, but on this stack it does not; no measurable effect |
| keep the checkpoint's block-FP8 experts as FP8 | not attempted as a change: vLLM-Ascend builds `AscendW8A8MXFP8Dynamic*` only on 950 (`is_950()`), so A2 expands every expert to bf16 at load | would need a native A2 block-FP8 grouped GEMM; out of scope here |
| `mamba_ssm_cache_dtype: bfloat16` | already the default in this deploy config | not a lever |

## Where the time goes

Phase timers in `fish_omni_model.forward` (eager, one stream, one request):
backbone ~195 ms, tower + sampling ~72 ms, writeback ~0.1 ms per frame. With
FULL graphs the same step is ~44 ms, so the graph removes most of the launch
overhead, not the arithmetic.

Why C1 = 0.1 is not reachable here: one frame is 40 MoE layers plus 13 tower
layers, and 21.5 frames/s at RTF 0.1 gives 4.65 ms per frame. Both ranks
hold roughly 32 GiB of expanded bf16 expert weights, so a single frame's
expert read alone is on the order of a ten-thousandth of a second per GB at
the card's bandwidth — the budget is below the bandwidth floor before KV,
tower and sampling are added.

## Operating notes learned the hard way

- CANN 9.1.0 does not ship `aclnnAddRmsNormBias`; vLLM-Ascend's custom-op
  vendor package must be registered (`${ASCEND_OPP_PATH}/vendors/config.ini`
  `load_priority`, plus readable directory modes). A `750 root:root` vendor
  directory makes `dlopen` fail with "Permission denied" and surfaces as a
  missing-operator error.
- `fla_npu`'s `.pth` rewrites `ASCEND_CUSTOM_OPP_PATH` at interpreter start;
  set `FLA_NPU_DISABLE_PTH=1` when a specific vendor list is required.
- `/health` answers before stage 0 finishes warming. A readiness probe must
  issue one real synthesis request, or a sweep starts against a dead port.
- Stage 1 (DAC) initialises after stage 0; the first request pays its engine
  startup unless the probe absorbs it.
