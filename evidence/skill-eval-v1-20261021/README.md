# Skill Eval v1: fixed-workload report audit

Acceptance scope: [#40](https://github.com/InferMatrixLab/InferRSI/issues/40).
Implementation and evidence delivery: [PR #69](https://github.com/InferMatrixLab/InferRSI/pull/69).

Both pinned skills were consumed and applied appropriately, but neither improved
task correctness over the no-skill baseline on this explicit audit task family.
All 18 final matched trials and three discovery probes passed. Across 12 N/E
pairs there were zero failure recoveries and zero correctness regressions.
Explicit conditions recorded higher token totals and mean elapsed times; the
time comparison is confounded by run order, not a causal skill-time effect.
The result supports keeping the useful decision rules and narrowing their scope/consumption cost;
it does not support promoting either candidate as empirically more effective.

## Order corrigendum — 2026-10-22

The original description of the schedule as counterbalanced was incorrect
([review finding](https://github.com/InferMatrixLab/InferRSI/pull/69#discussion_r4339359590)).
The scheduler counted `repeat - 1` in addition to the matched-group index.
The frozen v2 protocol's six groups therefore used rotations `0,1,0,0,1,0`.
Their actual position counts were:

| Condition | First | Second | Third |
| --- | --- | --- | --- |
| N | 4 | 0 | 2 |
| E-benchmark | 2 | 4 | 0 |
| E-evidence | 0 | 2 | 4 |

The measured times and token counts below remain unchanged. In particular,
+12.5% and +36.2% are descriptive differences with order, cache and provider-drift
confounding; they cannot be interpreted as elapsed-time increases caused by
the skills. The limited observation of no incremental correctness benefit
also remains unchanged; it is not a general efficacy estimate.

Future schedules rotate by matched-group index alone. Each condition occupies
each position twice across the six final groups, but this correction does not
rebalance or rerun the historical trial. A credible time-effect study needs a
separately authorized frozen design and budget; no new model calls accompany
this correction.

Historical protocols, outputs, verdicts, measurements and their hashes are
unchanged. The original publication manifest is preserved byte-for-byte as
[`plan/integrity.initial.json`](plan/integrity.initial.json); the
[original report](https://github.com/InferMatrixLab/InferRSI/blob/9a8f565f7629be091ea9f170ab2b93a4b01ec223/evidence/skill-eval-v1-20261021/README.md)
and [plan description](https://github.com/InferMatrixLab/InferRSI/blob/9a8f565f7629be091ea9f170ab2b93a4b01ec223/evidence/skill-eval-v1-20261021/plan/README.md)
remain available at their original revision. The current publication manifest
updates only these two explanatory documents and adds the archived manifest.

## Final outcomes and resource use

| Revised final instance | Correct report verdict | Repeats per N / E-benchmark / E-evidence | Agent-task result |
| --- | --- | --- | --- |
| `holdout-3`: changed step count | INCONCLUSIVE; gain null | 1 / 1 / 1 | 3/3 PASS |
| `holdout-4`: quality failed | FAIL; descriptive gain retained | 2 / 2 / 2 | 6/6 PASS |
| `holdout-5`: three failed requests omitted | FAIL; descriptive gain limited to reported requests | 1 / 1 / 1 | 3/3 PASS |
| `holdout-6`: valid C1-only scope | PASS, fixed_workload | 2 / 2 / 2 | 6/6 PASS |

Both repeated cases had consistent verdicts/findings in every condition. All
21 final calls completed with unchanged workspace inputs, available usage and
independent verifier results. Per-trial answers/checks are under
[`results/v2/`](results/v2/); paired comparisons and exact resource totals are in
[`results/summary.json`](results/summary.json).

| Condition | Tasks passed | Input + output tokens, total | Observed mean agent elapsed time |
| --- | --- | --- | --- |
| N | 6/6 | 195,918 | 58.63 s |
| E-benchmark | 6/6 | 349,476 (+78.4% vs N) | 65.97 s (+12.5%) |
| E-evidence | 6/6 | 379,322 (+93.6% vs N) | 79.88 s (+36.2%) |
| R, separate probes | 3/3 | 143,885 | 66.56 s |

These are descriptive totals/means for this client and exposure strategy.
Elapsed differences are confounded by the unbalanced condition order and may
reflect cache or provider drift; they are not causal skill-time effects or
billing prices. E supplies the
complete bundle inline and as files, and agents also read those files: these
numbers do not estimate the cost of every possible skill-loading strategy.
Input includes cached input (a subset); reasoning output is a subset of output.
Neither is added twice. Agent elapsed time excludes the separate CPU verifier.
R uses different tasks and is not a paired cost comparison with N.

Including retained development, 30/33 allowed task calls were attempted.
Known input-plus-output usage is 1,480,797 across 29 attempts; the interrupted
attempt remains unknown, so this is not an exact total or a certified provider
token cap. Recorded campaign wall time is approximately 2,541 seconds across
both phases, within the 5,400-second allocation. The 3,000,000-token threshold
is an observed-usage stop condition. Two readiness calls are separate: one
transport timeout with unknown usage, then one successful real file-read check
(92.38 seconds, 77,623 observed input-plus-output tokens). Their outcomes are
retained in [`readiness.json`](results/readiness.json). Billing cost remains null.

## Discovery and actual consumption

| Native discovery probe | Observed target-body access | Outcome and interpretation |
| --- | --- | --- |
| [Relevant: kernel-to-service claim](results/v2/R-relevant-R-1/record.json) | Both skill bodies read successfully from `.agents/skills` | Correct INCONCLUSIVE/kernel_only; requests matching HTTP end-to-end evidence. Discovery and correct application are observable. |
| [Ambiguous: summarize scoped measurements](results/v2/R-ambiguous-R-1/record.json) | No observed body read; only task input read | Correct fixed-workload PASS. Selection/content influence remains unknown; a narrow summary need not load both procedures. |
| [Irrelevant: arithmetic only](results/v2/R-irrelevant-R-1/record.json) | No observed body read; only task input read | Correct extraction with null verdict and no acceptance findings. No unnecessary target-body load was observed. |

All 12 E trials received the full assigned bundle and had successful observed
skill-body reads. Both E groups additionally read the shared case in the
dropped-request task. Manual inspection confirms the relevant rule/claim
boundaries were applied correctly, with reasonable smallest next actions.
The no-skill answers were equally correct. No observed command accessed another
trial, protected knowledge copy or verifier/answer root. This audit is narrower
than proving the absence of unobserved exposure. Native catalog trigger cause
and internal content influence are not exposed; no body-read event is not proof
that no knowledge influenced an answer.

## What was evaluated

Two unchanged candidate skills were evaluated on one task family: audit a
fixed-workload performance report. N receives the task alone; E-benchmark and
E-evidence each receive one complete, exact reader bundle. R makes both skills
available through native discovery. Execution uses real ephemeral Codex clients
on Windows, requesting `gpt-6.1-sol` at `xhigh`, CLI
`0.163.0-alpha.10.2`. The provider does not expose seed control or billing cost.

The latency arrays come from the repository's historical Qwen review summary;
quality, request-completion and scope metadata are explicitly counterfactual
fixtures. The descriptive 28.864466% reduction is arithmetic over those inputs,
not a newly measured engine improvement. The final baseline/candidate spreads
are 4.0415% / 3.3173%, below the frozen 12% contract. A passing task means the
agent audited correctly; the audited report may correctly receive FAIL or
INCONCLUSIVE.

| Skill | Exact content revision | Required bundle |
| --- | --- | --- |
| `checkout:inference-benchmark-design` | `sha256:54184fe055e1f072ca8c311eb8571ef54d458a25be86671d9af06b55f0bf845a` | Own procedure/metadata and declared admission-drain-occupancy MD/JSON |
| `checkout:dense-performance-evidence` | `sha256:9183ec24c1f9ce7641a72044e75f1b6559cf882176068bb059c7660f9c130ad7` | Own procedure/metadata and the same declared MD/JSON |

All per-resource hashes and dependency identities are in the
[v2 protocol](plan/protocol-v2.json). No knowledge content, metadata validation
state, matrix, automatic promotion or hardware qualification was changed.

## Retained development and final-instance limits

The first phase attempted 9/33 scheduled calls: 3 PASS, 5 FAIL and one interrupted
INCONCLUSIVE. All original outputs and strict assertions are retained under
[`results/v1/`](results/v1/). The three kernel-to-service answers correctly
rejected the claim but used FAIL where the hidden oracle expected INCONCLUSIVE.
Two workload-mismatch answers correctly diagnosed incomparability but used an
unaccepted label/number combination. The original task had not defined those
field meanings. These are task-contract diagnostics, not evidence of skill harm;
the N answers had the same ambiguity. The interrupted call has unknown usage
and elapsed time. The other 24 entries of that original schedule were not run;
[coverage](results/v1-coverage.json) preserves them explicitly.

Before further calls, an independently reviewed revision made verdict, numeric
null and scope semantics explicit for every condition. Skills and verifier were
unchanged. The four revised final instances used different historical baseline
values and a frozen, position-unbalanced 18-call N/E schedule plus three R probes
(actual first-position distribution 4/2/0; see the order corrigendum above).
These are new values of familiar semantic types, not independent new task types.
One old workload instance was already exposed during development. This is a
bounded final phase with no skill selection/tuning, not an untouched new task
distribution or a population-wide efficacy estimate. Original and revised
results must not be pooled into one efficacy score.

## Knowledge changes supported by the evidence

The following are specific update proposals, not implemented skill changes or
admission decisions.

| Knowledge | Observed use | Recommended change |
| --- | --- | --- |
| Benchmark: fixed-workload comparison, search integrity and scope limits | The [workload answer](results/v2/holdout-3-E-benchmark-1/answer.json) identifies the changed step count, returns null/INCONCLUSIVE and requests the same workload. The [quality answer](results/v2/holdout-4-E-benchmark-1/answer.json) keeps descriptive speed separate from acceptance. | Retain these concise decision rules. Put frozen caller policy before general benchmark advice. |
| Evidence: correctness before speed, isolated-scenario evidence and claim boundaries | The [quality answer](results/v2/holdout-4-E-evidence-1/answer.json) correctly refuses acceptance despite the descriptive gain. The [workload answer](results/v2/holdout-3-E-evidence-1/answer.json) requests comparable measurements. | Retain the evidence-to-claim mapping, with explicit quality and all-request gates. |
| Shared admission-drain-occupancy case: preserve failed requests and the measured denominator | Both E groups successfully read the declared shared case in the [dropped-request trial](results/v2/holdout-5-E-benchmark-1/record.json). Their answers limit the gain to reported requests and require all 18 requests to be accounted for. N identifies the same defect. | Keep the concrete case as a declared dependency; link it directly from the relevant rule rather than treating a successful read as efficacy. |
| Benchmark: “three required regimes”, minimum seeds and default spread | In the scoped cases, the model correctly gives the frozen C1/12% contract precedence; no overgeneralization is observed. The stronger wording in the source is a review concern, not demonstrated harm. | Separate production-coverage advice from a declared narrow campaign. State that regimes, repeat/seed requirements and spread bars are caller policy; remove universal defaults from acceptance wording. |
| Evidence: local numbered levels and the “safe to deploy” row | Deployment safety is not exercised by this pilot. Its local Level 3 means an isolated benchmark, whereas repository L3 means model quality. | Name these evidence-cost tiers to avoid confusion with repository L0–L4. Replace the deployment-safety shortcut with the need for target service, quality and failure-mode evidence. |

Correct attribution in an answer and observed body reads show consumption;
they do not show that the answer depended on the skill. A neutral result on
these explicit audit tasks does not establish that either skill is generally
useless. A further efficacy pilot should use one real task requiring a specific
project invariant or reference, with a clear contract but no supplied solution,
rather than build a larger platform or repeat more ceiling-level audit cases.

## Reproduction, access and evidence boundaries

The [plan](plan/README.md) records reuse, callable entries, freezes, budgets,
source provenance and host-isolation relaxation. Input/schema/verifier identities
were frozen before calls; `execute` rejects changed controller files or skill
revisions. Expected answers and verification stay outside each task workspace.
Every completed trial has saved input hashes, original answer bytes,
assertion results, usage and reviewed redacted command excerpts.

The human allowed controlled exposure without OS read confinement after native
Windows isolation failed. Fresh workspaces/sessions and client-only disabling of
global/bundled skills, plugins, apps, memory and web reduce exposure. Host reads
are still possible; absence of observed leakage cannot prove absence of implicit
or unobserved exposure. No-skill means the target bundle was not supplied or
observed accessed, subject to that limitation.

Raw client/service events, local paths and process identifiers are private.
Redacted protocols and records have their own public integrity manifest and
retain original digests; command output excerpts are explicitly truncated.
Only task/answer/verifier bytes, not redacted records, claim original byte
identity. Public source URLs and provenance are preserved.

```console
python evidence/skill-eval-v1-20261021/validator/replay.py
python tools/validate_evidence.py
```

Replay recomputes assertion sets, including expected v1 failures, without model
access. It cannot replay hosted model execution. The fixed verifier checks
structured outcomes, arithmetic, material findings and required evidence keys;
nonempty explanations alone do not validate reasoning. Independent manual
review covers reasons, smallest next actions and actual skill application.
Generic spread/seed/deployment validation is outside this fixture verifier.
