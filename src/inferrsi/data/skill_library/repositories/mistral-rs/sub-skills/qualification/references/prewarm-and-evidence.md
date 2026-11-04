# Prewarm coverage and native evidence

This procedure is grounded in the pinned mistral.rs source linked below.
Treat its constants as implementation facts at that revision, not hardware
identities, portable tuning rules or empirical acceptance gates.

## Follow the loaded model, not a generic warmup

[`prepare_model`](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/mistralrs-core/src/pipeline/metal_warmup.rs#L16-L121)
collects mapped devices plus the primary device, retains Metal devices, and
returns successfully if none remain. It calls common-kernel preparation and
each tracked module's resolved `prepare_metal_kernels(actual_dtype)` before
paged attention. Those calls must not be assumed to have the same inner
behavior as the paged preparation inspected here.

Paged preparation is conditional on paged configuration. For each eligible
layer it derives query/KV head counts, separate key/value dimensions, mapped
device, actual query/cache dtype, chosen HND/packed-cache layout and block size.
It takes sequence/batched-token limits from execution configuration and context
length from the model. Maximum prefill query length is the minimum of the
prefill chunk limit, batched-token limit and model context limit. It skips
nonpaged/MLA/non-Metal layers and unsupported shapes. Packed-query variants are
included only if packed prefill was enabled.

The prepared specification is causal, with zero multimodal ranges, no right
window and no attention chunk size. Sliding window is per layer; ALiBi uses F32
when present, sink features are prepared with F32 and the actual query dtype,
and softcap presence is retained. A `(device.location(), specification)` key
deduplicates work across layers. Thus a success log does not prove that every
request specialization was prepared, much less executed correctly.

## Preparation loads pipelines; actual dispatch is separate

[`prepare_metal_paged_attention`](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/mistralrs-paged-attn/src/metal/backend/paged_prefill.rs#L244-L273)
checks shape support, constructs parameters, loads prefill pipelines for query
length 1 and the configured maximum with function constants, loads the metadata
copy pipeline, then delegates decode preparation. These are pipeline loads,
not invocation of the actual prefill request.

[`prepare_decode_kernels`](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/mistralrs-paged-attn/src/metal/backend/paged_attention.rs#L16-L134)
prepares cache reshape/gather/copy and, for FP8, scaling pipelines. Unequal
key/value dimensions or unsupported decode head sizes return after those
auxiliary preparations. For supported decode dimensions it enumerates warmup
shapes and loads selected specialized or generic attention/reduction pipelines.
This is not an all-shape numerical test.

The [library and pipeline caches](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/mistralrs-paged-attn/src/metal/kernels/mod.rs#L1-L185)
are process-wide `OnceLock` maps. Library identity includes device registry ID;
pipeline identity includes registry ID, function name and function constants.
Creating a fresh `Kernels` value does not make a cold process. Embedded metallib
bytes are used when nonempty; failure to load those bytes returns an error.
Runtime source compilation is selected when embedded bytes are empty, **not**
as a silent fallback after a nonempty embedded library fails to load.

The [decode dispatch implementation](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/mistralrs-paged-attn/src/metal/kernels/mod.rs#L1287-L1406)
loads the selected native pipeline and issues threadgroups, with separate
reduction where needed. Selection metadata or a prepared pipeline name does
not prove that a request reached that dispatch or used the intended buffers.
Capture or instrument an authorized native run if that distinction matters;
this skill does not establish a public telemetry getter.

## What the boundary source test actually proves

The [enumeration and warmup coverage test](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/mistralrs-paged-attn/src/metal/kernels/mod.rs#L1238-L1465)
build a finite boundary set and check that selected pipeline names for several
head/window configurations are present in that prepared-name set. This is a
useful regression for pipeline-family coverage. It is not exhaustive coverage
of request features, per-request runtime telemetry or GPU output parity. The
bundled helper reproduces only the boundary enumeration, not this selector test.

## Native evidence candidates and required boundaries

All candidates below require the actual Metal backend, with **no full CPU
substitute**. On a host without Apple Metal/toolchain support their result is
`BLOCKED_REQUIRED_BACKEND`, not a passing reference check. Original test fixtures
are not bundled with this portable skill; source-checkout execution plans belong
in the separate native-candidate report, not this runtime procedure. The fixture
tensors in these selected tests do not require model weights, but that does not
make compilation or GPU resource cost preauthorized or negligible. Valid native
evidence requires a separately authorized, prepared Apple Metal stack, approved
dependency artifacts, finite resource limits, exact executed test identities,
nonzero counts, skips and exit status. A broad workspace/model suite is not an
equivalent bounded check.

| Candidate | Evidence asserted by the original source | Remaining boundary |
| --- | --- | --- |
| `metal_prefill_matches_reference_across_geometry_and_layouts` in `mistralrs-paged-attn/tests/metal_prefill.rs` | Creates Metal device 0; compares real prefill output with a host f64 reference across dtypes, unequal dimensions and HND/packed-cache layouts. Checks finite, scale-normalized errors with test-local tolerances. Its queries use the default unpacked form. | Test geometry is not every model/request; no service timing. |
| `metal_prefill_preserves_metadata_across_inline_and_buffered_batches` in that file | Exercises metadata batches 56 and 57 across inline/buffered boundary. | Source arithmetic or a skipped test does not establish native metadata transfer. |
| `metal_prefill_preserves_windows_with_historical_multimodal_ranges` and `metal_prefill_accepts_noncausal_and_custom_attention` in that file | Exercises request features absent from the inspected model-prewarm specification, including positions/ranges, noncausal/custom masking, right windows and chunking. | Their existence does not mean the model prewarmed every specialization. |
| `metal_hnd_decode_matches_cpu_with_ragged_pages_and_features` in `mistralrs-core/src/paged_attention/metal_hnd_tests.rs` | Creates Metal device 0, runs paged attention and compares returned values with the host reference across BF16/F16/F32 and ragged/window/feature cases. | Reference math alone is not this GPU execution; preserve actual selected route. |
| `metal_hnd_fp8_cache_matches_cpu` in that file | Executes with FP8 cache scales and compares output to the reference. | Quantized cache representation and output tolerances are distinct checks. |
| `metal_hnd_block_copies_preserve_offsets_and_other_blocks` in that file | Tests real Metal copy/swap on narrowed storage, exact copied K/V, guard blocks and unchanged source, including CPU-to-Metal source. | Copy correctness alone does not prove continuation output or concurrency safety. |
| `metal_native_prefill_wrapper_matches_cpu_and_preserves_cache` in that file | Covers cold/reused/cropped/donor combinations and several masks; checks outputs and gathered K/V against host values. | Still primitive/wrapper evidence, not loaded-model or HTTP-service acceptance. |

Source assertions: [prefill construction and reference](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/mistralrs-paged-attn/tests/metal_prefill.rs#L398-L737),
[decode/reference and donor cases](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/mistralrs-core/src/paged_attention/metal_hnd_tests.rs#L552-L760),
[copy guard assertions](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/mistralrs-core/src/paged_attention/metal_hnd_tests.rs#L924-L1009),
and [wrapper cache assertions](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/mistralrs-core/src/paged_attention/metal_hnd_tests.rs#L1338-L1399).

An evidence record needs the exact filter and test listing for its prepared
build; zero matching tests is not a pass. The prefill integration file is gated
by both `feature = "metal"` and `target_os = "macos"`; the core module is gated
by `test` and `feature = "metal"`. The source
[CI configuration](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/.github/workflows/ci.yml#L37-L71)
has a macOS `cargo check --workspace --features metal` job, but the displayed
test-suite command has no Metal feature flag and excludes the paged-attn
integration package. Do not cite its compile job as these native assertions.

## Evidence handoff

Retain identity/config, allowed commands, actual test counts, skips, exit codes,
native device/route evidence and numerical/cache observations. Use the source's
test-local assertions for that source test; any new model/service gate must be
frozen in the acceptance plan before candidate search. Keep compiler/prewarm
time, first request, steady state and client-observed service metrics separate.
Actual model/tokenizer outputs and quality evaluation remain independent of
these tensor tests. Absent native evidence is unresolved, even if every
offline inventory and documentation check passes.
