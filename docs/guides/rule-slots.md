# Harness rule slots

A **rule** is a replaceable, freezable policy that one managed-loop component
applies on every use, such as the Indexer's ranking weights. A **rule slot** is the
contract that lets a candidate rule be frozen into a plan, delivered, resumed and
replayed without changing code. An improvement loop can then compare one rule
against another while the session controller, budgets, assessment protocol and
raw evidence stay fixed.

This contract is being delivered in phase P0 of the
[Harness² rule-improvement RFC](https://github.com/InferMatrixLab/InferRSI/issues/460),
tracked in [#764](https://github.com/InferMatrixLab/InferRSI/issues/764). It covers
the four components of the [managed optimization loop](../../src/inferrsi/harness/README.md#managed-optimization-loop).
The Indexer is the only component that implements a slot in P0.

## Contract

| Element | Requirement |
| --- | --- |
| Identity | A rule ID, the rule version, the full effective configuration and its SHA-256 configuration digest. The version changes when the semantics of applying the configuration change. Service-reuse records omit the digest because that protocol excludes file fingerprints; they pin the full configuration by value and cross-check plan and manifest. |
| Editable parameters | The rule declares which fields exist and their types. An experiment declares which fields it may edit, with inclusive bounds and a step, and freezes that space before search. Every other field stays at its default. Edits outside the frozen space are rejected before any session or RunStore write. |
| Freeze and resume | A new plan freezes the full configuration and digest, not only a name. Resume rebuilds the rule from the frozen configuration and verifies version and digest. A candidate rule needs no registry entry or code change. A rule whose version the installed runtime does not support is rejected; use the original runtime. |
| Decision trace | Each use of the rule leaves fixed references in the session records, sufficient to replay what the rule returned, delivered and omitted. Archival verification of a retained receipt and exact replay are separate checks: a receipt can still verify after an undelivered corpus entry changes, while exact replay also needs the identical corpus and scoring version. |
| Ownership | A rule is only a parameterized policy. Manager keeps the loop, budgets, pending work, recovery and stop rules. Knowledge owns ranking, Benchmark owns assessment, and Apps only passes the frozen configuration through. A rule cannot start processes, change budgets or read held-out material. |

Search bounds and step sizes belong to the experiment's frozen plan. The
repository declares the fields and validation, not a default search range.

## Component status

| Component | Rule | Inputs → output | Status |
| --- | --- | --- | --- |
| **Indexer** | [`RankingPolicy`](../../src/inferrsi/knowledge/ranking_policy.py) field weights for lexical ranking | Query, eligible corpus and byte budget → ranked hits, delivered context and omissions | Identity, digest and delivery receipts exist. Sessions still resolve the frozen ID through `MANAGED_RANKING_POLICIES`, so unregistered candidates cannot be resumed, and no editable space is declared. P0 closes these gaps. |
| **Analyzer** | None yet. A future rule would order candidate bottlenecks | Critical-path timings, measured speedups and evidence references → an ordered bottleneck list with its basis, delivered to the agent as a suggestion | [`analyzer/`](../../src/inferrsi/harness/analyzer/__init__.py) only validates the caller's bottleneck text and measurement summary. A slot also needs a record of whether the agent followed the suggestion. |
| **Executor** | None yet. A future rule would decide when a running service may be reused | Candidate, configuration, startup cost and cold/warm measurement differences → reuse or restart | Reuse exists within one service-reuse attempt. Reuse across candidates needs its lifecycle and cleanup settled first. |
| **Evaluator** | None yet. A future rule would choose screening cases and escalation conditions | Screening and full-measurement results → which cases to screen and when to escalate | Screening is diagnostic and formal assessment keeps its current owner. Only the development-stage screening and escalation choices would become a rule. |

## P0 delivery

| Slice | Delivers |
| --- | --- |
| S1 | This contract and the component status above. |
| S2 | `RankingPolicy.from_configuration` and `RankingSpace` in Knowledge: rebuild a frozen configuration with version and digest checks, and check a candidate against an experiment-declared space. |
| S3 | Managed sessions accept a candidate ranking configuration, freeze it and resume from the frozen configuration without a registry lookup, for ordinary and service-reuse plans. |
| S4 | Replay of a frozen candidate rule against the frozen corpus reproduces its retained delivery receipt. |

P0 establishes software behavior only. It is not evidence that any candidate rule
improves retrieval or optimization results.
