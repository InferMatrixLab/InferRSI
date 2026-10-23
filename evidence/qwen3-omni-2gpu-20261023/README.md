# Qwen3-Omni two-GPU streaming speech

Acceptance: [#112](https://github.com/InferMatrixLab/InferRSI/issues/112).

Status: **INCONCLUSIVE**. The first baseline performance matrix and separate quality run are complete. Candidate search and repeated paired validation are in progress; no comparative gain or target attainment is claimed.

The frozen protocol records the full Thinker → Talker → Code2Wav pipeline, metric definitions, source provenance and quality gates. The hardware scope is exactly two L20X GPUs. Audio-input quality needs separate qualification; text readback alone does not establish conversational quality.

See [the actual baseline run manifest](results/baseline-v3-run-manifest.json) for source revisions, deployment, runtime, workload, raw results and limitations. Each performance point contains 256 requests after five warmups. Throughput counts 24 kHz PCM sample frames, not codec tokens.

| Concurrency | Throughput (frames/s) | TTFA p50 (ms) | TTFA p95 (ms) | RTF mean |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 189,393 | 132.4 | 141.2 | 0.1309 |
| 2 | 317,327 | 164.3 | 214.3 | 0.1572 |
| 4 | 524,676 | 201.6 | 299.4 | 0.1894 |
| 8 | 876,231 | 248.5 | 383.7 | 0.2253 |
| 16 | 1,289,916 | 357.0 | 514.5 | 0.3050 |
| 32 | 1,760,062 | 525.8 | 981.3 | 0.4323 |
| 64 | 2,094,731 | 735.0 | 1,032.4 | 0.6912 |

Baseline quality: mean WER 0.0383296 over 256 items, with no failed requests, missing PCM or ASR failures. Native Seed-TTS evaluation uses the frozen Whisper scorer. UTMOS is supplementary. These baseline values do not meet the issue's RTF targets.

[Candidate hypotheses and sources](plan/candidates.json) separate configuration adaptations from upstream algorithms. [PR #9278](https://github.com/vllm-project/vllm-omni/pull/9278) corrects valid-audio timestamps and preserves per-request benchmark measurements; it is instrumentation, not an inference speedup.
