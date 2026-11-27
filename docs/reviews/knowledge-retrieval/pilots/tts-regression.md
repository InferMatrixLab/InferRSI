# TTS streaming regression

Can the two releases be compared before changing a codec setting?

Both selected records declare locally_verified=false. Their measurement procedure can transfer. The timing boundary, cause of degradation and relationship between the two symptoms remain unknown on this target.

## Reviewed source passages

### Are both first-audio measurements comparable?

- `package:vllm_omni.common.audio.streaming_serving_measurement` at `sha256:d88cae264916abce761108bed26ab471fe5cd4ed8ff964fe0ad17058dd3abd8a`, resource `record.json`. Collect the complete stream and output alongside first-packet measurements. (analogue, method).
  > first media packet and chunk continuity alongside complete output and quality

- `package:vllm_omni.common.audio.streaming_serving_measurement` at `sha256:d88cae264916abce761108bed26ab471fe5cd4ed8ff964fe0ad17058dd3abd8a`, resource `data/skill_library/systems/engines/vllm-omni/sub-skills/omni-serving/references/serving.md`. Timestamp each of the three events per request. (analogue, method).
  > first received delta, first decoded packet or first audible speech

### What should the audio quality control include?

- `package:sglang_omni.common.audio.serving_and_streaming_quality` at `sha256:8b256066de12d761cf6944b449a6234f1857c8fce6e5a94b6813b236d81371f9`, resource `record.json`. Compare decoded audio, rate, termination and completeness. (analogue, method).
  > sample rate, SSE errors, EOS and complete content

## Missing observations and next experiment

- Effective versions, paired event timestamps, codec tokens and complete audio.

Fix text, reference audio, checkpoint and concurrency. Record all three events on both releases and compare full waveforms.

Replay the [pinned request](tts-regression.json) with `inferrsi knowledge round docs/reviews/knowledge-retrieval/pilots/tts-regression.json`. The returned body, digest and quotation are independently checkable.
