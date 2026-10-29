# Qualification troubleshooting

| Observation | Diagnose before changing anything | Safe disposition |
| --- | --- | --- |
| Final kernel-prepared log but no Metal device | The model warmup can return success when the retained Metal device set is empty; a log from another process is not this request's evidence. | Record actual mapped devices and process identity. Do not qualify GPU execution. |
| First request compiles despite model prewarm | Compare actual dtype/cache layout/layer geometry and request constants. Model prewarm has causal/no-ranges/no-right-window/no-chunk limits; supported requests can require additional specializations. | Retain the extra compilation event and exact request. Do not call it proof of an engine correctness regression without tracing the failed contract. |
| New `Kernels` instance appears cold | Libraries/pipelines are process-wide caches keyed by device and pipeline identity. | Use a separately authorized fresh process for cold measurements; record artifact and driver state too. Do not flush global state or change caches casually. |
| Nonempty embedded metallib fails to load | The inspected loader reports compilation error; runtime source compilation is used only when embedded bytes are empty. | Preserve build/SDK/device compatibility and exact error. Do not claim an automatic runtime fallback or silently substitute different artifacts. |
| Warmup boundary inventory has 119 pairs | That count is for the example maxima and static source boundaries only. It omits selector/model/features and executes no GPU. | Report `source_boundary_inventory_only`; keep native verification `not_run`. |
| `cargo check --features metal` is green | Check verifies compilation, not executed Metal numerical/cache assertions. Test feature/cfg/filter can also leave zero tests. | Inspect test listing, native device creation and nonzero executed counts. Preserve `BLOCKED_REQUIRED_BACKEND` when unavailable. |
| Host reference matches expected math | The native source tests call Metal attention before comparing against the reference. Running only the host formula omits that path. | Treat reference checks as reference checks, not CPU substitutes for Metal dispatch. |
| Output parity passes but reused cache corrupts | Inspect actual allocation aliasing, start offsets, guard blocks, copy/swap source preservation, cropped/donor state and continuation. Source copy tests explicitly use independent backing storage. | Add scoped native state evidence; one numeric output is insufficient. Route cache layout semantics to the sibling contract. |
| Native tensor tests pass, proposed serving speedup remains | Primitive assertions do not measure loaded-model quality, scheduling, token accounting, HTTP service or user-visible latency. | Freeze and execute a separate acceptance plan. Publish no speed/quality claim from these tests alone. |
| Helper rejects input | Check the exact schema, positive integer maxima, duplicate/unknown keys and 16 KiB limit. A JSON boolean is not an integer here. | Correct the plan; do not relax validation to accept opaque data. No raw input is echoed in diagnostics. |

Return the observation, exact scope and missing evidence separately. Do not
replace absent native evidence with a synthetic pass or hide a skipped/error
case behind a successful helper result.
