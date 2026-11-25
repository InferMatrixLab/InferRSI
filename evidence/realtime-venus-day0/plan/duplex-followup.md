# Full-duplex functional follow-up

This follow-up extends downstream PR #10976 with an explicit duplex deployment,
speech-tail flushing and intentionally silent text delivery. It is functional
validation of the implementation, not a new frozen performance campaign or a
repeat of the HTTP eager/compiled comparison. No full-duplex speedup is claimed.

The downstream tests cover configuration resolution, aligned delegation
filtering, cross-unit masking, flush-once behavior, speech restart, masked EOS,
request replacement, codec drain/cache epochs, silent text delivery and replay
fencing. The vocoder's isolated import test guards the producer/consumer import
boundary. Existing shared MiniCPM duplex tests remain in the regression run.

Real-weight checks use the same pinned Omni checkpoint, one NVIDIA L20X,
three stages, and the ten-step FP32 Flow recipe. A short greeting-only stream
is recorded as input acceptance when the model only listens. A seeded greeting
checks synthesis separately. A paced 30-second synthetic Mandarin audio/video
fixture exercises multiple questions and changing scenes; a separate lifecycle
probe reconnects a resumable session, cancels a spoken response, sends a fresh
audio/video question, and requires a new completed audio response without
stale audio from the cancelled response.

The lifecycle probe is provided in `validator/duplex_lifecycle.py`. To create
its seven-second question WAV, with `espeak-ng` and `ffmpeg` installed:

```bash
espeak-ng -v cmn -s 195 -w question-raw.wav '请说出现在画面中图形的颜色和形状。'
ffmpeg -v error -y -i question-raw.wav -ar 16000 -ac 1 -af apad -t 7 question.wav
python validator/duplex_lifecycle.py \
  --url ws://127.0.0.1:8091/v1/realtime \
  --model /path/to/Realtime-Venus/Realtime-Venus-Omni \
  --input-wav question.wav --output lifecycle.json
```

The server must use `realtime_venus_omni_duplex.yaml`. The probe requires
`websockets`, `pybase64` and Pillow. It generates red and blue circle camera images,
does not play audio or falsely acknowledge playback, and strips resume tokens
from its retained events. Synthetic speech can vary with tool versions; this
is a functional probe, not an exact-output or perceptual-quality benchmark.

The external delegation executor, long-video memory runtime, Audio-only
checkpoint, distributed/non-CUDA deployments and sustained-service quality
remain outside this follow-up's acceptance evidence. CPU delegation regressions
are not a claim that a real model was forced to produce every delegation path.
