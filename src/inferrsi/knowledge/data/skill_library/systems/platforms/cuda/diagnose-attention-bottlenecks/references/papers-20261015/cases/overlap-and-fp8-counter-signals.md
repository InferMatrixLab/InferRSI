# Case D-C3: More overlap and lower precision need separate acceptance tests

Status: candidate; empirical_validation: not_run. All measurements below are author-reported.

## F: matched overlap ablations

[D3 §4.2/Table 2, pp. 9/11](https://arxiv.org/pdf/2407.08608v2#page=11): non-causal FP16 forward, {batch, sequence, heads, head dimension}={4,8448,16,128}:

| Configuration | Time | Throughput |
|---|---:|---:|
| Full FA3 | 3.538 ms | 661 TFLOP/s |
| No GEMM-softmax pipeline; warp specialization retained | 4.021 ms | 582 TFLOP/s |
| GEMM-softmax pipeline retained; no warp specialization | 4.105 ms | 570 TFLOP/s |

Appendix C.1 specifies H100 80GB SXM5 (700W), fixed 1830MHz, CUDA 12.3, cuDNN 9.1.1.17, CUTLASS 3.5, FlashAttention 2.5.8, Triton nightly 3.0.0.post20240424212437 and PyTorch 2.3.0; benchmark times are the mean of 100 repetitions. These are the paper's historical benchmark dependencies, not a recommended current install set. No neither-feature baseline is shown, so the two ablations do not establish additive independent improvements.

Appendix B.3 supplies a negative result: the three-stage pipeline is worse than the two-stage design. The hoped-for second-GEMM/softmax overlap is not realized by the compiler and extra registers force smaller tiles. It gives no numerical three-stage timing. Appendix B.2's simplified SASS analysis is the authors' inspected machine-code evidence; no local compilation was performed.

## F: FP8 performance is not a universal win

[D3 Figure 7, p. 11 / Figure 9, p. 22](https://arxiv.org/pdf/2407.08608v2#page=22) includes causal d=256 FP8 forward: at the largest displayed length, FA3 is 1024 TFLOP/s and cuDNN is 1099 TFLOP/s. Appendix C.2 defines that axis label “16k” as actual N=16896; its larger lengths 4224, 8448 and 16896 are divisible by 132 to avoid wave quantization. The main text's 16k-total-token batch rule and the adjusted FP8 length family should not be used to invent an exact batch or latency not restated for this point.

Footnote 10, p. 12: FP16 FA3 uses persistent-kernel/load-balancing strategies while FP8 FA3 does not. This partly explains small-sequence and causal behavior against cuDNN. A precision comparison can therefore include a scheduling-design confound as well as arithmetic/layout costs.

## F: the accuracy ablation answers a different question

[D3 §4.3/Table 3, pp. 11–12](https://arxiv.org/pdf/2407.08608v2#page=12) uses an FP64 reference and a synthetic outlier distribution, not a training-quality benchmark. FP8 e4m3 RMSE is 2.4e-2 for the per-tensor-scaled baseline, 9.1e-3 for full FA3, 9.3e-3 without block quantization and 2.4e-2 without incoherent processing. FP16 FA2 and FA3 each have RMSE 1.9e-4; standard FP16 is 3.2e-4.

The reported 2.6× error reduction is against **that FP8 baseline**. It is neither better than FP16 nor evidence of unchanged model quality. In this synthetic setting the gain is primarily associated with incoherent processing; block quantization's independent effect is small. The source does not establish that this allocation of benefit generalizes to all models or outlier distributions.

## P: proposed decision

Use two gates: (1) verify that dependencies, compiler scheduling and extra buffer/register costs actually permit more overlap; (2) verify FP8 layout/preprocessing overhead and numerical/task-quality acceptance. Reject deeper pipelines that add live state without added overlap, and reject FP8 proposals whose speedup excludes required preprocessing or whose numerical evidence has the wrong baseline. No fixed precision, pipeline depth or hardware port is recommended from this paper alone. See [F6–F9](../../mechanisms.md).
