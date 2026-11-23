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
CPU handoff tests cover those properties. This is not full upstream duplex
parity: in particular, upstream's early speech-tail flushing for a fully muted
mid-turn unit and the external asynchronous delegation runtime need additional
end-to-end validation.

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

Use [vLLM-Omni PR #10976](https://github.com/vllm-project/vllm-omni/pull/10976)
and the pinned revisions linked from the acceptance issue.
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
