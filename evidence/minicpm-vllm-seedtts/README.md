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

## Exploratory service results

The host-driven development screens in `results/service-development.json`
retain per-request RTF, duration and completion time so their means can be
checked. They are **not** a managed Harness service campaign or final
qualification: each cell uses 64 tuning requests, two consecutive repetitions
in one server, with disjoint warmup requests. Both repetitions reuse the same
canonical seed index; fresh-process and speech-quality gates remain separate.

| Mean request RTF, two repetitions | C1 | C16 | C32 |
| --- | ---: | ---: | ---: |
| Independent engine, device A | 0.06238 | 0.20611 | 0.25723 |
| Original Omni, device A | 0.08014 | 0.33299 | 0.60703 |
| Omni + S3 replay, device A | 0.08023 | 0.33753 | 0.58381 |

All listed cells completed without request failures. The S3 component gain
has not met the service target, and C1/C16 show no persuasive improvement.
No statistical significance is claimed.

Additional screens on device B tested existing speaker CUDA replay and an
experimental opt-out from padding short references to six seconds. They have
no matched independent-engine run in this archive. Removing padding worsened
C1 to 0.14655/0.12276 and C16 to 0.98626/0.73510. During C1 screening it reached
253 CFM graph captures and seven cache flushes: reducing input length also
increased shape diversity. That prototype was rejected and its working-tree
changes reverted; widening its batch capacity was pruned before execution.
The rejected change is retained in `patch/rejected-unpadded.patch`.
Speaker replay used `token2wav_spk_cpu_reference: false` and
`token2wav_spk_cuda_graph: true`; unpadded used only
`ref_audio_pad_to_max_seconds: false`, each over the ordinary turn profile.
These diagnostic counters are reported observations; full private server logs
are outside this selected archive.

A configuration-only attempt to shorten the first packet was also ineffective:
the current MiniCPM transport ignores `initial_codec_chunk_frames`, so the
observed first audio remained 0.84 seconds. A configured value is not proof of
treatment delivery. An explicit implementation needs separate tests and quality
validation before any small-onset performance conclusion.

## Follow-up development screens

`results/service-followup-development.json` retains seven additional screens
and per-request results. Device C has matched original/independent-engine
measurements: engine mean RTF is 0.06244 / 0.20621 / 0.26620 at C1/C16/C32.
Existing K16 Talker plus Torch speaker replay reached approximately
0.07495 / 0.29211 / 0.49040, still above every target. The name
`k16-speaker-onset8` includes an ignored onset flag: first audio stayed 0.84 s.

On device B, two existing Code2Wav replicas on one allocated GPU reached
0.08106 / 0.24861 / 0.43934. Experimental grouped initial-state setup reached
0.08012 / 0.29290 / 0.46508. This device lacks a paired engine run, so these
are development observations, not qualification or cross-device speedups.

An implemented first-eight-frame transport option delivered 0.16 s first
audio, confirming treatment delivery, but did not improve end-to-end RTF
(single replica 0.08040 / 0.29699 / 0.51859). Two replicas likewise failed to
improve over their ordinary-onset screen. This option is rejected for the
current RTF objective. Both experimental patches are retained separately;
neither is part of the submitted S3 implementation. Local contract validation
passed 71 existing transport tests and 133 batch-setup regression tests;
these are correctness screens, not service acceptance.

All recorded quality cells evaluated 64 items successfully. WER, embedding
cosine SIM and UTMOS means do not establish a no-regression verdict: some
small SIM/UTMOS reductions remain unresolved, and the SIM proxy is not the
standalone engine's speaker-verification metric. Final qualification remains
INCONCLUSIVE. A four-replica screen was preempted by a scheduled GPU booking; its last C32
cell failed 61/64 requests. `results/replica4-interrupted.json` retains this
interruption and excludes the incomplete run from acceptance.

The next three hypotheses completed on device D, with a same-allocation
independent-engine comparison in `results/service-phase5-development.json`.
Thinker n-gram plus K16 Talker reached mean RTF 0.06164 / 0.26649 / 0.43239;
the paired engine reached 0.06222 / 0.21053 / 0.26183. The small C1 advantage
is unqualified; C16/C32 still miss the target. WER/SIM/UTMOS do not establish
no regression, so the full goal remains INCONCLUSIVE. TensorRT speaker and
encoder tail capture did not improve the earlier K16 speaker configuration.
A subsequent combination screen is testing n-gram with multiple Code2Wav
replicas and experimental grouped reference setup; it has no results here.

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
