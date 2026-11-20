---
name: vllm-musa
description: "Investigate text-LLM and Omni serving performance on Moore Threads MUSA through the vllm-musa plugin: device identity, torchada dispatch boundaries, the pinned Omni image, and measurement rules that keep a CUDA-derived result from being reported as a MUSA result."
license: Apache-2.0
disable-model-invocation: true
metadata:
  disco-role: operating
---

# vLLM-MUSA serving investigation

Use this **source-derived candidate** for the Moore Threads plugin at
`MooreThreads/vllm-musa`, not for upstream vLLM or for vLLM-Omni on CUDA,
ROCm or Ascend. Every procedure here is pinned to a revision in
[references/sources.md](references/sources.md); nothing in it was measured on
MUSA hardware by this skill's author.

Two model lanes share one plugin:

| Lane | What runs | Where the risk is |
| --- | --- | --- |
| Text LLM | vLLM + `vllm_musa` platform plugin on MUSA | device identity, dispatch of CUDA-shaped fast paths |
| Omni (image/video/audio) | vLLM-Omni built into the MUSA image | CUDA-only kernels excluded by constraint; model-specific numerics |

## Route by the question that can be answered

| Question | Read | First discriminator |
| --- | --- | --- |
| Is the campaign even on the card it claims? | [device identity](references/device-identity.md) | pymtml physical id/UUID versus `MUSA_VISIBLE_DEVICES` |
| Did the CUDA optimization actually run here? | [dispatch boundary](references/dispatch.md) | kernel names in a steady-state profile |
| Can this Omni change apply in the MUSA image? | [Omni lane](references/omni.md) | the image's constraint list and the resident kernels |
| Is the measured delta real? | [measurement](references/measurement.md) | AB/BA on identical physical devices, identical pins |

## Hard rules

1. **A CUDA result is a hypothesis here, not an effect size.** The plugin runs
   CUDA-oriented source through `torchada`, so presence of a fast path in the
   source says nothing about which implementation executed.
2. **Pin five things together:** plugin revision, upstream vLLM version, MUSA
   toolkit/driver, `torchada`/`torch_musa` revisions, and the model checkpoint.
   Any one of them changing makes the comparison a different experiment.
3. **Report the physical device set.** `pymtml` (MTML) answers with physical ids
   and is documented as unaffected by `MUSA_VISIBLE_DEVICES`, while `torch.musa`
   applies the logical remapping. Two arms that share an env string can still
   sit on different cards.
4. **Keep the Omni and LLM lanes apart.** An Omni image result does not describe
   `vllm serve` throughput, and a text-LLM decode number does not describe
   denoise or codec time.
5. **Missing evidence stays INCONCLUSIVE.** No profile, no physical-device
   record, or no quality gate means the run is not a result.

## What this skill does not give you

- No MUSA kernel implementation, no MATE tuning recipe, no expected speedup.
- No claim that any CUDA or Ascend optimization in the wider knowledge base
  transfers to MUSA; those records remain scoped to their own hardware.
- No authorization to execute a benchmark, restart a service or reserve devices.
  Bring your own frozen commands and gates.
