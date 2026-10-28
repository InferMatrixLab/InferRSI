# Merged FP8 projections: first complete 8K paired search

Issue #67's approved statistics produce **FAIL for both performance metrics**. Campaign status remains **INCONCLUSIVE** because task quality and retrieval are not complete. This is the cumulative candidate versus vLLM 0.32.0, not an isolated estimate of the projection-merge speedup.

Job 2163 completed with scheduler exit0:0 in2244seconds on one H20 (2244GPU-seconds). Six owned service starts generated66valid8192-input/2048-output requests: six discarded warmups and60measurements, yielding30matched pairs. Frozen source/runtime/model/overlay guards, seven actual FP8 operator cases,16same-candidate eager/Graph predictions and final live state, raw SSE accounting, and external terminal binding all passed their scoped checks. No validator or threshold was changed after observation.

| Metric | Baseline median | Candidate median | Median paired ratio | One-sided95% upper | Frozen metric verdict |
| --- | ---: | ---: | ---: | ---: | --- |
| TTFT |1.682033255s|2.860997974s|1.700627224|1.701239281|FAIL|
| TPOT |10.567210277ms|12.188331024ms|1.153776666|1.154741923|FAIL|

Both median and upper bound must be at most1.03. Statistics use10fixed inputs×3pairs and10,000input-cluster bootstrap draws, seed670032, linearquantile. Parent independently recomputed arm medians, paired medians, sample identity and upper bounds from retained rows. The delegated receipt reviewer ran the unchanged frozen binder; no errors were reported. Successful local integration is not model/task quality acceptance. Cross-revision output identity or incremental speedup is not established by this batch.

Baseline startup/shutdown warnings remain retained: cached cubin reload RuntimeError traces, missing precompiled kernels/JIT notices, deprecated entrypoint, generation/chat-template warnings, forced internal EngineCore shutdown and leaked semaphore notices. The six outer owned processes exited0 with zero remaining groups; that does not imply all internal workers shut down gracefully.

Raw archive SHA2567a2774618dee78bf60ba0def9fc8e605d22f80475c4648fe29db3235a076bcb1; bound result SHA256818046ab9571161fb631ff07d17e9ac267c95d1e1f50ce2b741fdb14cac93137. Candidate and baseline revisions are bound in the Issue and result. Raw private runtime paths, model tokens and logs remain outside publication. Follow-up hypotheses are causal FlashAttention prefill and separate BF16 b/a projection merge, each independently scoped and measured. This unsuccessful parity attempt remains retained; no candidate is silently relabeled PASS.
