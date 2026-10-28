# Source scope, candidates and excluded scripts

Source: [zuiho-kai/h3-metal](https://github.com/zuiho-kai/h3-metal/tree/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8)
at `4ba47a3eabdbebf801ac6664b31f8ec168bc57a8`, inspected 2026-10-28. The
[identity record](source-identity.json) preserves whole-file Git blobs, SHA-256,
sizes and selected inspected ranges. Hash identity is not exhaustive semantic
inspection. The [provenance note](repo-provenance.md) distinguishes source,
method, license resolution and missing execution.

## Bounded readset

| Files / selected surface | Extraction / boundary |
| --- | --- |
| `h3.c`, `h3.h`, `main.c` | FastH3 normalization, component-path choice, reference exclusion, temporal/result fields and selected CLI parsing; not the complete generation/cache/media pipeline |
| `h3_dit.c` | Loader transformations, valid packed-layout assumptions, ambient token controls, generated RoPE, VSA tile/top-k setup and selected dispatch/FC2/reuse gates; not complete DiT numerical verification |
| `h3_dit_schedule.c`, `h3_host.c`, `h3_host.h` | Separate FastH3 modality sigmas, schedule detection/BF16 timestep/AdaLN path, frame/latent arithmetic; remaining host processing not mined |
| `h3_gpu.m`, `h3_shaders.metal` | Selected compile/pipeline predicates, coarse pooling/masks/ties and fine-tail masking; not full kernel/device/MPSGraph audit |
| `tests/test_h3.c`, `tests/test_vsa_coarse.c`, `tests/test_real_dit_schedule.c`, `tests/bench_dit.c`, `Makefile` | Candidate definitions, build/fixture dependencies and important noncoverage; no native test execution |
| `README.md`, `docs/USAGE.md`, `bench/run_fox2.sh` | Public workflow/timing intent versus actual two-prompt script; benchmark claims not reproduced or imported as local evidence |
| `tools/fasth3_keymap.py`, `tools/fasth3_keymap.md` | Schema-analysis code versus checked-in report; unsafe execution excluded |
| `LICENSE`, `THIRD_PARTY_NOTICES.md` | MIT source and separate BSD-3-Clause shader-derived attribution retained; weights independent |

Implementation comments cite FastVideo paths/commits and unpublished notes.
Those are **h3-metal source comments**, not independently inspected FastVideo
conformance, accessible private notes or numerical correctness evidence.

## Native candidates and script dispositions

All required Apple/Metal/model execution remains **BLOCKED_REQUIRED_BACKEND /
not_run** for this source/CPU supplement. No backend mock or helper substitutes
for actual execution. Test names/assertions are evidence candidates, not receipts.

| Candidate | What its source actually exercises | Resources / limitation |
| --- | --- | --- |
| `make test` | Native scaffold and selected conditional fixture/model tests | Apple frameworks/Metal; per-test fixtures/model/tokenizer/FFmpeg. Conditional skips are not passes; not all standalone tests are in this target |
| `h3_vsa_tests` / `tests/test_vsa_coarse.c` | Coarse add-on with four row/head-major combinations; near-real rows with contiguous 64-row tiles and a short tail | Real Metal even without released weights. Does **not** invoke sparse fine/top-k or validate actual 3D tile-builder membership |
| `h3_real_dit_schedule_test` / `tests/test_real_dit_schedule.c` | FL2VA original 20-step AdaLN, row layout and fixture comparison | Metal + FL2VA weights + fixture; **not** FastH3 BF16 schedule coverage |
| `h3_dit_bench` / `tests/bench_dit.c` selected setup | Original FL2VA/Ref2VA paths, original/serving 20-step scheduling and AB hooks | Metal + model/fixture; not a FastH3-specific check or service/media-quality result |
| `tests/test_vae_bf16_rand.c`, `tests/test_vae_bf16_real.c` | Located standalone BF16 VAE candidates | Bodies not mined in this supplement, not default Makefile targets, actual Metal required; outside selected semantic workflow |
| `bench/run_fox2.sh` | Exactly two same-process prompts, profile enabled, environment and flags, writes output/log and records rc | **Excluded**, not copied: model/backend execution and output mutation. Two clips alone do not establish README clips2–4 means or ABBA summaries; final grep is not an acceptance validator |
| `tools/fasth3_keymap.py` | Local or curl-fetched JSON headers and shape/name comparisons, writes report | **Excluded**, not copied or executed: mutable remote `resolve/main`, network/report side effects, no validated Range/Content-Range/body-size guarantee |
| Bundled `audit_fasth3.py` | Selected declaration rules, real edge-count arithmetic and fixed label counterexamples | Safe stdlib CPU support, not copied native code, no inference or conversion; see [contract](preflight.md) |

Native targets and conditional behavior are visible in the pinned
[Makefile](https://github.com/zuiho-kai/h3-metal/blob/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8/Makefile),
[coarse test](https://github.com/zuiho-kai/h3-metal/blob/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8/tests/test_vsa_coarse.c#L225-L316),
[original schedule test](https://github.com/zuiho-kai/h3-metal/blob/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8/tests/test_real_dit_schedule.c#L30-L155),
and [benchmark setup](https://github.com/zuiho-kai/h3-metal/blob/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8/tests/bench_dit.c#L1534-L1654).
[`h3_host.c` imports Accelerate](https://github.com/zuiho-kai/h3-metal/blob/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8/h3_host.c#L1-L10);
do not call it a portable native CPU fallback or compile through fake stubs.

## Key-map report versus code

The checked-in [report](https://github.com/zuiho-kai/h3-metal/blob/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8/tools/fasth3_keymap.md)
says repeated-layer schemas were inferred when requests were unavailable. In
the current [script](https://github.com/zuiho-kai/h3-metal/blob/4ba47a3eabdbebf801ac6664b31f8ec168bc57a8/tools/fasth3_keymap.py#L43-L191),
failed remote reads insert names with empty dictionaries; the later inference
loop skips names already present, and shape comparisons skip empty shapes.
Do not assert that its fallback actually completes every missing schema. The
script's generated label mentions dtype mismatches, but its comparison branches
check shapes, not dtype equality. No absence-of-mismatch count proves payload
integrity, semantic row order, dtype equivalence or executable conversion.

## Measurement context, not duplicated evidence

InferRSI's existing Apple playbook and h3-metal lessons retain measurement
design and historical reports. This supplement does not alter those documents,
relabel their provenance or repeat their timing tables. Public README reports,
author-maintained run records and unverified statements must remain distinct;
neither a bundled-reader test nor this source audit upgrades them. New numerical,
quality, fit or performance claims require separately authorized frozen evidence.
