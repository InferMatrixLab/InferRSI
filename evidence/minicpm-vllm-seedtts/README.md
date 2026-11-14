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
The combination screens on device E are retained in
`results/service-phase6-development.json` (36 cells). Two Code2Wav replicas
with n-gram and grouped reference setup reached mean RTF
0.06155 / 0.24457 / 0.34937; the same-allocation independent engine reached
0.06277 / 0.20555 / 0.26662. C16/C32 still miss the target. Four replicas
worsened C32; increasing stage capacity, doubling codec chunks, and a
slot-pool/micro-batch combination also failed to improve the C32 result.
The K32 proposal was not executed: the supported Talker contract ends at K16.

A real-weight synthetic-feature diagnostic measured grouped reference setup
at about 75 ms per four voices versus about 284 ms serially, but cache values
were not identical (maximum estimator attention-cache difference about 0.29).
This establishes neither generated-speech equivalence nor service speedup.
An exploratory paired bootstrap over 64 utterances is retained as uncertainty
analysis, not an acceptance gate. C32 WER worsened in the first two-replica
cell; quality remains unresolved. Development profiling ran only after all
measured latency cells. Torch profiler export dominated the Talker CPU sample,
so that diagnostic cannot establish its normal service bottleneck.

## CPU reference and batch-size follow-up

`results/service-phase78-development.json` adds 42 development cells, with a
paired independent engine on each allocation. CPU reference parallelism was
observed in the live service and passed exact feature checks (16 CPU references,
four real-weight GPU references) plus 198 isolated-source regressions. However,
C32 RTF stayed near 0.349 versus its 0.353 control and the paired engine's 0.264.
Disabling grouped initialization reached about 0.345. Increasing initialization
and CFM micro-batches to eight stayed near 0.347 versus a paired engine at 0.268.
None establishes the requested service outcome. The CPU prototype is archived
as an experimental patch layered on `experimental-batch-setup.patch`, not a
submitted Omni implementation.

A plain initial-state capture diagnostic looked faster than eager execution,
but the configured service already uses inner graphs: its measured setup cost
was mostly 12–17 ms, versus about 25 ms for that plain outer replay. Capturing
around the configured wrappers failed when their nested-capture fallback reached
a cold CPU-to-device frequency table. This direction is rejected in its tested
form; the unconfigured microbenchmark does not describe service performance.

Additional SIM results use the standalone engine's pinned WavLM speaker-
verification source and hash-verified weights. Evaluator packages and identity
are retained, without claiming the standalone engine's full locked environment.
Original Omni C1/C16/C32 means were 51.55 / 51.70 / 51.34 on the x100 scale;
the earlier two-replica candidate scored 50.98 / 51.64 / 50.79. Descriptive
paired bootstrap intervals cross zero, which does not prove non-inferiority.
The original embedding-cosine proxy results remain separately labeled, and
speech-quality qualification remains unresolved.

## Asynchronous history follow-up

`results/service-phase910-development.json` retains 36 additional development
cells, their per-request results and completed speech-quality scores. On the
phase-nine allocation, asynchronous history upload reduced mean C1/C16/C32 RTF
from 0.06631 / 0.26794 / 0.36096 to 0.06307 / 0.25763 / 0.33202.
This is a two-repeat tuning observation, not final qualification. A fresh
phase-ten control reached 0.06214 / 0.23917 / 0.34450; batching its history
commit reached 0.06785 / 0.23567 / 0.34862, while the paired independent engine
reached 0.06300 / 0.21091 / 0.27334. Batched history did not improve the overall
objective. Both patches remain experimental and C16/C32 remain above target.

The asynchronous-history CPU profile places much of the remaining wait in
output parsing. Moving a synchronization location is not proof that all of its
time was eliminated. Neither prototype establishes speech-quality
non-inferiority; the archived WER, SIM and UTMOS scores remain descriptive.

## Sampling-overhead diagnostic

`results/service-phase12-development.json` records a valid-input exponential
sampling prototype layered on asynchronous history upload. Its component
check preserved sampled tokens and generator state in eager and CUDA Graph
execution, including the 6562-token vocabulary. Existing regressions recorded
179 passed and 27 skipped. The prototype omits invalid-probability assertions
and is **not a production patch**; its diagnostic diff is archived separately.

| Mean request RTF, two tuning repetitions | C1 | C16 | C32 |
| --- | ---: | ---: | ---: |
| Asynchronous-history control | 0.06121 | 0.23879 | 0.33334 |
| Sampling prototype | 0.05979 | 0.22041 | 0.31794 |
| Same-allocation independent engine | 0.06223 | 0.20710 | 0.27125 |

All 18 cells completed 64 requests without failures. The prototype improves
its development control, but C16/C32 still miss the engine target. C16 also
has substantial within-server repetition spread; these are not independent
fresh-process measurements. Quality was scored on the first repetition's
saved audio: WER was unchanged at C1/C32 and lower at C16, while speaker
verification SIM fell by about 0.224 and 0.336 points at C16/C32. These
descriptive scores do not establish non-inferiority. No service PASS follows
from the component parity or development latency change.

## Checked sampling and idle-prefetch follow-up

`results/service-phase13-development.json` retains 18 further tuning cells.
The sampler now computes finite/nonnegative/positive-mass validation alongside
argmax and retains a device assertion. Sparse and dense rows at widths 25,
626 and 6562 preserve valid-row tokens and generator state in eager and graph
checks. Invalid-row checks inspect rejection flags without deliberately
poisoning a CUDA context. Existing regressions: 244 passed, 27 skipped.
The experimental patch applies after the asynchronous-history candidate.

| Mean request RTF, two tuning repetitions | C1 | C16 | C32 |
| --- | ---: | ---: | ---: |
| Checked sampler | 0.06066 | 0.23625 | 0.31924 |
| Same sampler, idle-prefetch waiter limit 32 | 0.06051 | 0.24031 | 0.32161 |
| Sequential paired engine | 0.06226 | 0.21039 | 0.26523 |

The larger waiter limit was delivered: both Code2Wav replicas logged a
prefetch phase with multiple waiting references. It did not improve the
objective and is not retained for subsequent candidates. The checked sampler
still misses C16/C32, and its C16 variation prevents a stable benefit claim.
All cells completed 64 requests without failures. Saved-audio scores are
retained as descriptive tuning evidence, not speech-quality qualification.
The overall verdict remains **INCONCLUSIVE**.

## Background CPU reference preparation

`results/service-phase14-development.json` records 18 tuning cells from the
same source snapshot with zero or four background CPU feature workers, followed
by a sequential engine reference on the same reserved GPU. Both replicas logged
submission and consumption of background features. The queue is bounded at 32;
reference files stay pinned until their readers finish. GPU feature completion
remains on the service thread. This is an experimental patch layered on the
checked-sampler snapshot, not a production change.

| Mean request RTF, two tuning repetitions | C1 | C16 | C32 |
| --- | ---: | ---: | ---: |
| CPU prefetch disabled | 0.06070 | 0.23153 | 0.33311 |
| Four background CPU workers | 0.06166 | 0.39736 | 0.33687 |
| Sequential paired engine | 0.06424 | 0.21633 | 0.26031 |

All cells completed 64 requests without failures. CPU features matched exactly
on 16 real references, and complete real-weight prompt features matched on four.
Regressions and lifecycle checks: 247 passed, 27 skipped, including cancellation,
pinning and bounded queues. An isolated CPU diagnostic found roughly 0.048 s for
16 references with four workers versus 0.17 s with one, with one PyTorch thread
per worker in that diagnostic. This local speedup did not translate to the
service. C16 audio chunk gaps increased; graph logs show no cache flushes in
either variant. These observations do not establish the cause of the regression.
The four-worker configuration is not retained.

C1 saved waveforms had identical lengths, with 54/64 PCM-exact pairs and a
maximum sample difference of 0.000214. Two fresh control servers themselves
had 55/64 exact pairs and a maximum difference of 0.000519. Component feature
identity therefore is not presented as complete generated-waveform identity.
Saved-audio quality scores remain descriptive; the service objective remains
**INCONCLUSIVE**.

## Lessons supported by this investigation

- Match component precision to the running service. The HiFT diagnostic in
  `results/hift-service-precision-diagnostic.json` initially compared against
  a forced cuDNN-TF32-off control, but the service already enables TF32.
  Repeating nine real-weight cells with the service precision produced
  identical waveforms and essentially unchanged graph latency. The candidate
  service treatment was pruned; the original microbenchmark is not an
  available service speedup. Both fresh C32 controls were slower than earlier
  allocations, without an established cause; no cross-allocation gain is
  inferred from them.
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
