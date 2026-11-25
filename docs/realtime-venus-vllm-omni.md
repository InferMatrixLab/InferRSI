# Realtime-Venus: day-0 adaptation in vLLM-Omni

This case records an Omni-checkpoint adaptation and a bounded execution-mode
experiment. The governing [acceptance issue](https://github.com/InferMatrixLab/InferRSI/issues/593)
owns revision pins, frozen conditions, run outcomes and the downstream PR link.
The overall conclusion is **INCONCLUSIVE** for full model parity and general
performance: basic generation does not validate the external delegation runtime,
long-video memory, perceptual speech quality or sustained duplex service.

## What failed before generation

The [released repository](https://huggingface.co/inclusionAI/Realtime-Venus)
contains separate Omni and Audio checkpoints. The Omni child `config.json` is a
reference to a separately pinned root YAML, rather than a complete language
model configuration. Treating the child as an ordinary Qwen3 config loses the
backbone dimensions and the version used by the stage router.

With Transformers 5.20.2, the released configuration code also calls the removed
`_set_token_in_kwargs` API. Loading the released image processor hits another
incompatibility: its legacy registration uses a string where the current
`AutoImageProcessor.register` API expects a configuration class. These were
observed startup failures, not hypothetical compatibility concerns.

The adaptation uses a native config class that reads the sibling root YAML,
verifies its referenced SHA-256 and identity, and constructs the nested vision,
audio, TTS and slice configurations. Both `get_config_dict` and `from_dict`
need coverage: `AutoConfig` can select the registered class and call `from_dict`
without going through that class's `get_config_dict`. A direct-class unit test
alone missed that second path during bring-up.

The processor fix shares the existing MiniCPM compatibility context, ignores
only the two known redundant string registrations and restores the registration
method on success or failure. The tokenizer and processor still require trusted
checkpoint code. The config adapter deliberately requires a complete local
snapshot; it does not silently fetch a different root YAML on an offline host.

## Reuse boundaries matter

The Omni architecture derives from MiniCPM-o 4.5. Its stage pipeline can reuse
the existing Thinker, Talker and Code2Wav implementations, including compiled
execution and Talker multi-frame decoding. A separate architecture-to-pipeline
mapping and deployment overlay are sufficient; copying the model kernels would
create another implementation to maintain without solving the loader failures.

Reuse does not imply that every inherited tuning choice preserves the released
checkpoint's behavior. The existing MiniCPM CUDA recipe uses five Flow steps and
FP16 Flow weights. The Venus overlay retains ten steps and FP32 Flow, disables
the Flow TF32 override, and uses one codec replica. Those choices separate an
execution optimization from an unvalidated sampling or precision change.

Venus also introduces `<delegate>…</delegate>` spans. The native duplex handoff
must remove the same rows from token IDs and hidden states, retain the text
stream, carry masking state across units, and reset it at a turn boundary.
The follow-up adds an explicit full-duplex deployment and completes the speech
boundary handling. A fully muted unit flushes preceding speech using only the
Talker's audio-begin embedding, a 26-token ceiling and no minimum. The codec
bridge drains its pending frames and resets the vocoder without closing the
dialogue turn. Later silent units do not synthesize again; newly spoken content
replaces the Talker prompt and KV. The real turn terminator still closes the
dialogue, including when its speech row was masked by an unclosed delegation.

Filtering alone also missed an output-contract problem: the shared data plane
normally waits for waveform frames before publishing text. An intentionally
silent delegation needs its text delivered immediately. Model-owned metadata
now carries that distinction through Talker and Code2Wav; the bridge consumes
the queued text at the silent unit boundary and the data plane deduplicates it
by cache epoch and chunk sequence. It cannot be lost or replayed with later
speech. Regression tests cover the full producer-to-consumer metadata path.

These changes reuse the existing session engine, model-native listen/speak
policy, input append and interruption mechanisms. The external asynchronous
delegation executor and long-video memory runtime remain outside this adapter.

## Full-duplex follow-up lessons

The turn profile and `realtime_venus_omni_duplex.yaml` both retain ten-step FP32
Flow. Switching the serving mode is necessary but does not prove the model's
session behavior: exercise speech and dialogue boundaries independently, then
verify the actual public text/audio events.

A subsequent configuration-only change makes `realtime_venus_omni.yaml` default
to full duplex, including automatic deployment selection. The `_duplex.yaml`
profile remains an equivalent alias; `_turn.yaml` explicitly selects ordinary
HTTP serving. Resolving all inherited fields confirms that the new default
matches the previously tested duplex configuration and the explicit turn profile
matches the previous default. The historical measurements below keep their
original source pins and serving modes; changing a default is not a new benchmark.

The model's delegation capability also differs from serving-side tool execution:
the official [Harness](https://github.com/inclusionAI/Realtime-Venus/tree/main/harness)
executes `<delegate>` requests and returns `<backend>` feedback. The current
adapter preserves delegate text without speaking it, but does not integrate that
executor or translate delegates into OpenAI `tool_calls`.

The first paced audio/video probe used a short “Hello, welcome” waveform. The
model chose to listen for all twenty units; there was no protocol error, but
also no generated audio. That establishes input acceptance only. A separate
text-seeded duplex probe produced a spoken introduction and returned to
listening. Neither result alone establishes multi-turn audio conversation or
interruption recovery.

Widening the CPU check to the vocoder's isolated import test caught a new circular
import: placing transport constants under the duplex package caused Code2Wav
to import the plugin, which imports Code2Wav. Moving the constants to the shared
handoff module fixed the ownership boundary without duplicating their strings.
This illustrates why a passing in-process suite can miss an import-order defect.

Follow-up functional results are retained separately from the earlier HTTP
measurement. They are not extra repetitions of that experiment, and its latency
ratio is not a full-duplex speedup claim.

At downstream commit `59b193b992ce3d6b5c80a583bac7d82f8a43474e`, the related
CPU regression run completed with 681 passed and six CUDA-embedding cases
skipped. Applicable pre-commit hooks passed. A paced 30-second synthetic video
plus eight seconds of tail input produced four completed responses and nine
audio chunks at 24 kHz, with no protocol errors. Its first color answer was
wrong; this is transport/lifecycle evidence, not semantic acceptance.

The natural-input lifecycle probe resumed the same WebSocket session, asked
about a red circle, cancelled the first spoken response, then asked about a
blue circle in the same session. Transcripts were “红色。” then “蓝色。”; the
first response terminated as cancelled and the second completed. No audio
from the cancelled response arrived after cancellation acknowledgement, and
session close completed without protocol errors. A separate seeded-story
probe also recovered transport after cancellation, but resumed its initial
story context rather than answering the new scene question; it is not evidence
of semantic interruption recovery.

An untimed Transformers 4.51.3 reference check used the released duplex class
on the same 38 audio/video units with speech synthesis disabled and greedy
decoding. It also produced incorrect descriptions on the complex fixture.
The adapted service used its default sampling, so these runs do not establish
token parity or identify the cause of either model's wrong answers. The
[functional summary](../evidence/realtime-venus-day0/results/duplex-functional.json)
retains the outputs and separates them from the prior managed performance round.

Review subsequently found that the archived lifecycle script's gate could also
accept a failed or pre-input audio response. The positive trace above remains
a historical observation, but that script cannot qualify a new run. The
[revised probe](../tools/realtime_venus_lifecycle.py) waits for matching cancel
and input-clear acknowledgements, binds a new response to the fresh-input
phase, and requires nonempty audio plus terminal `completed`. Its
[replay instructions](../evidence/realtime-venus-day0/validator/README.md)
distinguish offline regression coverage from the unperformed live-model rerun.

## Validation and experiment boundaries

A tokenizer warning was checked against the isolated Transformers 4.51.3
reference. Nine fixed English, Chinese, mixed-Unicode, whitespace and special-token
inputs produced identical token IDs under 5.20.2 after the native config
registration. This is sample parity, not an exhaustive tokenizer proof; no regex
rewrite was applied to the checkpoint.

The task entered InferRSI through `skills enter task-day-0`, inspected the
checkpoint's configuration and reference implementation, and first established
real-weight generation. The isolated Transformers 4.51.3 reference produced the
expected Paris and red-image answers. The adapted HTTP service returned text,
image answers and speech audio. An initial text request exhausted its token
budget in a thinking span; subsequent fixed requests explicitly disabled
thinking and rejected truncated completions. Startup and first-request timings
are not used as an optimization baseline.

At the submitted downstream revision, automatic deployment selection also served
a fixed Chinese question and a short red/blue video correctly. Audio round-trip
checking exposed why structural WAV validation is insufficient: the initial
bring-up waveform produced unrelated marker-like transcriptions in both
vLLM-Omni and the isolated reference. A waveform generated by the final Venus
profile transcribed as “Hello, welcome.” in both implementations, including
both reference TTS-template settings. The initial/final generation settings also
differed in the thinking template, so this does not isolate Flow precision or
step count as the cause. Perceptual speech quality remains unqualified.

The managed project experiment uses `campaign start`, `campaign diagnose` and
one `campaign round`. Its common source is the already adapted model. The only
candidate change is Thinker `enforce_eager=true` to `false`; it does not compare
an unsupported upstream model against a working implementation. Model weights,
Flow settings, speculation and workload stay fixed.

The issue freezes a small C1 HTTP workload, warmup policy, point metric and
exact-text comparison before execution. It also distinguishes structural WAV
validation from speech-quality scoring. The initial trace places text generation
in stage 0; it does not independently prove that launch overhead is the dominant
bottleneck. Compilation/CUDA-graph benefit is therefore a tested hypothesis,
not a diagnosis inferred from the model family.

The operator requested one baseline measurement and one candidate measurement.
No repeated sampling or independent `campaign final` retest is authorized. The
managed round's retained observations are reported as exploratory evidence; the
campaign is not presented as finalized. There is no confidence interval, service
SLO, broad quality acceptance or full-duplex speedup claim.

## Reproduce the contribution

The contribution in
[vLLM-Omni PR #10976](https://github.com/vllm-project/vllm-omni/pull/10976)
merged on 2026-11-24 as
[`123c96e4a81a597e08526d46c54dc2325fc01488`](https://github.com/vllm-project/vllm-omni/commit/123c96e4a81a597e08526d46c54dc2325fc01488).
Use this immutable revision for the integrated contribution. The observations
and validation limits in this case refer to the earlier issue-pinned sources;
they do not qualify changes added between those sources and the merged revision.
Follow its recipe to download the Omni subdirectory and root YAML together,
then serve the local model path with the Venus deployment overlay. Preserve the
root YAML when moving the checkpoint to an offline host.

Run the configuration, native-duplex-hook and Thinker-to-Talker handoff tests
listed in that PR. For performance work, declare a new issue-scoped workload,
quality gate and budget; freeze its protocol before measuring. Do not copy the
exploratory latency threshold as an acceptance default for other hardware or
service traffic.

The [compact evidence bundle](../evidence/realtime-venus-day0/README.md) retains
the frozen measurement scripts and derived summary. The local original logs
and managed source snapshots remain retained by the
operator. They are not a published, independently downloadable archive; external
replay of those exact originals is unverified. The PR and acceptance issue
provide the public code, commands, compact outcomes and explicit limitations.
This case does not promote a reusable knowledge-library record or a campaign
`PASS` on the basis of unarchived smoke results.
