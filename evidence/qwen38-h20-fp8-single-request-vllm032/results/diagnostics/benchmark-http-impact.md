# Benchmark HTTP accounting: bounded impact

Refs InferRSI Issue #67. Campaign verdict **INCONCLUSIVE**.

Engine PR8 is merged as1ce49a19a72351668cdbb9d48996796f5ac2efb3. Its tree exactly
matches tested23417bbf13548127fdd0b49dbb26e495a38d9af6. Local and remote related
suites each passed72 tests. The installed official vLLM0.32.0 client was verified
byte-for-byte; old API rejected both synthetic probes, repaired API reported
correct natural-EOS/ignore-EOS token usage and token timing intervals.

Actual model HTTP job1951 completed three Graph requests with529/169/314 tokens,
then failed after876 tokens at the1024-capacity boundary. Eager never ran.
Results graph-long-1951.jsonl retain every observed token and ITL; the summary
records partial coverage and226 GPU-seconds. This does not establish paired E2E
speedup. Neither these timings nor the official client's false success flag
can establish acceptance. Strict usage/terminal/length checks rejected failure.

Independent review verified unchanged runner/model/graph/engine runtime hashes
and identified inherited hybrid demotion behavior; HTTP correctly exposed the
error. PR8 enables benchmark compatibility/accounting, not performance parity.

CPU attempt1947 failed due a fixture dependency crossing into the pristine
client environment; version2 isolated it and1950 passed. Later1952/1953 exposed
a preexisting readiness-file test race; separate test-only PR10 merged as
7ec5d224e983e437530355b94b0d6d08153bc27d after72 remote CPU tests and independent
review. No checks were removed or deadlines increased. See both ledgers.

KnowledgeStore candidates (verified readback, not library promotion):
- store:case.qwen38-official-http-accounting-cand at
  sha256:2863b8b4c714ae8423c83178a2ddf4ff0160ecd67c5be41e0a66a942cf9d8125.
- store:case.qwen38-hybrid-graph-demotion-cand at
  sha256:e39d8104adffd937f8e71f33465cd8afac6e66d714faf65381b77147652137d9.

The latter retains model diagnosis and negative preflight attempts. Their GPU
retry remains pending in this snapshot. Readiness use before retry is375
GPU-seconds; separate initial147 seconds remain separately accounted.
