# Native dispatch, residency, cancellation and prompt-cache contracts

This is original source-derived procedural analysis of **xororz/local-dream**
at `db162df4d9bb6efc6595250423d8df26241f4c27`, not a native execution report.
The upstream [LICENSE](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/LICENSE)
is **CC BY-NC 4.0**. This reference does not copy source code, model assets or
vendor binaries, remove the noncommercial restriction, or establish commercial
compatibility. SDK, dependency and model/artifact rights require separate review.

## 1. Resolve the backend before debugging the symptom

Treat the requested model type, package layout, native consumer and capability
flags as separate evidence fields. File existence is a prerequisite, not a
validated model ABI or a successful device allocation.

| Native type | Selected implementation contract | First discriminating check |
| --- | --- | --- |
| `sd15cpu` | MNN pipeline; CLIP session explicitly CPU, request-selected OpenCL applies through stage options | Distinguish CLIP from UNet/VAE device selection; a CPU-labelled package is not proof that every stage used CPU |
| `sd15npu` | Persistent MNN CPU CLIP plus QNN UNet/VAE; optional UNet patch applied against the base binary | Match patch to base artifact before attributing bring-up failure to the accelerator |
| `sdxl` | QNN UNet/VAE plus dual MNN CLIP; context-length dependent UNet rebuild | Separate fixed-chunk package metadata from patch-extended context and the actual current UNet context |
| `sdxlmnn` | Derived SDXL pipeline; MNN UNet reuse requires matching context length **and** OpenCL selection | A same-model request that changes token context or backend invalidates the live UNet reuse condition |
| `anima` | QNN text encoder and split DiT; separate T5 tokenizer; own text/latent layout | Do not substitute SDXL CLIP/cache/latent assumptions merely because both use the shared outer pipeline |
| `zimage`, `klein`, `qwen21`, `krea2turbo` | Dynamically loaded `libdit_engine.so`; whole generation delegated through its C ABI | Check core/engine ABI and the model-specific diffusion/vision assets before inspecting the shared modular denoising loop |

Inspect [type helpers and defaults](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/cpp/src/main.cpp#L55-L107),
[package dispatch](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/cpp/src/main.cpp#L343-L466),
[SD15 CPU CLIP](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/cpp/src/PipelineSd15Cpu.hpp#L28-L54),
[SD15 NPU initialization](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/cpp/src/PipelineSd15Npu.hpp#L34-L100)
and [SDXL MNN reuse and stage selection](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/cpp/src/PipelineSdxlMnn.hpp#L29-L46)
([stage loader](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/cpp/src/PipelineSdxlMnn.hpp#L123-L150)).
The introductory main.cpp comment says three formats, but the enum/dispatch
contains more; executable branches, not that stale count, own this inventory.

For DiT, `krea2turbo` expects a GGUF diffusion asset while the other listed DiT
families use safetensors. `qwen21` and `krea2turbo` additionally require the vision
LLM file. The engine library must exist, then `dlopen`, entry-symbol resolution,
ABI negotiation and context creation must each succeed. A loaded library alone
is not a created model context. [Initialization](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/cpp/src/PipelineDit.hpp#L49-L98)
also sets a direct-VAE-convolution flag; the source comment relates it to Hexagon
weight layout. That explanatory comment is not independent kernel validation.

The core's tokenizer and optional QNN runtime setup are distinct from the DiT
engine. [Startup](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/cpp/src/main.cpp#L816-L850)
loads the tokenizer before pipeline construction. [QNN initialization](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/cpp/src/main.cpp#L894-L905)
can supply the shared upscaler separately for DiT. Diagnose a QNN-upscale failure
as its own dependency failure; do not infer that successful DiT generation
initialized the core's QNN runtime.

## 2. Establish the serialization and cancellation boundary

[Generation](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/cpp/src/main.cpp#L485-L573)
and [upscaling](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/cpp/src/main.cpp#L599-L765)
share `g_generation_mutex`. The upscale lock is acquired before the MNN/QNN
branch, so the exclusion applies to **both** branches despite the nearby comment
emphasizing QNN. Generation holds the lock through result encoding and complete
event emission, not only the denoising kernel. Upscaling holds it through result
preparation and explicitly resets its temporary QNN model on normal and handled
exception paths before leaving the handler.

Consequences for investigation:

1. Separate waiting for the lock, generation/stage work, encoding and transport
   in a trace. An overlapping HTTP request is not proof of concurrent accelerator
   execution. A queued upscale request is not by itself a deadlock.
2. This is a process-local mutex. It does not coordinate another process or
   establish a device-wide memory budget. Retained contexts may still exist
   outside the currently executing stage.
3. Generation detects disconnect through the progress callback's writability
   check or failed write. A blocked lock acquisition and a long native operation
   without a callback do not acquire an immediate interrupt merely because the
   client disconnected. The completed-result write is not checked in the same
   way as progress writes; server-side completion is not client receipt.
4. Parsing errors return HTTP error responses before streaming; errors thrown
   inside the chunked provider attempt an SSE error. An error event may itself
   be undeliverable after disconnect. Preserve transport outcome separately from
   computation outcome.
5. [DiT callback forwarding](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/cpp/src/PipelineDit.hpp#L385-L428)
   catches the callback exception, stores it, and returns false through the C
   ABI. If the engine call fails, [the caller](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/cpp/src/PipelineDit.hpp#L214-L248)
   rethrows that stored reason rather than replacing it with a generic engine
   error. This establishes the local bridge, not the uninspected engine's exact
   interruption latency or memory-reclamation guarantee.

Cancellation is **not transactional rollback**. A prompt cache may already have
been persisted before the first outer progress callback. Cleanup hooks do not
prove deletion of disk caches, reversal of all engine state, or driver-level
memory reclamation. To qualify restart-after-cancel behavior, a separately
authorized native case must cancel at identified stages, confirm termination,
then run a controlled subsequent request while recording retained state.

## 3. Separate lifecycle mechanisms from memory-fit claims

The shared [generation entry](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/cpp/src/Pipeline.hpp#L915-L955)
installs a scope-exit transient cleanup hook after input validation. SDXL's
[low-RAM release hook](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/cpp/src/PipelineSdxl.hpp#L242-L276)
and [MNN variant](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/cpp/src/PipelineSdxlMnn.hpp#L116-L130)
release selected stage owners. Do not generalize this to every pipeline: the
base hook defaults to no action, and `PipelineDit::generate` bypasses the base
algorithm entirely. Its successful path explicitly calls the safety checker;
that is wiring evidence, not filter effectiveness.

A failed SDXL context transition must not leave a reusable half-initialized
UNet. The [transition code](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/cpp/src/PipelineSdxl.hpp#L192-L215)
releases VAE dependents before the UNet group head, builds the replacement into
a local owner, and assigns the persistent owner only after initialization.
Inspect failure stage and next-request reuse state, not only a success log.

Anima has two different memory strategies, not one boolean promise of fit:

- [Constructor gating](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/cpp/src/PipelineAnima.hpp#L45-L67)
  enables sequential DiT only when low-RAM mode is also enabled.
- In ordinary low-RAM denoising, both halves may coexist and share spill-fill
  storage. [Group construction/release](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/cpp/src/PipelineAnima.hpp#L351-L409)
  creates part 1 as head and destroys the referencing part 2 first.
- [Sequential DiT](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/cpp/src/PipelineAnima.hpp#L301-L322)
  computes/buffers each required CFG branch through part 1, releases it, then
  loads part 2 and consumes the intermediates. This trades parameter residency
  for repeated loading and intermediate storage. An upstream comment's device
  fit statement is not reproduced as a verified capacity here.

Measure actual stage peaks, retained allocations and transition costs under a
frozen device/model/configuration before comparing these strategies. Releasing
a C++ owner is not itself a measured memory reduction, and lower residency is
not automatically better end-to-end latency.

## 4. Audit prompt caching by identity, layout and caller eligibility

[PromptCache.hpp](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/cpp/src/PromptCache.hpp#L11-L105)
uses a prompt-derived filename beneath a supplied cache directory. Its header
checks magic, format version, mode, sequence length, hidden dimension and pooled
dimension, then reads the expected float payload. Missing, truncated or
header-incompatible entries become misses. These checks establish a narrow
layout contract, not semantic authenticity or full artifact integrity.

The actual [caller](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/cpp/src/Pipeline.hpp#L403-L483)
computes context length jointly from positive/negative prompts, sizes buffers,
checks each side independently, and bypasses a side whose prompt resolves a
textual-inversion embedding. It selects different modes for SD15, Anima,
patch-extended SDXL and fixed-chunk SDXL. A same positive prompt paired with a
longer negative prompt can therefore miss because the required layout changed;
that is not evidence of a broken hash. Two hits skip the encoder call; one hit
only avoids that side's encoding, not the whole generation.

Use these negative rules when diagnosing a suspicious hit:

- Model directory separation is contextual isolation, **not** a model-revision
  digest. Neither the filename key nor header includes tokenizer, encoder weight
  or embedding-table content identity. Replacing such files in place with a
  shape-compatible version cannot be declared safe from these checks alone.
  Require an explicit invalidation/versioned-directory strategy and a native
  cold-versus-warm equivalence case before reuse.
- The helper itself does not check textual inversion; eligibility is the
  caller's responsibility. Do not invoke a header-only cache test and claim that
  embedding-dependent caching is prevented throughout the engine.
- Separate mode prevents a false layout hit, but not filename collision at the
  storage-path level: modes use the same prompt-derived path and the header
  determines hit/miss. Changing mode can replace an earlier mode's entry.
- Payload reads detect short data, not a tensor checksum or numerical validity.
  Saving directly truncates/writes the target file; this header does not provide
  an atomic publication protocol or interprocess lock.
- The DiT override does not use this base prompt-encoding path. No conclusion
  about its internal text cache follows from `PromptCache.hpp`.

Keep prompt-cache behavior separate from OpenCL tuning caches, VAE latent caches
and model residency. Each has a different key and invalidation domain. Use
synthetic prompts and sanitized identities; native request logging includes
prompt text and is not safe to publish without review.

## 5. Smallest missing evidence and explicit omissions

| Proposed discriminator, not an executed test | Required observation | What a passing result would still not prove |
| --- | --- | --- |
| Header mismatch, truncated entry and one-sided hit/miss cases | Correct fallback and only eligible side reuse | Model-change invalidation, semantic tensor equality or DiT cache behavior |
| Change SDXL context/backend, then fail and retry initialization | Replacement owner published only after valid initialization; no invalid reuse | All QNN/MNN failure recovery or device-wide memory safety |
| Queue generation and upscale; disconnect at a known progress point | Lock ownership, callback/cancel sequence, explicit cleanup and subsequent request outcome | Immediate cancellation, fairness, multiprocess arbitration or transactional rollback |
| Compare Anima ordinary low-RAM and sequential mode | Actual loaded owners, intermediate lifetime, device peaks and timing | A universal device-fit or speedup claim |

These are proposed source-informed native cases, not named upstream test passes.
The inspected host `ExampleUnitTest` is an arithmetic smoke test, not evidence
for any of these contracts. No native C++ contract test was executed or claimed.

Readset: selected `main.cpp` spans 36–107, 343–597, 599–613, 635–765, 805–850, 894–937;
`PromptCache.hpp` 1–110; `Pipeline.hpp` 280–315, 403–483, 915–965;
`PipelineDit.hpp` 20–100, 205–260, 275–330, 350–465;
`PipelineSd15Cpu.hpp` 1–60, 135–180, 230–267;
`PipelineSd15Npu.hpp` 1–100; `PipelineSdxl.hpp` 185–215, 235–285;
`PipelineSdxlMnn.hpp` 1–65, 110–162; `PipelineAnima.hpp` 1–85,
170–185, 235–420; native `CMakeLists.txt` 1–95; `.gitmodules`;
`app/src/test/java/io/github/xororz/localdream/ExampleUnitTest.kt` 1–16;
and the upstream license identification. Line inspection is not exhaustive
analysis of unlisted functions in those files.

The native [build declaration](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/cpp/CMakeLists.txt#L7-L36)
copies/patches QNN sample support and packages SDK libraries/notices; it was read,
not run. Dependency gitlinks, vendor SDK internals, `DitEngine.cpp`, the actual
stable-diffusion.cpp fork body, RequestParser image/mask transforms, schedulers,
quantization, mathematical parity, security hardening and full memory ownership
are outside this reference's inspected depth. The stable-diffusion.cpp gitlink
identifies `a63954dc794f6daade32c407da1a9c4bc2d73cf0`; that identifies a dependency,
not an inspected or tested dependency implementation. No build, model loading,
Android/Qualcomm execution, quality, memory-fit or performance result exists in
this reference. Empirical state remains `not_run`; qualification is
**INCONCLUSIVE**.
