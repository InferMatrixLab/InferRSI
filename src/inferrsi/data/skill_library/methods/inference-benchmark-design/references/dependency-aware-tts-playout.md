# Dependency-aware TTS playout

Use this reference when designing or auditing a streaming TTS benchmark whose
chunks share model state or are scheduled against estimated playback time.
It derives from [Faster CosyVoice][source] at
`f1049c59196c2c1a890079abc56056b43f27cd1d`, inspected 2026-11-03. The
[source record](faster-cosyvoice-source.json) preserves the exact bounded
readset, file identities and rights. This is source-derived **candidate**
guidance: native/model/device/quality/service execution is **not_run** and
efficacy is **not_evaluated**.

Keep the [parent method](../SKILL.md) and
[task benchmark selection](task-benchmark-selection.md) for quality gates,
reference parity, comparable workloads, statistics and evidence verdicts. This
reference adds the source-specific playout and cost-accounting prerequisites;
it adds no runtime, hardware prerequisite or measured optimization.

## 1. Establish the client event and buffer policy

Before comparing first-audio measurements, record sample rate, channel count,
sample width, encoding, leading-silence policy and the client's playback-buffer
policy. The source client requests mono, 24 kHz, little-endian PCM16. It carries
an odd byte into the next HTTP read and records an audio observation only when
at least one complete sample exists. HTTP reads can split or combine model
chunks; their boundaries are not model chunk identities. [Client][client]

| Source field | Event or quantity | Interpretation limit |
| --- | --- | --- |
| `ttfb_ms` | First nonempty raw response-body read after request start | An odd byte can arrive before any complete PCM sample; a WAV header is a different payload again |
| `first_playable_ms` | First sample-aligned PCM observation | Receipt of complete samples, not a physical speaker measurement or a guaranteed startup buffer |
| `audible_ttfa_ms` | Detected onset placed on the simulated playback clock | Depends on both the onset detector and the playback policy; can be absent when no onset is detected |
| `underruns` | Later arrival events that exceed the simulated playback deadline | Event count, not total missing-audio duration or measured device underruns |
| `audio_s` | Complete received PCM sample count divided by sample rate | Delivered content duration; preserve it alongside latency and completion |

The client's zero-buffer simulation starts playback at the first complete
payload arrival. Each payload extends the deadline by its audio duration. If a
later payload arrives after that deadline, the simulation records an underrun
and restarts playback at the later arrival before adding its duration. Audible
onset uses this rebased clock, rather than adding leading silence directly to
first-body time. [Playback calculation][playback]

Retain the onset detector's parameters when comparing audible latency. This
source uses 20 ms RMS frames, 10 ms hops, per-frame DC removal, a -45 dBFS
threshold and two consecutive active frames. These are the source's detector
settings, not general quality or acceptance gates. Its tests define an onset
case and a late-arrival case; they are test definitions, not executed audio or
service evidence. [Detector][detector] · [Client test definitions][client-tests]

If a supplied report records only HTTP headers, token events or first-body
time, keep first-playable/audible latency unknown until the required event is
available. Do not infer physical playback from this simulation.

## 2. Separate server credit from client playback

Trace the actual PCM bytes credited by the serving path before interpreting a
deadline scheduler. Here, each session retains its first route timestamp and
accumulates routed sample duration. The scheduler estimates its playback
deadline as that timestamp plus the accumulated duration.
[Session accounting][session] · [Deadline policy][scheduler]

The generator marks credit immediately before yielding a nonempty encoded,
optionally trimmed PCM payload. This is the server response-generator boundary;
it is not acknowledgment of network receipt or client consumption. The server's
monotonic clock and the client's request-relative arrival/playback clock must
remain distinct. No client buffer feedback is present in these selected paths.
[PCM production and credit][route]

The source prioritizes established streams within its configured reserve,
then streams without a first PCM payload, then established streams with the
earliest estimated deadline, with admission order resolving ties. The default
reserve is 100 ms in this source. Treat it as source context, not a universal
bar or a guarantee that a client will avoid underruns. Record actual arrival
and playback observations before claiming continuity. [Policy][scheduler] ·
[CLI conversion and validation][arguments]

When leading-silence trimming is enabled, initial output can be buffered and
released only after its bounded onset/buffer decision. Credit uses the resulting
payload length. Record trimming, pre-roll and startup-buffer settings with both
first-payload and audible measurements. Changing initial PCM content does not
establish reduced model computation or a latency benefit for every request.
[Trimmer][detector] · [Documented scope][trim]

## 3. Identify independent batching work and accumulated cost

Inspect the selected planner and session state before treating chunks as
independent jobs. For this model, the first non-final hop includes prompt-token
alignment padding and requires lookahead tokens; lookahead is resent without
being consumed. Later hops grow to the configured cap, and completion drains
the remaining tokens. Nominal hop size alone does not identify the delivered
PCM duration. Use actual output samples for playback credit.
[Chunk planning][planner] · [Model rates][builders]

The serving coroutine awaits each session's submitted chunk. The packed worker
also allows at most one chunk from a given session in a batch because the next
chunk depends on that session's Mel cache. It forms batches from ready jobs
across different sessions, subject to its maximum size and scheduling order.
This is the source's dependency boundary, not proof that an arbitrary caller's
jobs or changed model are independent. [Submission][route] · [Worker][worker]

Flow runs across the selected sessions, after which HiFT finishes each session
separately. Each finish updates accumulated Mel state, vocodes that cache and
returns only waveform samples beyond the previous speech offset. The visible
streaming path also recomputes Flow from the available token prefix. Newly
delivered audio is therefore not a measure of all work performed for that
chunk. [Token2Wav implementation][token2wav]

When auditing a batching or chunk-size claim, retain prompt and lookahead
context, prefix length, accumulated Mel length, actual batch membership and
per-session output duration. Keep queueing, conditioning, vocoding, conversion
and delivery in the declared cost boundary. A packed Flow call does not show
batched HiFT, constant work per emitted chunk, numerical parity or a service
throughput gain. Queue tests using fake workers define selection/dependency
cases only; no native model result follows from them. [Worker test definitions][worker-tests]

## 4. Audit the reported timing and quality boundary

Resolve registered-voice and reference-cache state before comparing cost. A
registered voice reuses prepared conditions; a request-level reference follows
audio decoding/frontend processing and can itself hit the frontend cache.
Record which preparation actually belongs to the timed request.
[Condition resolution][condition] · [Frontend cache][frontend]

| Source measurement or mode | Included boundary | Required interpretation |
| --- | --- | --- |
| Streaming `request_done.ttfa_ms` | Generator-local start through its first nonempty PCM payload | The streaming HTTP handler resolves conditioning before this timer starts; it excludes that earlier preparation and client delivery |
| `stream=false` HTTP response | The same incremental synthesis collected before response delivery | It changes buffering, not the backend into the separate offline static-batch implementation; internal route credit does not observe buffered-response playback |
| Offline `rtf` | Sum of LLM and Token2Wav stage wall times divided by token-derived audio seconds | Frontend time is reported separately; loading, other preparation and output delivery are not a full-pipeline denominator |
| Offline `audio_seconds` | Counted generated token IDs divided by the source's 25-token/s rate | Not measured saved/received PCM duration; the counter is updated before filtering outputs without valid speech tokens |
| Documented RTFx | Audio duration received within a measurement window divided by window duration | Author-reported aggregate throughput; do not replace it with inverse mean per-request RTF or the offline estimate |

Source paths: [HTTP handler][handler], [generator timer][route],
[offline accounting][offline] and [reported metrics][benchmark]. Keep an absent
common timing or audio-duration boundary unresolved rather than comparing
similarly named fields.

The author performance report uses a fixed registered voice/reference, one
NVIDIA Hopper GPU, fixed concurrency, 15 s warmup, a 60 s measurement window,
seed 0 and disabled trimming. Its concurrency-one cumulative ablations report
complete requests without underruns and equal 760 ms first chunks. Preserve
these conditions when citing the report; the exact Hopper SKU, raw timing
records and independent reproduction are not established here.
[Reported workload][reported] · [Ablation conditions][benchmark]

The quality table reports a target-only versus DSpark comparison over 2,020
paired Chinese Seed-TTS samples decoded with Paraformer. It does not establish
speaker similarity, perceptual quality, every cumulative optimization's quality
or another workload's result. Keep its character-error protocol and per-row
conditioning scope distinct from fixed-voice performance. The inspected release
tree contains no raw benchmark/evaluator receipts; that does not establish
whether external receipts exist. [Author quality report][quality]

Return a benchmark contract or audit note identifying the event/buffer policy,
server-credit origin, dependent state, actual timed stages, delivered-duration
denominator, quality scope and missing evidence. If a required event, native
dispatch, output, evaluator or common boundary is missing, withhold the affected
comparison or gain claim. Use the parent method's frozen gates and verdicts for
any separately authorized campaign.

## Source and rights limits

The pinned tree has no repository-level license/notice file and its package
metadata declares no license, so overall source rights remain **UNKNOWN**.
Selected NVIDIA and Alibaba files have Apache-2.0 headers; those do not license
other files. The vendored HiFT generator names unpinned HiFi-GAN,
ParallelWaveGAN and BigVGAN origins, and Nari-compatible comments do not resolve
implementation lineage. Exact header scopes, unresolved inheritance and other
unlicensed files remain in the [source record](faster-cosyvoice-source.json).

This reference contains original analysis and immutable links. It copies no
upstream implementation, patch, audio, model, dataset, paper or figure. Source
dependency/model names are inspection context, not a tested stack or permission
to install or execute it. Recheck changed source contracts before transferring
the procedure; no native, quality, performance or efficacy result is implied.

[source]: https://github.com/yuekaizhang/faster-cosyvoice/tree/f1049c59196c2c1a890079abc56056b43f27cd1d
[client]: https://github.com/yuekaizhang/faster-cosyvoice/blob/f1049c59196c2c1a890079abc56056b43f27cd1d/examples/stream_client.py#L85-L134
[playback]: https://github.com/yuekaizhang/faster-cosyvoice/blob/f1049c59196c2c1a890079abc56056b43f27cd1d/examples/stream_client.py#L27-L51
[detector]: https://github.com/yuekaizhang/faster-cosyvoice/blob/f1049c59196c2c1a890079abc56056b43f27cd1d/faster_cosyvoice/server/leading_silence.py#L1-L88
[client-tests]: https://github.com/yuekaizhang/faster-cosyvoice/blob/f1049c59196c2c1a890079abc56056b43f27cd1d/tests/test_stream_client.py#L6-L22
[session]: https://github.com/yuekaizhang/faster-cosyvoice/blob/f1049c59196c2c1a890079abc56056b43f27cd1d/faster_cosyvoice/streaming/session.py#L17-L37
[scheduler]: https://github.com/yuekaizhang/faster-cosyvoice/blob/f1049c59196c2c1a890079abc56056b43f27cd1d/faster_cosyvoice/streaming/token2wav_scheduler.py#L46-L122
[route]: https://github.com/yuekaizhang/faster-cosyvoice/blob/f1049c59196c2c1a890079abc56056b43f27cd1d/faster_cosyvoice/server/openai_speech.py#L52-L128
[arguments]: https://github.com/yuekaizhang/faster-cosyvoice/blob/f1049c59196c2c1a890079abc56056b43f27cd1d/faster_cosyvoice/server/arguments.py#L273-L336
[trim]: https://github.com/yuekaizhang/faster-cosyvoice/blob/f1049c59196c2c1a890079abc56056b43f27cd1d/docs/usage.md#L198-L202
[planner]: https://github.com/yuekaizhang/faster-cosyvoice/blob/f1049c59196c2c1a890079abc56056b43f27cd1d/faster_cosyvoice/streaming/chunker.py#L20-L55
[builders]: https://github.com/yuekaizhang/faster-cosyvoice/blob/f1049c59196c2c1a890079abc56056b43f27cd1d/faster_cosyvoice/token2wav/builders.py#L16-L50
[worker]: https://github.com/yuekaizhang/faster-cosyvoice/blob/f1049c59196c2c1a890079abc56056b43f27cd1d/faster_cosyvoice/streaming/token2wav_batcher.py#L79-L183
[token2wav]: https://github.com/yuekaizhang/faster-cosyvoice/blob/f1049c59196c2c1a890079abc56056b43f27cd1d/faster_cosyvoice/token2wav/token2wav.py#L153-L226
[worker-tests]: https://github.com/yuekaizhang/faster-cosyvoice/blob/f1049c59196c2c1a890079abc56056b43f27cd1d/tests/test_token2wav_batcher.py#L57-L320
[condition]: https://github.com/yuekaizhang/faster-cosyvoice/blob/f1049c59196c2c1a890079abc56056b43f27cd1d/faster_cosyvoice/server/openai_speech.py#L31-L49
[frontend]: https://github.com/yuekaizhang/faster-cosyvoice/blob/f1049c59196c2c1a890079abc56056b43f27cd1d/faster_cosyvoice/token2wav/frontend.py#L91-L139
[handler]: https://github.com/yuekaizhang/faster-cosyvoice/blob/f1049c59196c2c1a890079abc56056b43f27cd1d/faster_cosyvoice/server/app.py#L143-L173
[offline]: https://github.com/yuekaizhang/faster-cosyvoice/blob/f1049c59196c2c1a890079abc56056b43f27cd1d/examples/offline_inference.py#L240-L308
[benchmark]: https://github.com/yuekaizhang/faster-cosyvoice/blob/f1049c59196c2c1a890079abc56056b43f27cd1d/docs/benchmark.md#L9-L49
[reported]: https://github.com/yuekaizhang/faster-cosyvoice/blob/f1049c59196c2c1a890079abc56056b43f27cd1d/README.md#L120-L135
[quality]: https://github.com/yuekaizhang/faster-cosyvoice/blob/f1049c59196c2c1a890079abc56056b43f27cd1d/docs/benchmark.md#L74-L84
