# Model-specific audio duration contract

This version preserves the original failed coverage observation. The 15s baseline has 362 video frames at24FPS and a15.075s audio stream. The earlier validator assumed audio must reach362/24seconds and rejected it.

At engine source `ce216014adb4c037dc15b3d49623e493ca3d3ac3`, `pipeline_minimax_h3.py` derives `expected_audio_t` from the aligned video duration using `MiniMaxH3ShapePlanner.audio_latent_t`; `time_request.py` implements `round(duration_seconds *40)`. Thus the expected audio duration is603/40=15.075seconds. This contract correction applies equally to baseline and candidates; it does not increase an arbitrary error tolerance. Timestamp continuity, full decoded sample coverage, finite output and bounded codec padding remain required.

The implementation is adapted from InferRSI PR318 validator at `e59b39a3ced3a18585576bcea8bda325699dde5b`. `upstream_metrics.py` and scorer weight hashes are unchanged. Supply explicit AlexNet and LPIPS weight paths to `compare.py`; it authenticates their bytes and never downloads fallback weights. Model outputs and weights are external artifacts.

The baseline pair passes coverage and perceptual gates but differs in decoded video and audio. Its verdict remains INCONCLUSIVE. A perceptual threshold pass does not alone establish losslessness. This is not independent review or candidate acceptance.
