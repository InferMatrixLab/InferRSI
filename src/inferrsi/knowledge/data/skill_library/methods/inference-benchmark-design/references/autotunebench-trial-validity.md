# AutoTuneBench: treatment delivery and trial validity

Status: source-derived candidate; empirical validation not_run. The ordinary
[source record](autotunebench-source.json) owns the paired repository/paper
identity, inspected regions, digests, rights and unresolved evidence. This
reference supplies an interpretation procedure, not a tuning controller or an
executed benchmark.

Use it when a report attributes an improvement or null result to an enabled
treatment, such as profiler feedback, or claims that a frozen protocol and a
complete gate record establish measurement integrity.

## Bind the treatment and arm-validity contract

Before interpreting outcomes, recover the declared treatment, eligible consumer
calls, first delivery checkpoint, usable-iteration definition, required counts,
exclusions, budget and verdict precedence. Keep these rules distinct from the
report's conclusion. An enabled flag states intent; it does not show that the
treatment reached the measured search.

Apply the actual experiment's validity rules before its benefit/null rules.
When an arm fails a required validity condition, retain its attempts, failures,
observations and costs, and withhold the treatment conclusion that condition
bars. Do not repair the experiment by changing its denominator or acceptance
rule after seeing the result. Numeric bars below belong to this fixed source,
not to InferRSI or a future campaign.

## Follow feedback to the next actual input

Separate four observations: requested collection, produced feedback, serialized
feedback, and delivery to the intended consumer. Identify the run, candidate,
feedback artifact and eligible consumer input that connect them. A non-NULL
output object or a positive summary count alone is not a receipt for the next
prompt.

The exported loop calls the proposer with the previous `last_asi_prompt`. After
a kept candidate N, it collects profiling output, builds ASI feedback and
serializes it for iteration N+1; the adapter inserts that context into the
generation prompt. The first candidate cannot receive feedback produced by
itself, and feedback produced by a final keep may have no later consumer. Treat
this source wiring as a static observation until actual input evidence confirms
the intended exposure. Keep the off-arm's absence of treatment intentional and
separate from failed delivery on the on-arm.

The paper describes a checkpoint that stops both arms if the on-arm's first
keep has NULL ASI. The inspected CLI calls `SearchLoop.run`, while
`_profile_kept` tolerates missing/failed profiling, `_build_asi` permits None,
and the loop records the keep and continues. That first-keep stop is not
implemented in this exported CLI-to-loop path. Original operational plans are
absent from the public tree, so this observation does not establish whether
the authors used an external checkpoint during their experiment.

Sources: [loop](https://github.com/li-ch/autotunebench/blob/64cc8d7ca5d0ee40c4e2189b2c2c8dfb1a2a7c2f/agents/loop.py),
[prompt adapter](https://github.com/li-ch/autotunebench/blob/64cc8d7ca5d0ee40c4e2189b2c2c8dfb1a2a7c2f/agents/adapter.py),
[CLI caller](https://github.com/li-ch/autotunebench/blob/64cc8d7ca5d0ee40c4e2189b2c2c8dfb1a2a7c2f/orchestrator/cli.py);
[paper](https://arxiv.org/html/2609.18123v1), Sections 4.3 and 6.6.

## Apply validity precedence to the source A/B

The paper's Section 4.3 says inadequate usability makes an arm invalid and
bars every other verdict. Section 6.2/Table 3 requires 15 usable iterations out
of 20, but reports the counts below and interprets the result as a shared-wall
null. Preserve that interpretation as the authors' conclusion while exposing
its conflict with the stated precedence rule.

| Arm and public run scope | Attempts | Numeric timing observations | Kept | Keeps with feedback summary | Best `p50_ms` field (ms) |
| --- | --- | --- | --- | --- | --- |
| Off, `8ea96a70` | 20 | 11 | 7 | 0, by design | 2.4840 |
| On, `7b1b274a` | 20 | 14 | 13 | 13 | 2.4957 |

These counts can be read from the public iteration ledger. They support the
reported trajectories, delivery-summary distinction and usability shortfall;
they are not an independently rerun experiment. Both arms fail this source's
minimum count. Under its stated validity precedence, their similar best values
do not establish a valid causal null for profiler feedback. A plateau is a
descriptive observation; treating saturation as its cause still needs a valid
comparison and evidence for the proposed ceiling.

The figure script embeds selected scored points and omits unscored rejects.
Read the full arm denominator rather than counting plotted points. Its constants
refer to an unavailable original report, so the script is not a replacement for
the complete preregistration or actual prompt receipts.

Sources: paper Sections 2.3, 4.3 and 6.2, Table 3 and Figure 3;
[public ledger](https://github.com/li-ch/autotunebench/blob/64cc8d7ca5d0ee40c4e2189b2c2c8dfb1a2a7c2f/observability/iterations.jsonl)
and [figure producer](https://github.com/li-ch/autotunebench/blob/64cc8d7ca5d0ee40c4e2189b2c2c8dfb1a2a7c2f/figs/plot_cand_ab_saturation.py).

## Compare the protocol with reachable checks and records

For each important rule, identify its producer, caller, check and persisted
outcome. Keep a declared requirement separate from enforcement and from the
evidence that enforcement ran.

| Exported boundary | Source observation | Limit on interpretation |
| --- | --- | --- |
| Database ingest | `new_variant` invokes `validate_result` when a harness result is supplied. The validator implements paired engine seed and timing/percentile-key checks, and permits records without measurements. | This is not validation of every value in the frozen protocol. Presence of a `p50_ms` key does not verify its timing/reduction semantics. |
| Correctness gate | G3 rejects missing/zero shape totals and failed shapes; it does not enforce the protocol's minimum of five shapes. | A pass through this function alone does not prove the declared shape coverage. No malformed-packet execution was performed here. |
| Gate persistence | The loop calls G1 and G2/G3, but `_record` supplies an empty verdict map and writes all five iteration-log gates as `n/a`. Those same `n/a` values appear in the two selected ledger scopes. | A complete key set or zero recorded failures is not evidence that all gates passed. Preserve unrecorded and unreached states. |
| Anomaly handling | G5 defines a separate graduation check; the KernelBench tabulator separately marks excessive-speedup rows as anomalies and excludes them from admitted summaries. | Do not infer one universal all-candidate quarantine path from a separate function or tabulation step. |

Sources: [protocol](https://github.com/li-ch/autotunebench/blob/64cc8d7ca5d0ee40c4e2189b2c2c8dfb1a2a7c2f/config/protocol.yaml),
[store](https://github.com/li-ch/autotunebench/blob/64cc8d7ca5d0ee40c4e2189b2c2c8dfb1a2a7c2f/pdb/store.py),
[ingest validator](https://github.com/li-ch/autotunebench/blob/64cc8d7ca5d0ee40c4e2189b2c2c8dfb1a2a7c2f/pdb/ingest_validate.py),
[G3](https://github.com/li-ch/autotunebench/blob/64cc8d7ca5d0ee40c4e2189b2c2c8dfb1a2a7c2f/gates/g3_correctness.py),
[gate container](https://github.com/li-ch/autotunebench/blob/64cc8d7ca5d0ee40c4e2189b2c2c8dfb1a2a7c2f/gates/schema.py),
[G5](https://github.com/li-ch/autotunebench/blob/64cc8d7ca5d0ee40c4e2189b2c2c8dfb1a2a7c2f/gates/g5_graduation.py)
and the loop above.

## Keep comparator and anomaly limits with the numbers

Paper Section 2.3 reports 10.6x against a naive denominator and 2.03x against
its stated honest incumbent. Retain which artifact each denominator denotes;
neither label establishes a strong compiled/tuned comparator. The Level-1
summary uses PyTorch eager and cannot establish superiority over unmeasured
stronger baselines. Reuse the main benchmark procedure's workload, quality,
budget and timing controls instead of treating a large ratio as validation.

The Level-1 report retains 53 raw correct tasks, two quarantined identity
anomalies and 51 admitted tasks. All-positive exposed inputs allowed ReLU-family
identity implementations to pass the available correctness check. Keep the
input-coverage concern and raw/quarantined/admitted counts visible; a passing
exposed check does not justify admitting the anomalous speedup. The source's
greater-than-10x breaker is a contextual rule, not an InferRSI default or proof
that every smaller result is valid.

The results README explicitly leaves a median of 1.0005x versus TABLE.md and
the paper's 1.0001x unreconciled. Preserve both locations and the conflict if
using that number; this distillation does not resolve it. Both are
author-reported readings against eager, not local acceleration evidence.

Sources: paper Sections 2.3, 4.2 and 6.3, Table 4;
[results README](https://github.com/li-ch/autotunebench/blob/64cc8d7ca5d0ee40c4e2189b2c2c8dfb1a2a7c2f/experiments/kernelbench_l1/results/README.md),
[table](https://github.com/li-ch/autotunebench/blob/64cc8d7ca5d0ee40c4e2189b2c2c8dfb1a2a7c2f/experiments/kernelbench_l1/results/TABLE.md)
and [tabulation](https://github.com/li-ch/autotunebench/blob/64cc8d7ca5d0ee40c4e2189b2c2c8dfb1a2a7c2f/scripts/kernelbench_tabulate.py).

## Return an auditable interpretation

Report treatment intent and observed delivery separately, the eligible arm
counts and failed validity conditions, the applicable verdict precedence,
declared versus observed checks, comparator identities, and any anomaly or
source conflict. Name the missing receipt or observation that prevents the
next conclusion. Follow the supplied contract's verdict semantics; this
reference does not create an InferRSI PASS.

When delivery or arm eligibility is unverified, retain the recovery point and
withhold causal benefit/null claims. A future rerun needs its own frozen
contract and authority; reading this reference grants no execution permission.
Existing generic headroom, fixed-workload arithmetic, independent acceptance
and search-budget procedures retain their owners.

## Attribution, distribution and evidence limits

This is original analysis of Li Chen, *AutoTuneBench: Trustworthy Measurement
for Agent Auto-Tuning of LLM Serving Engines*, arXiv:2609.18123v1, submitted
2026-09-16, and its paired public repository. The paper's arXiv license is
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); this reference adapts
its methodology and explicitly preserves conflicts rather than reproducing its
PDF, figures or prose. Repository code/data carry MIT attribution; vendored
third-party code and KernelBench task notices remain separate. No source code
or raw ledger is redistributed. The source record retains the exact rights
dispositions and selected readset.

The paper's measurements remain historical author reports, primarily on one
GB10 box; its held-out MLX result is an algorithm-level port. Original private
registration/checkpoint records and runtime prompt receipts were not
reconstructed. Source tests, devices, model quality, performance and service
behavior were not run locally; agent efficacy was not evaluated. Static source,
record-counting and native package-reader checks do not promote this candidate
or establish an optimization effect.
