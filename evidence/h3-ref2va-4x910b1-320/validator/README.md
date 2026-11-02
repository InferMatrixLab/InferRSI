# Validation boundary

The preflight client uses the upstream H3 Ref2VA request and media shape contract, inherited from the #293 client. Complete decoded media checks and authenticated scorer loading will reuse [the repair in #318](https://github.com/InferMatrixLab/InferRSI/pull/318) at an explicitly frozen revision before candidate search. The old SSIM/PSNR/LPIPS and audio similarity thresholds alone do not establish losslessness.

Baseline repetition is required before judging nonidentical outputs. Exact decoded parity is sufficient for the media comparison; missing or nonidentical evidence remains INCONCLUSIVE without additional equivalence proof. Both video and audio require expected temporal coverage. No candidate validator is frozen yet and no candidate search has begun.
