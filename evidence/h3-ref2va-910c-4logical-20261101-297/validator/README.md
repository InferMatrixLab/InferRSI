# Validator status

The requester selected **strict bit-exact** for the lossless tracks. The
[lossless contract](../plan/frozen-lossless-contract-v1.json) was frozen before
search. It fixes video/audio FP32 checkpoints, schedule and all decoded RGB24/PCM
bytes. Original B0 repeatability passed separately at both durations. Equal MP4
hashes alone do not establish this contract.

The [lossy contract](../plan/frozen-lossy-contract-v1.json) was frozen before real
lossy outputs. It specifies ten prompts, pinned scorers/weights, reduced official
VBench dimensions and paired video/audio/reference/temporal guards. The source
requirement's human inspection is excluded from this RSI loop and is not claimed
as completed. These proxies do not certify absolute quality or semantic AV synchrony.

The [snapshot manifest](frozen-snapshots.json) identifies exact original bytes.
Archived scorer paths assume the original execution-tree layout and pinned
dependencies; this evidence folder alone is not a self-contained runtime. No
weights or raw media are bundled. Keep numerical qualification, automatic model
quality and clean timing separate. Missing samples remain INCONCLUSIVE; an observed
gate violation remains FAIL even when other samples are missing.
