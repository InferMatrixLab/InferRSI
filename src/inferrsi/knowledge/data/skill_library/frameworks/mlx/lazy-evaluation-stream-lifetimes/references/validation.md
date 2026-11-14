# Validation choices

This candidate has no runtime or performance qualification. Native tests below are source evidence and later verification candidates, not a runtime dependency on the upstream checkout.

1. Identify the installed build and actual CPU/Metal/CUDA backend. A source archive and a package import are different checks. Use only an authorized existing environment; do not install broad extras to make a diagnosis appear complete.
2. For CPU evaluation semantics, select the native assertions behind `TestEval.test_eval`, `test_async_eval_into_eval` and `test_async_eval_into_eval_diff_stream`. The native harness accepts `DEVICE=cpu`. Inspect the selected tests and dependencies before execution.
3. For Metal or CUDA buffer lifetime, repeat the real producer/consumer stream topology, perform the explicit completion/read boundary, and retain numerical checks after dropping graph references. CPU values alone cannot validate a device completion callback or CUDA temporary lifetime.
4. For a suspected error path, preserve the original exception and test a separate known-good computation after it. For memory claims, synchronize the relevant stream and separate active storage from allocator cache.
5. For timing, state whether compilation/warmup, graph construction, execution and host reads are included. Compare identical inputs/dtypes/streams after confirming actual dispatch. No speedup threshold is supplied by this skill.

Report exact passed/failed/not-run scopes. Stop when the question is answered; framework correctness does not establish end-to-end model or service performance.
