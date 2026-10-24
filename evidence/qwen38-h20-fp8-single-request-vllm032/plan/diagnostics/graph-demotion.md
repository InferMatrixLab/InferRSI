# Hybrid Graph demotion readiness

Authority and prospective limits: InferRSI Issue #67 comments6346532120,
6346586062 and6346638737. This is not an acceptance freeze or performance search.

Model-plane candidate80e5108e44c43f3f54fabb5723e6154d18088516 on test-only
base7ec5d224e983e437530355b94b0d6d08153bc27d. Its model patch and all runtime
bytes equal reviewed e69035df55d7fd956a7a2529c75a402164cdf1ed; the sole rebase
delta is the independently reviewed readiness test. Only full-attention KV
is compacted; linear conv/recurrent history remains available to eager decode.

After CPU regressions reproduce the old exception, verify the same original
four requests per Graph/eager arm from benchmark-http.md, plus a final16-token
ignore-EOS request for case783 after demotion. Total10 requests; same allocated
GPU, official FP8 weights, exact pinned client, context4096 and concurrency1.
Preserve every output difference. No candidate selection or reduced replacement
work. Observer v2 is separate; original observer and failed1951 remain frozen.

One GPU maximum30minutes, within approved readiness2 GPU-hours and overall44.
Startup180seconds/service, request300seconds, command1720seconds; owned-process
cleanup20seconds then bounded kill. Readiness before retry uses375 GPU seconds;
initial separate allowance147 seconds is not charged again.

1952 failed at CPU preflight before model execution (73passed/1failed,5 GPU
seconds). CPU-only1953 repeated the same existing ready-file race. Separate
harness test repair94eed335c365fccc39289551837818e333758263 waits for complete JSON
within unchanged3 seconds;72 remote CPU tests passed in1954, then merged7ec5d22.
Combined source74 local tests pass. Runtime and GPU diagnostic definitions were
not changed by the test correction.
