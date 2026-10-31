# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM-Omni project

# Frozen metric functions from vLLM-Omni c7f56f0155953c7d4a77276a2f4fcbd844ab0da2.
# Retained verbatim; campaign runner must enforce equal stream lengths first.
import numpy as np
import torch


def _canonical_audio(audio: object) -> np.ndarray:
    """Return H3 audio as float32 [channels, samples]."""
    array = np.asarray(audio, dtype=np.float32)
    while array.ndim > 2 and array.shape[0] == 1:
        array = array[0]
    if array.ndim == 1:
        array = array[None, :]
    if array.ndim != 2:
        raise ValueError(f"Expected mono/stereo audio, got shape {array.shape}")
    if array.shape[0] > array.shape[1] and array.shape[1] <= 8:
        array = array.T
    if not 1 <= array.shape[0] <= 8:
        raise ValueError(f"Expected channel-first audio, got shape {array.shape}")
    if not np.isfinite(array).all():
        raise ValueError("Audio contains non-finite samples")
    return np.ascontiguousarray(array)

def _audio_quality_metrics(baseline: object, quantized: object) -> tuple[float, float]:
    """Compare phase-tolerant spectral structure and overall signal energy."""
    baseline_array = _canonical_audio(baseline)
    quantized_array = _canonical_audio(quantized)
    if baseline_array.shape != quantized_array.shape:
        raise ValueError(
            "Audio shapes do not match for metric computation: "
            f"baseline={baseline_array.shape}, quantized={quantized_array.shape}"
        )

    baseline_tensor = torch.from_numpy(baseline_array)
    quantized_tensor = torch.from_numpy(quantized_array)
    similarities: list[float] = []
    for n_fft in (512, 1024, 2048):
        window = torch.hann_window(n_fft)
        baseline_magnitude = torch.stft(
            baseline_tensor,
            n_fft=n_fft,
            hop_length=n_fft // 4,
            window=window,
            return_complex=True,
        ).abs()
        quantized_magnitude = torch.stft(
            quantized_tensor,
            n_fft=n_fft,
            hop_length=n_fft // 4,
            window=window,
            return_complex=True,
        ).abs()
        cosine = torch.nn.functional.cosine_similarity(
            baseline_magnitude.flatten(1),
            quantized_magnitude.flatten(1),
            dim=1,
            eps=1e-12,
        )
        similarities.extend(float(value) for value in cosine)

    baseline_rms = float(torch.sqrt(torch.mean(baseline_tensor.square())))
    quantized_rms = float(torch.sqrt(torch.mean(quantized_tensor.square())))
    rms_ratio = quantized_rms / max(baseline_rms, 1e-12)
    return float(np.mean(similarities)), rms_ratio

def compute_lpips_video(
    baseline_frames: np.ndarray,
    quantized_frames: np.ndarray,
    net: str = "alex",
) -> float:
    """Compute mean per-frame LPIPS for a video pair.

    Args:
        baseline_frames: (F, H, W, C) float array in [0, 1].
        quantized_frames: same shape.

    Returns:
        Mean LPIPS across all frames.
    """
    import lpips

    loss_fn = lpips.LPIPS(net=net).eval()
    if torch.cuda.is_available():
        loss_fn = loss_fn.cuda()

    num_frames = min(len(baseline_frames), len(quantized_frames))
    scores = []
    for i in range(num_frames):
        # Convert (H, W, C) float [0,1] -> (1, C, H, W) float [-1, 1]
        f_bl = torch.from_numpy(baseline_frames[i]).permute(2, 0, 1).unsqueeze(0).float() * 2 - 1
        f_qt = torch.from_numpy(quantized_frames[i]).permute(2, 0, 1).unsqueeze(0).float() * 2 - 1
        if torch.cuda.is_available():
            f_bl, f_qt = f_bl.cuda(), f_qt.cuda()
        with torch.no_grad():
            score = loss_fn(f_bl, f_qt).item()
        scores.append(score)
    return float(np.mean(scores))
