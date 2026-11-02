# MiniMax-H3 Ref2VA lossless follow-up

Status: **INCONCLUSIVE**. No new lossless performance gain is qualified.

The requester requires lossless acceleration, no audio-quality degradation, and
both 5-second and 15-second outputs. The accepted scope is recorded in
[the campaign update](https://github.com/InferMatrixLab/InferRSI/issues/293#issuecomment-6573035907).
The old Cache-DiT result is lossy and cannot satisfy this request. The historical
`h3-ref2va-ascend-293` bundle is preserved byte for byte.

## Current delivery

The new validator rejects two equally truncated audio tracks, checks audio
timestamps and decoded sample coverage, and authenticates the actual bytes used
for both LPIPS networks. Weight loading is explicit and offline, with strict
parameter loading; the complete scorer state was compared against LPIPS 0.1.4's
previous loader. The synthetic regression is not model-quality evidence.

Old perceptual gates remain diagnostic. A media-threshold PASS does not become a
lossless PASS: this validator returns INCONCLUSIVE for unequal decoded outputs
that pass those thresholds. It records audio and video equality separately.
Control repetitions are themselves non-bitwise-identical; any tolerance-based
adjudication needs a separately frozen matched repeatability protocol. This
bundle does not certify subjective sound quality, meaning, or lip synchronization.

## Experiment plan

- Native BF16, dense attention, 50 denoising steps, same references/seeds and
  resolution. Disable approximate block caches, reference-KV reuse, quantization
  and sparse attention in every arm.
- First screen exact weight placement: AllGather, rank-local streaming, and a
  16-layer resident prefix. The retained [screening plan](plan/screening.json)
  fixes one source for all three arms. This is an existing-configuration search.
- Screen 5 seconds first with two warmups and one measured request per server,
  inside one eight-card reservation. A pilot is not a repeated E2E qualification.
- After a candidate passes quality, run fresh A/B/B/A servers at **both 5 and
  15 seconds**, two warmups and three measured requests per duration/server.
  Freeze the selected final source/configuration and quality protocol first.
- Report HTTP upload-to-full-MP4 E2E, independent server aggregates, completion,
  sampled HBM and actual worker exit codes. Run stage profiling separately from
  unprofiled timings. Do not estimate p95/p99 from the small sample set.
- Compare the final combination directly against the original dense baseline;
  keep the matched diagnostic baseline shutdown budget explicit. Do not add
  separate optimization percentages or claim a global optimum.

## Sources and attribution

| Item | Source | Current evidence |
| --- | --- | --- |
| Exact weight placement | [vLLM-Omni #5929](https://github.com/vllm-project/vllm-omni/pull/5929), component-selective DLO; current control source in the plan | Existing implementation; 16-layer choice is a campaign hypothesis, no gain claimed |
| HTTP workload and video/audio metrics | Prior campaign's frozen vLLM-Omni accuracy/quantization-test extracts | Metrics retained, old permissive audio gate is not a no-degradation certificate |
| Audio coverage repair | [review counterexample](https://github.com/InferMatrixLab/InferRSI/pull/294#discussion_r4432729023) | Reproduced with synthetic equal truncated tracks; new validator rejects |
| Authenticated scorer | [review finding](https://github.com/InferMatrixLab/InferRSI/pull/294#discussion_r4432729025), installed LPIPS 0.1.4 `LPIPS` and `alexnet` loaders | Explicit verified-byte loads; complete state equality checked on CPU |
| No approximation as an acceptance constraint | Requester's follow-up, linked above | Source/configuration audit plus new output validation still required for each promoted optimization |

## Reproduction and limits

The optional CPU scorer needs NumPy, PyTorch, torchvision, LPIPS 0.1.4 and FFmpeg.
Supply the two already provisioned weight files explicitly; the hashes are in
`validator/weights.json`. The validator does not download weights.

```bash
python validator/compare.py --baseline <BASELINE_MP4> --candidate <CANDIDATE_MP4> \
  --frames 124 --alexnet-weights <ALEXNET_PTH> --lpips-weights <LPIPS_PTH> \
  --output <RESULT_JSON>
```

Use 362 frames for the existing 15-second request contract. The 2048-sample upper
padding allowance is two AAC frames, not permission to truncate the expected
audio duration. The process returns 0 for exact decoded parity, 1 for a failed
media gate, and 2 for nonidentical outputs requiring further adjudication;
execution errors do not establish a campaign verdict. Model files, media and
host scripts/logs remain external. No completed 5/15-second E2E result is claimed.
