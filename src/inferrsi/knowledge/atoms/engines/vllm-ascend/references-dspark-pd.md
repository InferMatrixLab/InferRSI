# Reconcile DeepSeek-V4-Flash DSpark across prefill and decode

1. Identify the checkpoint's draft config and the requested method on both roles. The 950DT tutorial selects `dspark`, with matching speculative token counts on P and D and at least five, subject to the checkpoint. Its MTP example has a different P/D rule. Earlier A2/A3 examples in the same file describe other versions. Use the RC release table for qualification.
2. Compare each engine's actual DP/TP sizes with the connector's `prefill` and `decode` sections. The two-server example uses P DP1/TP8 with DSA-CP, D DP8/TP1. The tutorial advises pairing TP with DSA-CP on 950DT. Record the connector and both layouts even if each engine starts in isolation. For the KV Pool path, also verify hybrid KV manager enablement and the communication-resource mount. A startup OOM and a failure on the first transfer require different traces.
3. Separate proposer and target graph mode. The V1 `AscendDSparkProposer` disables draft graph execution, sizes draft hidden-state buffers from the draft model, and selects query width from `sample_from_anchor` (N or N+1). The documented target decode capture example budgets 1+N tokens per sequence. At N=5 a 360-token tier corresponds to roughly 60 sequences per step. Observe actual scheduled requests and graph descriptors before citing achieved concurrency.
4. In a compatible four-card test environment, isolate the source regression case:

   ```bash
   pytest -q tests/e2e/pull_request/four_card/spec_decode/test_dspark_deepseekv4.py -k dsa-cp-dspark
   ```

   This case uses the test checkpoint, TP4, DSA-CP, seven speculative tokens and eager draft with target FULL_DECODE_ONLY. The shared helper generates greedily and computes 1 + accepted tokens / drafts (fallback 1 when zero drafts). Report the two raw counters. Its oracle is relative acceptance-length error. It does not compare generated text to a reference, exercise two-node transfer or qualify W4A8C8 service performance.
5. For a PD-only failure, replay one fixed prompt through the proxy and correlate both roles' request, transfer and decode events. For a performance question, hold checkpoint, shape, pool mode, cache-hit rate and load fixed; separate pure prefill, pure decode and end-to-end measurements. Report the first diverging boundary and any unobserved quality, transfer or serving result.

See the [tutorial, proposer and test helper](sources.md).
