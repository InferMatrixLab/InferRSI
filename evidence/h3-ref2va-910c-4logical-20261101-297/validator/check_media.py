"""Decode every frame/sample and hash canonical RGB24 and interleaved PCM."""

import argparse
import hashlib
import json
from pathlib import Path

import av
import numpy as np


def inspect(path, frames):
    video_hash, audio_hash = hashlib.sha256(), hashlib.sha256()
    frame_hashes = []
    with av.open(str(path)) as media:
        assert len(media.streams.video) == 1 and len(media.streams.audio) == 1
        stream = media.streams.video[0]
        assert (stream.width, stream.height, float(stream.average_rate)) == (1344, 768, 24.)
        for frame in media.decode(video=0):
            value = frame.to_ndarray(format='rgb24')
            payload = value.tobytes(order='C')
            video_hash.update(payload)
            frame_hashes.append(hashlib.sha256(payload).hexdigest())
    assert len(frame_hashes) == frames, len(frame_hashes)
    samples, sum_squares, peak = 0, 0., 0.
    with av.open(str(path)) as media:
        stream = media.streams.audio[0]
        assert stream.rate == 32000 and stream.codec_context.channels == 2
        for frame in media.decode(audio=0):
            assert frame.format.name == 'fltp' and frame.layout.nb_channels == 2
            value = frame.to_ndarray()
            assert value.dtype == np.float32 and np.isfinite(value).all()
            samples += value.shape[1]
            sum_squares += np.square(value.astype(np.float64)).sum().item()
            peak = max(peak, float(np.abs(value).max()))
            audio_hash.update(value.T.copy(order='C').tobytes())
    assert samples > 0 and sum_squares > 0
    assert abs(samples / 32000 - frames / 24) <= 1 / 24
    return {'video_frames': frames, 'width': 1344, 'height': 768, 'fps': 24,
            'rgb24_sha256': video_hash.hexdigest(), 'frame_rgb24_sha256': frame_hashes,
            'audio_sample_rate': 32000, 'audio_channels': 2, 'audio_samples': samples,
            'pcm_f32_interleaved_sha256': audio_hash.hexdigest(),
            'finite_audio': True, 'audio_rms': (sum_squares / (samples * 2)) ** .5,
            'audio_peak': peak, 'media_integrity': 'PASS',
            'model_quality': 'not_evaluated'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--media', required=True)
    parser.add_argument('--frames', type=int, required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = inspect(Path(args.media), args.frames)
    Path(args.output).write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != 'frame_rgb24_sha256'}))


if __name__ == '__main__':
    main()
