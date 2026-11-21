# Scheduling RSI lessons: Ascend queue ordering and agent KV eviction

This is an unverified exploration record. The two campaigns below have no
acceptance issue, their measurements are in the maintainers' unpublished
campaign ledger, Campaign 1 is a simulation that was not run on NPU hardware,
and nothing here is an InferRSI PASS. The page therefore publishes no
capacity, latency, hit-rate or speedup figures; it keeps only the method and
the failure modes.

This page records two earlier campaigns of the same RSI line (model proposes a
policy → a frozen scorer measures it → keep the better, drop the worse) so that
later campaigns inherit the measurement rules and the failure modes, not only
the headline. Apple-silicon lessons from later work are in the
[Apple silicon playbook](apple-silicon-playbook.md) and
[Inkling 2 Mini on Apple silicon](inkling2-mini-apple-silicon.md).

## Sources and labels

| Label | Meaning |
| --- | --- |
| **public** | In a public repository or dataset at the link given in the row. |
| **ledger** | From the maintainers' unpublished campaign report or run log; not reproducible from this page; unverified. |
| **inferred** | Analysis made during the work and not measured. |

## Campaign 1: vLLM-Ascend waiting-queue order (simulation)

Setup (ledger): real vLLM engine with only the device operators replaced by
stand-ins; a virtual clock calibrated from another team's operator timing
table (step time as a linear function of tokens in the step); multi-turn
sessions in which almost every request contains the whole previous request.
Several candidates ran in parallel until the CPU saturated. Simulator wall time
was never used as the metric.

| Observation | Cause | Action | Source |
| --- | --- | --- | --- |
| Ordering by the *share* of the prompt already cached, highest first, ranked above ordering by *absolute* tokens saved (either direction). | Share favours requests whose remaining prefill is small relative to what is already resident, so cache pages are reused before eviction. | Try the normalised form of a key as well as the absolute one. | ledger |
| The capacity at which the *mean* TTFT meets the bound was clearly higher than the capacity at which *every* run stays under it. | Mean-at-bound and every-run-under-bound are different operating points. | Publish the conservative point next to any headline and name which one is quoted. | ledger |
| At the same mean TTFT, median TTFT and the shortest prompts' TTFT got worse while the longest-to-mean ratio fell. | The policy equalises latency: long prompts gain, short cold prompts wait. | Report latency by prompt-length band, not only capacity. State the precondition: prefill-dominated load and no hard sub-second SLO for short requests. | ledger |
| Several successive "guaranteed floor" values were each inside the run-to-run noise and were all withdrawn. | Single-seed differences below the noise are not results. | Below 5% difference: no conclusion. A "better" verdict also needs a mechanism signal (hit rate up, recompute down, queue shorter). | ledger |
| Split validation (sessions halved into an evolution half and an exam half) gave similar results on both halves, but under a larger cache pool than the headline run. | Checks the policy is not fitted to the sessions it was found on. | Always hold out sessions, and never combine figures measured under different cache pools. | ledger |
| Parameter-level search improved for a few generations and then stopped moving; a late round produced almost only duplicates of known candidates. | The parameter plane was exhausted; the proposer kept regenerating known candidates. | De-duplicate before scoring. When a plane stops moving, switch planes rather than spend generations. | ledger |
| In the first structure-level round only gate tuning helped; later structural ideas (placing by free slots, a starvation quota for the longest waiter, reserving slots, ordering by waiting time) varied widely. | Structural changes reach gains the parameter plane cannot. | Expect most first-round structural ideas to fail; keep the failures in the trial index. | ledger |
| The champion came from a human-written requirement route, not from the automatic mutation chain. | — | Attribute candidates to their actual origin; write "measured on the same scorer", not "found by the model", unless the chain produced it. | ledger |
| Most human effort went into making candidates run on both the NPU path and the simulator (interfaces, parameter adaptation, debugging). | Two execution targets. | Budget the adaptation work explicitly; it is the cost driver, not proposal generation. | ledger |
| At the highest load, ordering alone came close to perfect reuse, and cold short requests remained slower. | The ordering plane is close to its ceiling. | Next plane: cache residency and admission. | ledger, inferred |

Not established: NPU hardware confirmation of the simulated ranking; paired
per-session statistics instead of the 5% rule; a separate held-out audit split
for the champion.

## Campaign 2: agent-aware KV eviction (CPU replay)

Setup: CPU replay of public agent traces, policy proposed by a model, scored by
hit rate. Code was contributed to
[JiusiServe/vllm-evolve#1](https://github.com/JiusiServe/vllm-evolve/pull/1)
(public). Primary trace: Weka cc-traces with sub-agents
([HF dataset](https://huggingface.co/datasets/semianalysisai/cc-traces-weka-with-subagents-051926), public);
219 traces.

| Observation | Cause | Action | Source |
| --- | --- | --- | --- |
| Trace chains are idle most of the time; sub-agents return sooner than root agents. | Tool calls and model turns alternate. | Expected return time is a usable eviction feature; sub-agent KV should stay resident before root-agent KV. | ledger, inferred |
| With device memory small relative to the active working set, LRU left a large gap to the offline upper bound, and the gap came from eviction order, not prefetch; with more memory the gap shrank. | The headroom comes from eviction order by expected return, not from prefetch. | Agent-aware eviction is worth searching only when memory is tight; measure the gap to Belady before searching. | ledger |
| After pinning the blocks of running requests, the gap between LRU and Belady almost disappeared; without pinning it looked large. | The unpinned replay credited evictions a real engine cannot make. | Model engine constraints (pinning, admission queueing) in the scorer before quoting headroom. | ledger |
| An exploratory search after pinning moved mean hit rate only inside the noise. | Small remaining headroom after pinning. | Compute the reachable headroom first; do not spend search budget on a plane with almost nothing to gain. | ledger |
| On a real vLLM 0.20 engine with Qwen2.5-7B, the evolved eviction function loaded through `--scheduler-cls`, evicted by score, and kept outputs identical under batch-invariant mode. | — | The hardware test proves the plug-in runs and keeps outputs; it does not score the policy. Gains come from the RSI scorer only. | ledger |
| Locally collected agent sessions were rejected as a dataset. | They have no external standing. | Use public traces already used by papers or benchmarks (Weka cc-traces, FreeInference, TraceLab). | ledger |

## Campaign gates inherited from both

These are the pre-run checks the maintainers now apply before any search
(ledger, from a closed research campaign that spent most of its time on its
harness):

1. **Mechanism first.** Write the hypothesis as "variant X beats Y because part
   P makes them differ", and name P in code. No P, no run.
2. **Power before running.** Baseline rate, samples per arm and the smallest
   difference that would be visible against the measured run-to-run noise.
3. **Harness time box.** Harness and framework acceptance together at most one
   working day or one quarter of the budget.
4. **Smallest discriminating run first.** Two arms, one seed. A tie sends the
   work back to step 1, not to more seeds.
5. **Daily split.** Record how much of the day went to the hypothesis and how
   much to the harness.
6. **Kernel gain is not end-to-end gain.** In a sibling InferMatrixLab engine
   a kernel that was clearly faster in isolation barely moved end-to-end time
   (public, `InferMatrixLab/system1-omni`). Score candidates on the full
   generation path only.
7. **Freeze the rival.** Thresholds written before the run, rival
   configuration frozen, inputs byte-identical, failed candidates kept.
