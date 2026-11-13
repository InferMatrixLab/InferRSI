# MiniCPM-o 4.5: vLLM-Omni Seed-TTS investigation

Acceptance: [issue #431](https://github.com/InferMatrixLab/InferRSI/issues/431).
Implementation draft: [vLLM-Omni #10331](https://github.com/vllm-project/vllm-omni/pull/10331).
The service goal remains **INCONCLUSIVE**. A component PASS below does not
establish lower RTF than the independent engine at all requested concurrencies.

## Verified component result

The current-Agent workflow ran `campaign start`, `knowledge`, `round` and an
independent `final`. Three alternating measurements per side measured repeated
600- and 1200-frame S3 inputs with real checkpoint weights. Each measurement
warms each shape before synchronized host timing, including replay copies.
The quality script checks exact codec tokens and lengths on synthetic inputs
and 16 distinct Seed-TTS tuning reference WAVs.

| Independent final | Eager baseline | S3 graph replay |
| --- | ---: | ---: |
| Median call latency, ms | 4.2791 | 3.7187 |
| Process sample range, ms | 4.2502–4.4535 | 3.7154–3.7329 |

The local component evaluator returned PASS (13.09% lower latency). It did not
establish statistical significance or generated-speech quality. Only two
repeated shapes are admitted: the real-reference check recorded four graph
hits and 44 misses. This is a correctness workload, not a service hit-rate
measurement, and illustrates why a repeated-shape microbenchmark is insufficient.

`results/s3-component.json` preserves the final assessment and corrects the
initial hypothesis's mistaken mention of scalar synchronization. The published
S3 0.3.0 encoder already uses static mask widths. The retained candidate wraps
the unchanged encoder and quantizer; it does not replace their arithmetic.

## Lessons supported by this investigation

- Check dependency source bytes as well as package versions. The shared local
  S3 installation reported the pinned version but changed quantization,
  LayerNorm epsilon and mask construction. Its exploratory service runs were
  excluded. Later comparisons use an isolated published wheel for both engines;
  the shared installation was left intact.
- Re-profile the current framework revision. Existing CUDA CFM, HiFT and
  encoder graph optimizations make an older framework comparison insufficient
  to identify today's bottleneck.
- Separate runner/configuration choices from new code. The existing K-step
  Talker configuration must be compared with MRv2 before attributing gains to
  a new tokenizer option.
- Validate graph output ownership and fallback behavior, not just one capture.
  Retained outputs must survive subsequent replay, shape capacity must remain
  bounded, and changed precision policies must use the original eager path.
- Preserve the user gate at service scope. A local operator improvement, a
  green test suite, or successful PR submission cannot substitute for matched
  C1/C16/C32 service measurements and speech-quality evidence.

## Archive boundaries

`plan/` records the acceptance and component scope. `validator/` contains the
executed frozen component scripts and public-dataset input hashes. The model
and dataset paths retain the experiment's generic `/data/models` cache mount;
mount the pinned assets there when reproducing this exact validator. The
source snapshot can be reconstructed from the issue's baseline revision and
`patch/s3-component.patch`.

`results/` retains numeric measurement and quality outputs. Full local Harness
workspaces, private process paths, GPU UUIDs, service logs and generated WAVs
are not included. This selected archive does not claim to replay the full
Harness source-check chain. Service qualification and the final implementation
remain separate from this component snapshot.
