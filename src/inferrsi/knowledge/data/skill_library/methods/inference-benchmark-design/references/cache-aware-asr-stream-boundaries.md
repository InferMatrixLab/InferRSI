# Cache-aware ASR stream boundaries

Use this reference before comparing chunk latency, decoded progress or streaming
recognition quality for the cache-aware RNNT path in
[NVIDIA/NeMo-Speech.cpp][source]. It is source-derived candidate guidance at
`20999cc921d2b14aa58708f61756a8b2e787ba20`, inspected 2026-11-01. Native tests,
models, devices, ASR quality, long-audio stress and serving performance were
**not run**. Recheck the selected model and code when applying it elsewhere.

Keep the parent [benchmark method](../SKILL.md) for comparable workloads,
precision, warmup, quality gates, SLOs and evidence verdicts. This reference adds
the ASR state and time prerequisites; it does not qualify a serving engine or
prescribe an optimization.

## Establish the model and state boundary

Record the exact GGUF/model revision, backend, feature hop/sample rate,
subsampling factor, right/left context, overlap/drop policy, packetization,
decoder and endpoint configuration before choosing tests or timing a change.
Resolve right context before the shared encoder session is built. The runner
and session derive geometry through `make_cache_aware_config`; calling an
override after construction is not a supported way to reconfigure topology.
The visible post-build exception guard checks a previously recorded nonnegative
override, so do not assume every differing late call raises.
[Configuration and session construction][session] · [shared derivation][derive]

| Owner / lifetime | State to preserve or inspect |
| --- | --- |
| Model / encoder lifetime | One lazily constructed encoder session and persistent cache arenas shared by streams |
| Stream lifetime | Move-only cache handle selecting a slot, ring head, mel overlap, host attention mask and absolute emitted-frame clock |
| Utterance output lifetime | Transcript, tokens and word output captured at EOU; this boundary does not end the acoustic stream |

The encoder's state destructor releases a slot by marking it dirty. A later
acquisition carries a reset flag into the batch, which clears selected K/V and
convolution rows before running. Explicit `reset_state` clears the existing
slot and its ring head. Do not describe release as immediate device zeroing or
every reset as allocating another slot. Arena exhaustion raises; it is not a
fallback to an untracked stream.
[State interface][state] · [release, acquisition and reset][slots] ·
[deferred batch reset][batch-reset]

These are source observations. They do not establish cross-stream isolation,
backend synchronization correctness, memory capacity or throughput under load.

## Derive first, steady and decoded coordinates separately

For this runner, let `sub` be the selected subsampling factor and `R` the right
context. Its overlap is nine mel frames and its chunked-limited drop policy is
declared separately. Derive:

```text
first input mel frames = 1 + sub * R
steady input mel frames = 9 + sub * (1 + R)
encoder frames per chunk = 1 + R
decoded mel frontier = 0 if emitted == 0 else 1 + (emitted - 1) * sub
```

The overlap constant belongs to the pinned runner/model policy; it is not a
universal consequence of subsampling. The first chunk has no preceding overlap
to discard. The geometry test independently checks the first and steady output
lengths, including the steady `cache_drop_extra`, rather than applying the same
startup length to both. At `R=0`, negative history is padded only after the first
real chunk is encoded.
[Geometry helpers][geometry] · [runner policy][policy] ·
[chunk production][chunks] · [shape checks][shape-test]

For the source's `sub=8, R=13` example, first input is 105 mel frames, steady
input is 121, and each chunk emits 14 encoder frames. Fourteen emitted frames
cover 105 real mel frames, not 112. At a 10 ms hop, using the latter clock moves
an endpoint 70 ms early. The source test checks an 800 ms silence threshold
against this distinction. These are source equations and a test definition,
not locally measured timing or a recommended universal threshold.

Use the decoded mel frontier for VAD scanning and `audio_processed` progress;
queued audio includes lookahead. The runner also caps progress by available
audio. Token-silence endpointing uses its decoder-frame clock instead of the
VAD mel timeline. Word attribution has a receptive-field center coordinate,
which is separate again from the causal end/frontier coordinate.
[Progress and endpoint clocks][clocks] · [frame-center definition][geometry] ·
[independent receptive-field checks][center-test]

## Select the correct event contract

| Event | Pinned behavior | Check before accepting a change |
| --- | --- | --- |
| Mid-stream EOU | Capture utterance output after head finalization, then call `reset_utterance`. Retain acoustic cache, mel overlap and absolute stream clock; do not synthesize EOF tail frames. Forced EOU publishes after all currently decodable chunks. | Compare forced/no-EOU controls with identical feature packet shapes; require unchanged encoder output/cache and steady geometry after EOU. |
| Actual EOF / `finalize()` | Suppress mid-stream endpoint fires while draining; flush the VAD timeline before tail masking, drain whole chunks, pad remaining mel tail, finalize the head and bound output words. | Keep tail words within real audio; include empty/short inputs, odd and 100 ms packets, and repeated finalization without duplicate new tokens. |
| Full stream `reset()` | Clear audio/mel/frontier/output/decoder counters, restore first-chunk geometry and request cache reset for an allocated state. | Repeat startup with the same feature packet shapes; require reset first encoder output to match the initial output and clocks to restart. |

Source paths: [EOU capture][eou-output], [EOU dispatch][eou], [EOF][eof],
[full reset][reset], and [model comparison definitions][model-test]. A decoder's
`reset_utterance` is a distinct call from full reset; its predictor internals and
the model wrapper's reset dispatch were not independently audited in this
readset. The EOU control test compares encoder state/output, not general decoder
quality.

Endpoint policy is another layer: threshold firing requires enable plus an
armed speech history; new speech re-arms it. A forced endpoint works regardless
of enable, and reset clears latches while preserving a per-request threshold
override. A latched EOU event alone does not imply stream/cache destruction.
[Endpoint implementation][endpoint] · [endpoint API and override][endpoint-api]

The runner bounds word frames before consumers read them. The SDK additionally
bounds milliseconds by the input's original-rate duration, and final progress
uses that original duration after resampling. The source test checks a 0.64 s
JFK prefix at 16 and 8 kHz through stream/offline paths and requires the R13
streamed tail word to survive. This bounded fixture is not proof of quality or
word alignment on a corpus.
[SDK word bounds][word-bounds] · [SDK final progress][final-progress] ·
[word-bound test definitions][word-test]

## Choose tests without hiding skipped coverage

The existing target is `test_cache_stream_geometry`. CTest supplies the optional
`NEMO_SPEECH_TEST_CACHE_AWARE_RNNT_MODEL` path; it is kept separate from the
general ASR-model variable because a CTC model is insufficient.
[Target wiring][cmake]

| Invocation / resource | Defined coverage | Evidence limit |
| --- | --- | --- |
| `test_cache_stream_geometry` without a model | Shape/decode-clock checks for R=0,1,3,6,13; receptive-field centers for subsampling 2,4,8 | Prints a model-check SKIP followed by a geometry PASS; no model state behavior is exercised |
| `test_cache_stream_geometry MODEL.gguf` with a matching cache-aware RNNT model and repository fixtures | Actual chunk assembly/reference output, reset, EOF/EOU, first-word coordinates and EOF word bounds for R=0,3,6,13 | Requires the matching built engine, model and JFK sample; no run is established here |
| The same model invocation with `--gpu N` | Requests the specified GPU in that test configuration | An argument or configured backend is not proof of executed dispatch or device correctness |

Inspect the [test entry point][test-entry] and retain its actual stdout/stderr,
model/code revisions, backend and skipped checks when separately authorized to
run it. Do not copy the test's local tolerance into a general acceptance gate.
Long streams, slot reuse/crosstalk, repeated requests and saturation need their
own real workload and failure accounting; these short geometry fixtures do not
establish those outcomes.

If a source revision or geometry policy differs, rederive the affected contract
before comparing results. If a model, backend or required fixture is absent,
record the missing coverage and stop that claim. Do not substitute a Python
simulation, fake decoder or shape-only PASS for the native model test.

## Interpret the author ASR benchmark

`BENCHMARK.md` reports Nemotron Speech Streaming EN 0.6B on LibriSpeech test-clean.
Retain the following qualifications before reusing its results:

- NeMo-Speech.cpp uses Q8_0 GGUF weights; NeMo uses FP32. This is an engine and
  configuration comparison, not an isolated measurement of quantization benefit.
- NeMo's chunk compute and audio-duration/wall-time throughput exclude feature
  extraction, which its example performs per utterance. Declare a common boundary
  before making a new comparison.
- The CPU result uses every 26th test-clean utterance: 100 utterances, 40 speakers,
  13.3 minutes. The GPU table identifies the full 2,620-utterance, 5.4-hour corpus.
- The report gives three NeMo-Speech.cpp trials versus one NeMo trial for RTX
  4090 and CPU. Spark repetitions are not specified in the ASR trial row.
- Preserve device/software/thread settings, R13 versus R1 chunk presets, WER
  normalization and failures. WER is a quality observation separate from compute
  latency and RTFX. No reported figure is a local reproduction or L4 service gain.

[Author ASR tables][benchmark-tables] · [devices][benchmark-devices] ·
[ASR methodology and command][benchmark-method]

## Retained readset and rights

All paths below belong to the fixed source commit above. The readset is closed
for the stated claims, not for a complete build/dependency audit. Decoder/model
wrapper internals, actual encoder kernels, feature/resampler numerical parity,
server transport, concurrency test bodies and TTS are outside the inspected scope.

| Source path | Inspected responsibility |
| --- | --- |
| `src/asr/encoder/cache_aware_encoder.cpp` | Session/config and stream-slot lifecycle |
| `src/asr/encoder/cache_aware_encoder.h` | State interface and ownership |
| `src/asr/encoder/fastconformer.h` | Causal geometry/configuration helpers |
| `src/asr/runner.cpp` | Chunk production, clocks, reset, EOU/EOF and word bounding |
| `src/asr/runner.h` | Runner overlap/drop policy and lifetime fields |
| `src/asr/recognizer.cpp` | SDK routing, original-rate progress and millisecond bounds |
| `src/asr/vad/vad_endpointer.cpp` | Endpoint state transitions |
| `src/asr/vad/vad_endpointer.h` | Endpoint clock/configuration contract |
| `tests/cpp/asr/test_cache_stream_geometry.cpp` | Source test definitions, not executed results |
| `tests/cpp/asr/CMakeLists.txt` | Native test and optional model wiring |
| `BENCHMARK.md` | Author ASR report only; TTS results excluded |
| `LICENSE`, `NOTICE`, `THIRD_PARTY_NOTICES.md` | Source license and attribution inventory |

The selected code/CMake files identify Apache-2.0. FastConformer additionally
identifies portions derived from Jason Ni's parakeet.cpp under MIT; the retained
third-party notice names its pinned origin. Preserve NVIDIA and Jason Ni
attribution when adapting this material. This reference paraphrases mechanisms
and links source; it vendors no upstream code, audio, model or dataset. Repository
rights do not grant rights to separately retrieved model/dependency material.
[FastConformer attribution][attribution] · [Apache license][license] ·
[repository notice][notice] · [parakeet origin][parakeet] · [MIT text][mit]

[source]: https://github.com/NVIDIA/NeMo-Speech.cpp/tree/20999cc921d2b14aa58708f61756a8b2e787ba20
[session]: https://github.com/NVIDIA/NeMo-Speech.cpp/blob/20999cc921d2b14aa58708f61756a8b2e787ba20/src/asr/encoder/cache_aware_encoder.cpp#L232-L285
[derive]: https://github.com/NVIDIA/NeMo-Speech.cpp/blob/20999cc921d2b14aa58708f61756a8b2e787ba20/src/asr/runner.cpp#L823-L840
[state]: https://github.com/NVIDIA/NeMo-Speech.cpp/blob/20999cc921d2b14aa58708f61756a8b2e787ba20/src/asr/encoder/cache_aware_encoder.h#L23-L76
[slots]: https://github.com/NVIDIA/NeMo-Speech.cpp/blob/20999cc921d2b14aa58708f61756a8b2e787ba20/src/asr/encoder/cache_aware_encoder.cpp#L287-L364
[batch-reset]: https://github.com/NVIDIA/NeMo-Speech.cpp/blob/20999cc921d2b14aa58708f61756a8b2e787ba20/src/asr/encoder/cache_aware_encoder.cpp#L118-L125
[geometry]: https://github.com/NVIDIA/NeMo-Speech.cpp/blob/20999cc921d2b14aa58708f61756a8b2e787ba20/src/asr/encoder/fastconformer.h#L64-L129
[policy]: https://github.com/NVIDIA/NeMo-Speech.cpp/blob/20999cc921d2b14aa58708f61756a8b2e787ba20/src/asr/runner.h#L301-L311
[chunks]: https://github.com/NVIDIA/NeMo-Speech.cpp/blob/20999cc921d2b14aa58708f61756a8b2e787ba20/src/asr/runner.cpp#L910-L1004
[shape-test]: https://github.com/NVIDIA/NeMo-Speech.cpp/blob/20999cc921d2b14aa58708f61756a8b2e787ba20/tests/cpp/asr/test_cache_stream_geometry.cpp#L24-L54
[clocks]: https://github.com/NVIDIA/NeMo-Speech.cpp/blob/20999cc921d2b14aa58708f61756a8b2e787ba20/src/asr/runner.cpp#L1067-L1133
[center-test]: https://github.com/NVIDIA/NeMo-Speech.cpp/blob/20999cc921d2b14aa58708f61756a8b2e787ba20/tests/cpp/asr/test_cache_stream_geometry.cpp#L56-L85
[eou-output]: https://github.com/NVIDIA/NeMo-Speech.cpp/blob/20999cc921d2b14aa58708f61756a8b2e787ba20/src/asr/runner.cpp#L91-L127
[eou]: https://github.com/NVIDIA/NeMo-Speech.cpp/blob/20999cc921d2b14aa58708f61756a8b2e787ba20/src/asr/runner.cpp#L1091-L1133
[eof]: https://github.com/NVIDIA/NeMo-Speech.cpp/blob/20999cc921d2b14aa58708f61756a8b2e787ba20/src/asr/runner.cpp#L1171-L1246
[reset]: https://github.com/NVIDIA/NeMo-Speech.cpp/blob/20999cc921d2b14aa58708f61756a8b2e787ba20/src/asr/runner.cpp#L1250-L1280
[model-test]: https://github.com/NVIDIA/NeMo-Speech.cpp/blob/20999cc921d2b14aa58708f61756a8b2e787ba20/tests/cpp/asr/test_cache_stream_geometry.cpp#L259-L443
[endpoint]: https://github.com/NVIDIA/NeMo-Speech.cpp/blob/20999cc921d2b14aa58708f61756a8b2e787ba20/src/asr/vad/vad_endpointer.cpp#L8-L33
[endpoint-api]: https://github.com/NVIDIA/NeMo-Speech.cpp/blob/20999cc921d2b14aa58708f61756a8b2e787ba20/src/asr/vad/vad_endpointer.h#L38-L65
[word-bounds]: https://github.com/NVIDIA/NeMo-Speech.cpp/blob/20999cc921d2b14aa58708f61756a8b2e787ba20/src/asr/recognizer.cpp#L630-L652
[final-progress]: https://github.com/NVIDIA/NeMo-Speech.cpp/blob/20999cc921d2b14aa58708f61756a8b2e787ba20/src/asr/recognizer.cpp#L717-L735
[word-test]: https://github.com/NVIDIA/NeMo-Speech.cpp/blob/20999cc921d2b14aa58708f61756a8b2e787ba20/tests/cpp/asr/test_cache_stream_geometry.cpp#L198-L257
[cmake]: https://github.com/NVIDIA/NeMo-Speech.cpp/blob/20999cc921d2b14aa58708f61756a8b2e787ba20/tests/cpp/asr/CMakeLists.txt#L12-L18
[test-entry]: https://github.com/NVIDIA/NeMo-Speech.cpp/blob/20999cc921d2b14aa58708f61756a8b2e787ba20/tests/cpp/asr/test_cache_stream_geometry.cpp#L445-L465
[benchmark-tables]: https://github.com/NVIDIA/NeMo-Speech.cpp/blob/20999cc921d2b14aa58708f61756a8b2e787ba20/BENCHMARK.md#L3-L35
[benchmark-devices]: https://github.com/NVIDIA/NeMo-Speech.cpp/blob/20999cc921d2b14aa58708f61756a8b2e787ba20/BENCHMARK.md#L88-L115
[benchmark-method]: https://github.com/NVIDIA/NeMo-Speech.cpp/blob/20999cc921d2b14aa58708f61756a8b2e787ba20/BENCHMARK.md#L117-L141
[attribution]: https://github.com/NVIDIA/NeMo-Speech.cpp/blob/20999cc921d2b14aa58708f61756a8b2e787ba20/src/asr/encoder/fastconformer.h#L1-L6
[license]: https://github.com/NVIDIA/NeMo-Speech.cpp/blob/20999cc921d2b14aa58708f61756a8b2e787ba20/LICENSE
[notice]: https://github.com/NVIDIA/NeMo-Speech.cpp/blob/20999cc921d2b14aa58708f61756a8b2e787ba20/NOTICE
[parakeet]: https://github.com/NVIDIA/NeMo-Speech.cpp/blob/20999cc921d2b14aa58708f61756a8b2e787ba20/THIRD_PARTY_NOTICES.md#L204-L211
[mit]: https://github.com/NVIDIA/NeMo-Speech.cpp/blob/20999cc921d2b14aa58708f61756a8b2e787ba20/THIRD_PARTY_NOTICES.md#L255-L276
