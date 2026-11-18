# Speculative candidate search and group learning

The experimental implementation of [issue #363](https://github.com/InferMatrixLab/InferRSI/issues/363)
composes bounded VATS, trainable CPU roles, GVO, durable work accounting and
independent final selection. It follows the two loops in
[SpecRSI v2 §3](https://arxiv.org/html/2610.16491v2#S3). It does not reproduce the
paper's language-model training or establish its reported gains. Existing
`campaign` and `benchmarks session` commands keep their serial lifecycle.

## Supported profile and authority

| Component | Implementation | Boundary |
| --- | --- | --- |
| Candidate/evidence model | `harness.search_tree`, `search_records` | Immutable artifacts, actual dependency epochs and complete-candidate selection |
| Solver | `harness.verification_plans`, `vats.menu` | Bounded exhaustive completion plans; conservative integer millisecond caps |
| Drafter | `model.search_roles`, `harness.search_adapter` | Trainable softmax over supplied exact text edits; actual retained changes, not free-form LLM generation |
| Policy | `model.search_roles` | Independent eight-feature linear softmax, recorded behavior probabilities, deterministic deployment actions |
| Scorer | `model.search_roles` | Separate linear model; actual suffix MSE and optional paid continuation differences |
| Work/state authority | `harness.work_control` | Transactions in the shared `RunStore` SQLite database |
| Execution | Existing `scenarios.external` and `local_process` | Absolute deadline and process-domain cleanup; no new subprocess runner |
| Engine | `apps.search_benchmarks.EngineEvaluator` | Existing packaged `optimization.py` as one whole check; currently the Qwen denoiser NPU task |
| Skill | `apps.search_benchmarks.SkillEvaluator`, checkout `tools.speculative_skill.Comparator` | Explicit provider configuration, original baseline, independent grader, separate development/holdout descriptors |
| Final | `harness.search_campaign.finalize` | One-time scope claim before access; receipt-only recovery/export; task promotion only |

This is a trusted local host controller. Resource domains exclude **cooperating
controllers sharing one RunStore**. They are not scheduler/GPU reservations,
filesystem sandboxes, distributed leases, provider cancellation guarantees or
cryptographic attestations. The caller supplies authorized resources and frozen
edit/check permissions. Candidate code cannot enforce its own isolation.

Execution uses one worker. The offline planner represents shared setup and
conflicts; supplied runtime adapters package setup into each whole check. They
do not execute arbitrary standalone shared-setup jobs. Multi-worker performance
qualification remains outstanding.

## Candidate and evidence semantics

`Contract` freezes search ID, context, roles, checks, objective/direction and
candidate/depth/attempt caps. Context includes plan, validator, workload,
environment, original baseline and reference. Objectives must be finite;
overflowing the difference between two finite scores is also rejected. Quality
checks are hard requirements, never compensable by a better score.

`qualify_root` obtains root evidence through claimed real checks. Unknown root
acquisition can only recover its original receipt. `import_qualified_root`
explicitly re-scopes root receipts under identical artifact/check/context
conditions, retaining physical execution and reservation identities. Root check
attempts count against each search's cap; actual acquisition is charged once to
the campaign, separately from independent search returns.

In `A → B → C`, B may be unchecked or fail quality while C is edited and checked.
C needs every required receipt for **C's own artifact** to win. Task failure does
not invalidate descendants. Genuine environment/source dependency invalidation
does invalidate dependent evidence. Dependencies are predeclared; dynamic
introduction of new authorities is unsupported.

`record_receipt` archives registered late results; `evidence` admits only current,
matching receipts. Equal bytes alone do not authorize reuse. Duplicate delivery
is idempotent; conflicts fail. FAIL is an observation; INCONCLUSIVE leaves a
check missing. A valid outcome cannot be repeatedly sampled until it passes.
Permitted retries need new identities and paid reservations.

`Search.invalidate` persists the epoch change and incumbent recomputation
atomically. An invalid root blocks search; late evidence can still be archived
and charged. `ACCEPT` prefers the root on ties, then candidate ID order. It
selects a development result without changing the stable version.

## VATS execution

`Search.start` retains a qualified root and frozen role/settings/adapter hashes.
Each decision claims and meters Solver/Scorer/Policy preparation, constructs
bounded DRAFT/VERIFY/ACCEPT actions and records the behavior law and paid state.
Completion bundles remain in the menu; Scorer predictions never become receipts.
Optional refinement adds unions without removing base completions. An undersized
menu cap fails explicitly. Collection samples Policy; deployment uses argmax.
Drafter edits remain sampled from the supplied permitted vocabulary.

The chosen work block is persisted before execution. Each edit waits for its
parent artifact, without waiting for parent quality. Each check binds candidate,
contract, attempt, execution, reservation and domain. Settlement commits elapsed
time, cleanup facts and evidence/incumbent changes in one transaction. Recovery
continues the retained block cursor before making another Policy decision.

ACCEPT and limits return only complete admissible versions. Unstarted work stops
when its conservative cap no longer fits. Unknown launched operations block
continuation until reconciled. Candidate, depth, step, menu and attempt limits
bound the search independently of its time budget.

The planner closes prerequisites, counts shared costs once and checks conflicts.
`max_targets` limits completion **seeds**, not candidates incidentally completed
by cross-candidate prerequisites. `max_jobs` bounds the whole supplied job graph.
The exact algorithm targets small menus. `draft_ahead=False` and `bundled=False`
are explicit ablation switches; they are not claims of comparative efficiency.

## GVO and paid continuations

`collect_group` requires at least two independent complete searches with the same
root, contract, budget, snapshot and adapter. Each owns a tree and seed. The
campaign must be able to provide equal declared budgets before collection.
Leaves from one tree are not independent group members.

`gvo.examples` computes whole-search returns and leave-one-out advantages.
Natural sampled Drafter/Policy choices supply the clipped PPO-style objective
with KL regularization against a frozen reference. Scorer targets use actual
remaining gains and future costs from each paid decision boundary. Current
preparation is sunk for that suffix but stays in total campaign cost. Missing
labels/cost observations are never zero-filled. Penalties and training settings
are explicit frozen conditions.

`train_group` checks retained settled records and replayed behavior probabilities,
updates separate actual parameter arrays and commits checkpoint plus training
receipt. `learn` supports Reset/Carry and reuses completed updates on resume;
unknown training cannot be relaunched. An initial checkpoint with explicit
provenance is required. This profile provides neither a pretrained model nor a
supervised warmup dataset.

`search_continuations.continue_from` copies a retained paid state, charges the
copy, forces one legal first action and continues the frozen policy. The entire
suffix is Scorer-only. `paired_targets` requires the same source state, settings,
snapshot, adapter and continuation seed with different first actions. Both
absolute suffix targets and observed relative differences train the Scorer.
Caller-authored unreceipted pair targets are rejected.

These are real updates to a constrained CPU operator model. They are not LLM
finetuning, prompt summarization or evidence of pretrained-model improvement.
Apps injects the role snapshot's `choose`, `predict`, `train`, `restore` and
`document` operations. Harness retains traces and controls when they may run;
it has no import dependency on Model.

## Accounting, recovery and final

`WorkControl` extends the existing RunStore database with campaign, domain and
holdout tables. It is the authority for this experimental runtime, not a mirror
of serial-session manifests. One transaction reserves work/domains and registers
the pending tree attempt. Controllers using the same resource or holdout must
use the **same shared store**.

Launch intent is durable before dispatch; an ambiguous crash never authorizes a
second launch. Known elapsed time and cleanup release unused reservation.
Unknown usage/cleanup retains the entire reservation and domain. Over-cap work
is charged and blocks promotion. Absolute deadlines include queueing and cleanup.
In-process bounded planning, editing and training are checked after return;
they are not forcibly preempted like subprocesses. Preflight freezing and initial
setup are outside this campaign meter, a remaining lifecycle-cost limitation.

Receipts bind candidate/adapter identities and content hashes. They detect
accidental mutation under a trusted host, not malicious-host forgery. Recovery
checks retained candidate bytes and never launches new work. Lost preparation,
training or copy receipts remain unresolved; no guessed-cost retry is available.
External process-liveness reconciliation needs a qualified authority.

`finalize` consumes a unique scope in the shared store before final data access,
freezes selection and closes search/training. Engine compares again with the
original baseline. For Skill, supply a **holdout-bound adapter** and
`Comparator.holdout_scope` (derived from the frozen data digest), never the
development adapter or a replacement label. Exact bounded radix utility keeps
quality before token use; reduced tokens cannot offset a quality regression.

After interruption, final consumes existing receipts only. Even an unstarted
remaining check cannot be newly dispatched by recovery. Existing final results
are immutable; export never reruns them. Only complete accepted final evidence,
known cleanup and valid budget can update `stable`. Role checkpoints are never
automatically promoted to a production/default improver. Such promotion needs
separate independent data and acceptance authority.

Enforced spend is in milliseconds. Skill reports retain provider token/currency
facts, and the existing comparator enforces its per-comparison limits. A
**campaign-wide provider token/currency reservation bridge is not implemented**.
Elapsed-time caps must not be presented as that guarantee.

## Entry points

`inferrsi search engine --help` lists explicit Engine bounds and permissions.
Supply a fresh `--session`, shared `--store`, unique `--campaign`, packaged task,
initial checkpoint, edit vocabulary, authorized resource domain, time/search/
training bounds, independent group count, rounds, final scope and final threshold.
Task protocol flags follow `--`, for example `--pairs 1 --samples 1 --warmups 0`
when the campaign owner chooses one measurement per arm. No gate is inferred.
A domain name does not allocate a device.

Checkpoint JSON contains numeric arrays `drafter`, `policy`, `scorer` and nonempty
`origin`. Drafter dimensions match edits; Policy/Scorer each have eight dimensions.
Freeze initial parameters and provenance in the campaign plan.
`--edit TOKEN FILE BEFORE AFTER` permits one exact replacement in a candidate
relative file; candidates cannot change the evaluator or roles.

Read/export without execution:

```bash
inferrsi search status --session <session-directory>
inferrsi search export --session <session-directory> --output <result.json>
```

Python composition uses `qualify_root`, `collect_group`, `learn`, `continue_from`
and `finalize`. Recovery requires the original frozen adapters. The CLI has no
blind whole-campaign restart command. Skill's checkout `Comparator` takes the
existing comparator configuration with an explicit bounded provider, original
Git baseline, editable bundle paths and two split descriptors (`path`, `sha256`,
`scope`, `task_count`). It uses the existing private Git-index materializer,
executes the existing comparator under the shared process executor and revalidates
its independent retained report. Construction does not load holdout bytes.
Provider readiness/credentials/authorization remain existing explicit requirements.

## Validation and issue completion

```bash
python -m pytest tests/test_speculative_search.py tests/test_verification_plans.py \
  tests/test_work_control.py tests/test_search_roles.py tests/test_vats_runtime.py \
  tests/test_search_benchmarks.py
```

Controls cover exhaustive planning, failed-parent repair, finite-score overflow,
concurrent domain claims, unknown reservations, atomic evidence/accounting,
invalid roots, process-backed CPU searches, numerical actor-gradient checks,
parameter updates, fresh searches, paid continuations, recovery and final export.
The numeric process grader and Skill report fixtures test software behavior;
they are not real task/provider efficacy evidence.

| Issue area | Delivered software | Still required for full acceptance |
| --- | --- | --- |
| AC-01/02 | Support/permission boundaries and immutable trees | Production role/environment qualification |
| AC-03/05 | Durable transitions, late receipts, invalidation, bounded synchronous VATS | Production adapter fault/race evidence |
| AC-04 | Exact planner, independent oracle and Scorer refinement | Scaling and real complementary-check evidence |
| AC-06 | Independent groups, actor/value updates, paid continuations, checkpoints, Reset/Carry | Actual task training results and role qualification |
| AC-07 | Shared local claims, elapsed-time caps and cleanup-aware recovery | Host callback preemption, provider/device total accounting and production resource integration |
| AC-08 | One-time final scope and task promotion gate | Real independent final evidence and separate default-improver qualification |
| AC-09 | Packaged Engine evaluator and explicit Skill comparator bridge | Both complete real VATS/GVO/final pilots |
| AC-10 | Retained trajectories/costs and ablation switches | Serial/VATS, bundle, learning, Reset/Carry and worker experiments with full lifecycle costs |

The parent issue remains open. Software tests, CPU mathematical checks or an
available adapter do not establish full acceptance, NPU speedup, provider quality,
search efficiency or universal SpecRSI gains.
