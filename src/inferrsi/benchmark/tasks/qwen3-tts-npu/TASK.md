# Standalone Qwen3-TTS CustomVoice on one Ascend NPU

Optimize real text-to-audio synthesis with the complete Qwen3-TTS 1.7B
CustomVoice checkpoint. The bundled reference owns text/instruction preparation,
Talker/code predictor orchestration, speech-tokenizer decode, PCM conversion,
HTTP serving and a bounded single-owner queue. It uses official qwen-tts model
components. No vLLM/vLLM-Omni checkout or inference engine is required.

## Reference and candidate

The v2 task replaces the former engine-backed reference. Do not combine results
across those baselines. Source provenance is in sources.json; exact model files,
revision, sizes and SHA256 are in model-assets.json. baseline.py verifies every
asset and blocks actual imports of vllm, vllm_omni, sglang, sglang_omni and the
historical qwen3_tts_engine. Runtime: PyTorch/torch_npu/CANN, qwen-tts==0.1.1 and
transformers==4.57.3, real model and speech tokenizer, BF16, one allocated NPU.

Read inference.py for text preparation, model generation, codec decode and PCM;
read service.py for scheduling and delivery. Copy the frozen reference to an
independent candidate source directory. Optimize those components or adapt
official model code within the candidate, with attribution and actual loaded
source hashes. Record all dependency versions and compatibility changes.

Keep weights, tokenizer, speakers, language, generation parameters and device
budget fixed. Preserve full text, natural stop semantics and request isolation.
Return complete 24 kHz mono PCM16 through the speech SSE API. Input/output
memoization, dropping words, shortening responses, changing sampling or leaking
speaker/state between requests violate the task. Weight-only preparation needs
invalidation and separate cost records.

The reference generates the full waveform before one SSE PCM event; it is not
an incremental audio generator. Its TTFA includes full generation. Candidates
may optimize real incremental generation, streaming codec, batching, caching,
operators, synchronization and queueing while preserving frozen quality gates.

## Execute and measure

The scenario CLI has prepare / serve / collect / assess. prepare freezes all
task files, texts and caller-selected gates. serve verifies the reference and
executes its baseline.py in the caller's one-NPU allocation. It accepts local
model path, loopback port and a new identity-output path. Startup identity binds
model assets, bundled source, actual model component source, dtype and runtime.
Start the candidate's own baseline.py directly with the same arguments; do not
modify the frozen prepared directory. collect and assess always use the frozen
reference policy, regardless of which implementation serves the request.

workload.jsonl contains twelve original English/Chinese requests, short/longer
text, punctuation, questions, voices and different seeds. Every concurrency
uses the complete workload. Held-out sets need separately frozen versions.
The reference queue serializes model work; concurrent HTTP requests can wait.

RTF is mean per-request HTTP completion seconds / decoded audio seconds. TTFA
runs from dispatch to the first complete nonempty PCM sample, including server
queueing. Retain audio seconds/cohort wall second, per-request timing, chunk
arrivals, errors, WAV files and PCM hashes. Model verification/loading,
readiness, warmups, scoring and shutdown are outside steady-state speed and
belong in whole-run cost.

An outer Harness owns launch, source/model capture, total deadlines, resources
and cleanup. Each arm needs a fresh process. Qualify baseline A/A first; compare
arms sequentially on the same allocated device with frozen controls and paired
AB/BA repeats. The existing external-command runner may own trial wrappers and
snapshots. Profiling is optional. Markdown never triggers execution by itself.

## Quality and acceptance

Independently score every waveform including warmups: English WER or Chinese
CER using fixed ASR/normalization, and speaker cosine using a fixed verifier
and independent voice anchors. Bind scorer/assets/anchors to an immutable
identity, retain transcripts and per-waveform scores, and freeze quality,
duration, TTFA and speed gates before search. Exact PCM comparison against
official generation is an additional parity diagnostic, not an ASR/voice score.

The assessor verifies retained PCM, payloads, coverage and arithmetic and
compares independent quality scores. Missing evidence or failed gates produce
no usable speedup. Its PASS scope is retained client evidence and supplied
scores. Complete device acceptance also needs loaded source/model identity,
dtype, device, repeatability, lifecycle and scorer execution evidence. A model
smoke run alone cannot qualify quality or campaign performance.

## Deliver

Retain each round's source/configuration patch, hypothesis, materials used,
both arms' audio, independent scoring, raw samples, execution receipts and model
usage. Preserve failed/slower candidates. Select a historically valid candidate
and perform independent final evaluation. Report all concurrencies and whole-run
cost, including cumulative tokens, loading and preparation.
