# Scheduling RSI lessons: Ascend queue ordering and agent KV eviction

**An LLM-proposed waiting-queue order (prefix-cache hit share of the prompt,
highest first) raised simulated capacity at a 10 s mean TTFT bound from about
3.3 to 15.3 req/s (4.61×, repeats 4.2–4.8×) over the Ascend shortest-job-first
baseline.** This is a virtual-clock simulation result from the maintainers'
campaign ledger. It has no acceptance issue, was not run on NPU hardware and is
not an InferRSI PASS.

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
| **ledger** | From the maintainers' unpublished campaign report or run log; not reproducible from this page. |
| **inferred** | Analysis made during the work and not measured. |

## Campaign 1: vLLM-Ascend waiting-queue order (simulation)

Setup (ledger): real vLLM engine with only the device operators replaced by
stand-ins; a virtual clock calibrated from another team's operator timing
table, step time ≈ 1.313 ms + 0.00468 ms × tokens in the step, error ≤ 3%;
393 multi-turn sessions in which 98.7% of requests contain the whole previous
request; baseline prefix reuse about 14%. Eight candidates ran in parallel;
more saturated the CPU. Wall time of the simulator was 5–45× faster than the
device and was never used as the metric.

| Observation | Cause | Action | Source |
| --- | --- | --- | --- |
| Ordering by *absolute* tokens saved, fewest first: 1.75×; most first: 2.47×; by *share* of the prompt already cached, highest first: 4.61×. | Share favours requests whose remaining prefill is small relative to what is already resident, so cache pages are reused before eviction. | Try the normalised form of a key as well as the absolute one. | ledger |
| 4.61× is the load at which the *mean* TTFT equals 10 s. Requiring every run to stay under the bound gives about 3.9×. | Mean-at-bound and every-run-under-bound are different operating points. | Publish the conservative point next to the headline and name which one is quoted. | ledger |
| At the same 10 s mean, median TTFT moved 1.5 → 5.7 s and the shortest quarter of prompts 1.8 → 9.5 s; the longest-to-mean ratio fell 1.80 → 1.28. | The policy equalises latency: long prompts gain, short cold prompts wait. | Report latency by prompt-length band, not only capacity. State the precondition: prefill-dominated load and no hard sub-second SLO for short requests. | ledger |
| Run-to-run noise was about 4%. Four successive "guaranteed floor" values were each inside the noise and were all withdrawn. | Single-seed differences below the noise are not results. | Below 5% difference: no conclusion. A "better" verdict also needs a mechanism signal (hit rate up, recompute down, queue shorter). | ledger |
| Split validation: sessions halved into an evolution half and an exam half gave 2.06× and 2.01× at the baseline's bound load. | Checks the policy is not fitted to the sessions it was found on. | Always hold out sessions. Note that this split used a larger cache pool than the 4.61× figure; the two numbers must not be combined. | ledger |
| Parameter-level search: −11.2% mean TTFT in 4 generations, then 30 generations without change; the last 80-generation round produced 1 new candidate and 79 duplicates. | The parameter plane was exhausted; the proposer kept regenerating known candidates. | De-duplicate before scoring. When a plane stops moving, switch planes rather than spend generations. | ledger |
| Structure-level search, first round of 5 candidates: only gate tuning helped (10.5%). Later: place by free slots 33.2%, add a starvation quota (1 slot in 8 for the longest waiter) 38.1%, reserve one quarter of slots 28.2%, order by waiting time only 23.6%. | Structural changes reach gains the parameter plane cannot. | Expect most first-round structural ideas to fail; keep the failures in the trial index. | ledger |
| The champion came from a human-written requirement route, not from the automatic mutation chain. | — | Attribute candidates to their actual origin; write "measured on the same scorer", not "found by the model", unless the chain produced it. | ledger |
| Most human effort went into making candidates run on both the NPU path and the simulator (interfaces, parameter adaptation, debugging). | Two execution targets. | Budget the adaptation work explicitly; it is the cost driver, not proposal generation. | ledger |
| At the highest load, recompute was only ten-odd percentage points from perfect reuse with ordering alone, and cold short requests remained slower. | The ordering plane is close to its ceiling. | Next plane: cache residency and admission. | ledger, inferred |

Not established: NPU hardware confirmation of the simulated ranking; paired
per-session statistics instead of the 5% rule; a separate held-out audit split
for the champion.

## Campaign 2: agent-aware KV eviction (CPU replay)

Setup: CPU replay of public agent traces, policy proposed by a model, scored by
hit rate. Code was contributed to
[JiusiServe/vllm-evolve#1](https://github.com/JiusiServe/vllm-evolve/pull/1)
(public). Primary trace: Weka cc-traces with sub-agents
([HF dataset](https://huggingface.co/datasets/semianalysisai/cc-traces-weka-with-subagents-051926), public);
219 traces, about 78,000 requests.

| Observation | Cause | Action | Source |
| --- | --- | --- | --- |
| Trace chains are idle 91% of the time; root agents idle p50 2.0 s / p90 35 s, sub-agents p50 0.54 s. | Tool calls and model turns alternate. | Expected return time is a usable eviction feature; sub-agent KV should stay resident before root-agent KV. | ledger, inferred |
| With 32 sessions and device memory at 10% of the active working set, LRU hit rate 51% against an upper bound of 83% (Belady 78%, prefetch-only 53%); at 25%: 88% against 97%. | The headroom comes from eviction order by expected return, not from prefetch. | Agent-aware eviction is worth searching only when memory is tight; measure the gap to Belady before searching. | ledger |
| After pinning the blocks of running requests, LRU and Belady differed by only 0.7 points (10%) and 3.3 points (25%); without pinning, by 26 points. | The unpinned replay credited evictions a real engine cannot make. | Model engine constraints (pinning, admission queueing) in the scorer before quoting headroom. | ledger |
| A 30-generation exploratory search cost 5.15 USD and moved mean hit rate 60.93% → 61.13%. | Small remaining headroom after pinning; the gain is inside noise. | Compute the reachable headroom first; do not spend search budget on a plane with < 1 point to gain. | ledger |
| On a real vLLM 0.20 engine with Qwen2.5-7B, the evolved eviction function loaded through `--scheduler-cls`, evicted by score, and produced 192/192 identical outputs under batch-invariant mode. | — | The hardware test proves the plug-in runs and keeps outputs; it does not score the policy. Gains come from the RSI scorer only. | ledger |
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
