# FP8 text correctness preparation

[Acceptance #57](https://github.com/InferMatrixLab/InferRSI/issues/57) owns this
separate FP8 campaign under [parent #53](https://github.com/InferMatrixLab/InferRSI/issues/53).
The historical BF16 preparation and evidence remain in their existing tree.

Status: preparation only; INCONCLUSIVE. The workload is proposed, not frozen.
Authenticate the official Qwen/Qwen3.8-27B-FP8 checkpoint at `<model_revision>`.
Freeze its byte manifest, this workload, control/baseline/candidate revisions,
registered environment lock, exact GPU, validator sources, gates and budget in
the acceptance issue before any candidate experiment. No pins or numerical
gates are supplied by this template.

The checkpoint uses dynamic e4m3 FP8 linear weights with 128 by 128 blocks and
BF16 activations; unquantized layers remain BF16. Reference and candidate must
retain and execute FP8 weights. Whole-checkpoint BF16 dequantization is excluded.
The reference additionally requires an immutable kernel-registry revision and
trusted source fingerprint for the prepared torch-cuda build of
kernels-community/finegrained-fp8, with offline caches and DeepGEMM disabled.

The bounded native_text_smoke compares full-prefix Transformers teacher forcing
with the native hybrid-state engine through the common correctness loop. It is
not broad quality, complete engine acceptance or a performance claim.
