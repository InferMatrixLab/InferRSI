# Ascend A2 AR campaign trajectory

Tracking [issue #775](https://github.com/InferMatrixLab/InferRSI/issues/775). Target metric is batched AR output tokens per second.

1. The first four-device full-stage attempt used HunyuanImage-3.0-Instruct, TP4, stage 0 only. The host worker environment failed during platform import because the vLLM Ascend plugin was missing. No generated-token timing was produced.
2. Source inspection identified a per-decode-step gather, conditional selection and indexed assignment for every row of comprehension-only batches, even though the blocklist is shared. A one-device calibration measured 43,838 transformed rows/s. This isolated the operation without timing the base sampler.
3. The candidate applies the constant blocklist in-place by column and retains conditional masking for mixed-mode engines. Three alternating InferRSI pairs gave median 44,290 to 396,763 transformed rows/s on one Ascend 910B1. The attached evaluator, six raw trial records and independent reference comparison cover this operation. Every fp32 logit and greedy token matched on all five batch sizes. This check exercises checkpoint vocabulary, not a transformer forward or model-generated text.
4. The full-stage results and acceptance decision follow below.

Runtime for the isolated trial: vLLM 0.34.0, PyTorch 2.10.0, torch-npu 2.10.0.post7, CANN 9.2.1; checkpoint revision `2ec2c78bee7d4b94157341fba86c4c2c7b1858b2`. The frozen validator resolves the tested method directly from each pinned source. Each timed trial uses the same instrumented method with an identity base sampler.

## TP4 bring-up

All four ranks loaded the 32 checkpoint shards and initialized HCCL with the official Ascend plugin on the host. On this installation the container device probe failed at `aclInit`; a tensor operation succeeded on the reserved device on the host. A full-engine attempt using 75% device memory timed out during initialization and reported insufficient KV cache headroom. The pure-text retry at 90% reported 13.53 GiB available for KV cache. Its first request contained 1,243 prompt tokens after the checkpoint's official template, exceeding the initial 1,024-token context limit. Both arms use a corrected 4,096-token limit and a 2,048-token scheduler budget. These failed attempts produced no timed batches.

After correcting the context budget, the stock engine generated the first 8 × 32-token batch. Its second greedy batch differed from the first at the token-ID level. The original inline equality assertion stopped the run during warmup. The final collector retains all five batches per trial and runs the same strict, full-sequence equality check after all six timing trials. Neither the prompts nor the acceptance condition changed. The eight timed prompts are 1,238–1,243 tokens after checkpoint formatting; the held-out prompt is 1,243 tokens.

## Completed TP4 stage comparison

Text-only HunyuanImage-3.0-Instruct AR, four Ascend 910B1 devices in TP4, bf16/eager, batch eight, 1,238–1,243 input tokens and 32 greedy output tokens per request. Each of six trial processes loaded its own engine. Two warmup batches preceded three timed batches. A ninth prompt was generated separately after timing.

Median warm offline throughput was **43.55 → 44.11 generated tokens/s (+1.29%)**. Paired changes were +1.01%, -9.54%, +2.91%.

| Pair | Order | Baseline tokens/s | Candidate tokens/s | Paired change |
|---|---|---:|---:|---:|
| 1 | A/B | 43.89 | 44.33 | +1.01% |
| 2 | B/A | 43.55 | 39.39 | -9.54% |
| 3 | A/B | 42.86 | 44.11 | +2.91% |

The baseline peak-to-peak spread was 2.36% and the preregistered minimum median gain was 2.36%. InferRSI returned **INCONCLUSIVE**. The measurements do not establish a full-stage speedup under the preregistered gates.

Across the nine timed batches per arm, 7/8 baseline prompts and 8/8 candidate prompts produced multiple 32-token sequences. Across all runs the held-out result matched the baseline trial-1 held-out sequence in 1/3 baseline trials and 0/3 candidate trials. The exact-token gate failed. Baseline variability limits attribution of output differences to the patch.

InferRSI also flagged a source-snapshot change. Its seven before/after snapshots preserve both commit IDs. The first candidate startup created an empty untracked runtime/config/runtime_config.json.lock file, the only observed delta. A post-run Git comparison found zero tracked-file changes in either checkout. The original INCONCLUSIVE evaluator verdict is retained.

The results directory includes the six trial records, 18 individual timed batch rates, retained warmup/timed output IDs, the held-out outputs and the InferRSI evaluation receipt.

The [subsequent lossless rounds](../lossless/README.md) include the deterministic A/A calibration, paired complete-stage measurements and the per-round throughput curve.
