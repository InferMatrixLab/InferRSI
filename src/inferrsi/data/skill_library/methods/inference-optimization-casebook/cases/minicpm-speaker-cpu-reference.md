# MiniCPM-o speaker extraction: preserve the executed reference graph

This is a scoped diagnostic from [acceptance issue #49](https://github.com/InferMatrixLab/InferRSI/issues/49).
The isolated component gate passed; service and generated-speech qualification
remain separate. Raw measurements belong to the campaign evidence tree.

## Observation

Concurrent voice cloning repeatedly prepares distinct reference audio. A host
stack sample concentrated in CPU CAM++ extraction, but profiling perturbed the
service and cannot establish its wall-time share. An isolated synchronized
benchmark confirmed substantial CPU extraction cost. Moving the original ONNX
graph to either Torch or TensorRT changed normalized speaker embeddings, most
strongly on short inputs. Disabling TF32 did not remove that discrepancy.

## Confirmed mechanism

The reference CPU ONNX Runtime session optimizes the graph. Its BASIC PadFusion
folds zero Pad into ceil-mode AveragePool and changes `count_include_pad` for
partial windows. An unfused conversion preserves the original graph rather
than the currently executed CPU semantics. Comparing optimization-disabled and
BASIC/ALL sessions, plus a minimal all-ones pooling regression, isolated this
difference from floating-point precision.

The candidate exports the portable BASIC-optimized graph, keys it by model
content and ONNX Runtime version, and builds a separate IEEE FP32 TensorRT
engine. This met the predeclared component tolerance on the sampled normal
and short reference inputs. It is not a proof of bitwise waveform identity or
service-quality equivalence.

## Reuse procedure

1. Pin model assets, runtime optimizer version, preprocessing and reference
   lengths. Include partial pooling windows and short inputs.
2. Compare intermediate outputs with graph optimizations disabled and enabled
   before attributing differences to TF32, quantization or checkpoint drift.
3. Export only portable operators; keep derived artifacts outside model files
   and isolate caches by content, backend version and precision policy.
4. Measure the component with explicit synchronization and warmup, then run
   matched service workloads with the same concurrency and reference diversity.
5. Evaluate WER, speaker similarity and perceptual quality independently.
   Do not promote a component PASS to a service or accuracy PASS.

## Counter-signals and rejected alternatives

MPS, runtime encoder capture and a larger CFM microbatch did not improve both
high-concurrency tuning cells in the initial scan. This does not blacklist
those mechanisms: after removing a host bottleneck, accelerator contention
and batching may become relevant. MRv2 traded lower first-audio latency for
lower throughput on this workload; select against the requested objective.

The original-ONNX GPU conversions failed the numerical gate even though their
component latency was lower. The cause was graph semantics, so retrying only
with different precision would repeat the wrong experiment. Short reference
inputs were discriminating; long references alone understated the error.

## Service qualification and conditional composition

The subsequent speaker-plus-MPS control changed the ranking: MPS improved
high-concurrency throughput after speaker extraction moved off CPU, although
the initial MPS-only control did not improve both target tuning cells. Treat
this as a conditional interaction, not a universal MPS recommendation.

Both speaker variants failed the original strict generated-speech gate despite
passing the isolated embedding tolerance. Repeated low-concurrency scoring and
fresh-start controls retained the differences. Do not reinterpret numerical
closeness or a confidence interval containing zero as evidence of noninferiority.

If an authorized owner changes acceptable quality loss after exploratory
results, preserve the original verdict, freeze the new margins and statistical
rule before generating unused holdout outputs, and report the new scope
separately. Profile selection must finish before opening that holdout. The
campaign evidence owns both decisions; this case does not supply default
quality tolerances.

## Limits

Evidence covers one CUDA GPU family, one official model revision and an English
voice-cloning workload. TensorRT is optional, engine startup cost is separate,
and the optimized graph must be revalidated when ONNX Runtime changes. The
case is diagnostic guidance, not an automatic backend-selection rule.
