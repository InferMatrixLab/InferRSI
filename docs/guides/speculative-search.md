# Speculative candidate search and group learning

The experimental implementation of [issue #363](https://github.com/InferMatrixLab/InferRSI/issues/363)
composes bounded VATS, trainable CPU roles, GVO, durable work accounting and
independent final selection. It follows the two loops in
[SpecRSI v2 §3](https://arxiv.org/html/2610.16491v2#S3). It does not reproduce the
paper's language-model training or establish its reported gains. Existing
Project and benchmark `session` commands keep their serial lifecycle.

## Supported profile and authority

Direct callers import `EngineSearchPlan`, `run_engine_search` and `read_engine_search`
from `inferrsi.harness.manager`. Apps parses `inferrsi search engine` arguments and
supplies the checkpoint loader and evaluator factory. Manager checks the campaign cap
and final reserve before either callback runs or any session or RunStore is created.
It selects a candidate using development evidence, binds that candidate to one final
evaluation and returns the stored result. `read_engine_search(session)` reads it back.

The search implementation moved from the Harness root to `harness/manager/search/`.
This includes `gvo`, `improvement`, `search_adapter`, `search_campaign`,
`search_continuations`, `search_records`, `search_tree`, `vats`, `verification_plans`
and `work_control`. For subprocess environment setup, replace imports of
`runtime_environment` from `inferrsi.harness.optimization_session` with
`from inferrsi.harness.executor import runtime_environment`.

| Component | Implementation | Boundary |
| --- | --- | --- |
| Candidate/evidence model | `harness.manager.search.search_tree`, `search_records` | Immutable artifacts, actual dependency epochs and complete-candidate selection |
| Solver | `harness.manager.search.verification_plans`, `vats.menu` | Bounded exhaustive completion plans; conservative integer millisecond caps |
| Drafter | `apps.workflows.search_roles`, `harness.manager.search.search_adapter` | Trainable softmax over supplied exact text edits; actual retained changes, not free-form LLM generation |
| Policy | `apps.workflows.search_roles` | Independent eight-feature linear softmax, recorded behavior probabilities, deterministic deployment actions |
| Scorer | `apps.workflows.search_roles` | Separate linear model; actual suffix MSE and optional paid continuation differences |
| Work/state authority | `harness.manager.search.work_control` | Transactions in the shared `RunStore` SQLite database |
| Execution | Existing `executor.trials.external` and `executor.local_process` | Absolute deadline and process-domain cleanup; no new subprocess runner |
| Engine | `apps.workflows.search_benchmarks.EngineEvaluator` | Existing packaged `optimization.py` as one whole check; currently the Qwen denoiser NPU task |
| Skill | `apps.workflows.search_benchmarks.SkillEvaluator`, checkout `tools.speculative_skill.Comparator` | Explicit provider configuration, original baseline, independent grader, separate development/holdout descriptors |
| Final | `harness.manager.search.search_campaign.finalize` | One-time scope claim before access; receipt-only recovery/export; task promotion only |

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

Experimental records predating `initial_conditions` remain readable/exportable
through WorkControl, but cannot resume or enter GVO training. Start fresh searches
from qualified evidence; there is no migration that guesses a historical starting
tree from a later tree. Receiving search/attempt IDs may differ after an explicit
root import; actual execution identities, evidence and dependency epochs must agree.

The chosen work block is persisted before execution. Each edit waits for its
parent artifact, without waiting for parent quality. Each check binds candidate,
contract, attempt, execution, reservation and domain. Settlement commits elapsed
time, cleanup facts and evidence/incumbent changes in one transaction. Recovery
continues the retained block cursor before making another Policy decision.
An ACCEPT already retained in the trace is terminal even if the controller
stopped before writing the completed status. Recovery finishes that decision
without sampling or charging another preparation, including forced ACCEPT.

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

VATS spends a search budget using a frozen Drafter, Policy and Scorer. GVO
updates those three roles **between** collections. The Solver's feasibility
rules, verification contract and real evaluator stay fixed across the update.
The formal objectives are in [SpecRSI §3.4](https://arxiv.org/html/2610.16491v2#S3.SS4).

1. **Collect a group.** Start at least two independent VATS searches from the
   same root, initial evidence and history, role checkpoint, adapter and budget.
   Each search has a separate tree and random seed. The controller checks that
   the campaign can fund all declared search budgets before collection. Record the legal choices,
   sampled actions, their probabilities, the paid work and its verified outcomes.
2. **Give the Drafter and Policy whole-search credit.** Let `F` be the best
   observed gain among candidates that satisfy every required check. For search
   `i`, compute the return and its leave-one-out advantage:

   ```text
   R_i = F(end_i) - F(start_i) - expense_weight * spent_seconds_i
                               - elapsed_weight * wall_seconds_i
   A_i = R_i - mean(R_j for all other searches j in this group)
   ```

   For returns of 8, 5 and 2, the advantages are +4.5, 0 and −4.5. Every
   naturally sampled edit or plan choice in a search receives that search's
   advantage. This gives an early edit credit when a later descendant earns a
   verified gain. Replay the recorded action probabilities and apply the
   PPO-style clipped probability ratio, with KL regularization against the
   fixed initial actor. The ratio is the current probability of the sampled
   choice divided by its recorded collection probability, under the same legal
   menu and sampling settings. With the default single update per group this
   ratio starts at one, so clipping is inactive on that gradient step.
   Deployment trajectories are excluded. Both cost
   weights default to zero. Work still counts against the hard budget.
3. **Train the Scorer on realized continuation returns.** At each paid decision
   boundary fit the predicted plan value to the gain still to come, less the remaining
   measured work and time penalties. If the best verified gain is 3 at that
   boundary and ends at 8, the unpenalized target is 5. Preparation already
   performed stays in the whole-search cost. Missing results supply no target. When two alternative first
   actions have both been executed from a saved state, the difference between
   their realized returns also supervises the difference in predicted values.
4. **Save the update and collect fresh evidence.** `train_group` verifies the
   records, updates the three sets of weights and settles the training receipt
   and checkpoint together. A resumed run reuses a settled update and blocks
   a second training launch if the first outcome is unknown. Reset keeps the
   original root for the next group.
   Carry starts the next group from the best fully verified candidate and its
   receipts. Final measurements are reserved for independently retesting the
   selected candidate.

The [collection and target code](../../src/inferrsi/harness/manager/search/gvo.py) and the
[CPU role update](../../src/inferrsi/apps/workflows/search_roles.py) implement these
steps with finite edit operators, a linear Policy and a linear Scorer. The
caller supplies the initial checkpoint and its provenance.

`search_continuations.continue_from` copies a retained paid state, charges the
copy, forces one legal first action and continues the frozen policy. The entire
suffix is Scorer-only. `paired_targets` requires the same source state, settings,
snapshot, adapter and continuation seed with different first actions. Both
absolute suffix targets and observed relative differences train the Scorer.
Caller-authored unreceipted pair targets are rejected.
The saved source step counts toward the continuation's original step limit and
random-stream position; omitting the prefix from its training trace does not
grant additional decision slots.

These are real updates to a constrained CPU operator model. They are not LLM
finetuning, prompt summarization or evidence of pretrained-model improvement.
Apps injects the role snapshot's `choose`, `predict`, `train`, `restore` and
`document` operations. Harness retains traces and controls when they may run;
it has no import dependency on the Apps role implementation.

## Accounting, recovery and final

`WorkControl` extends the existing RunStore database with campaign, domain and
holdout tables. It is the authority for this experimental runtime, not a mirror
of serial-session manifests. One transaction reserves work/domains and registers
the pending tree attempt. Controllers using the same resource or holdout must
use the **same shared store**.

Launch intent is durable before dispatch; an ambiguous crash never authorizes a
second launch. Known elapsed time and cleanup release unused reservation.
Unknown usage/cleanup retains the entire reservation and domain. Over-cap work
blocks further claims and dispatch of previously reserved work. The launch
transaction rechecks the campaign before recording intent. With unknown cleanup,
the retained hold is at least the largest known usage. Later reconciliation
releases the domain and charges the final usage once, never below that lower
bound. Absolute deadlines include queueing and cleanup.
Engine protocol timeouts retain an INCONCLUSIVE adapter receipt with measured
elapsed time. Confirmed cleanup of both task and protocol permits settlement
and domain release; uncertain protocol cleanup keeps the reservation. A known
overrun still blocks the campaign, even after its domain has been released.
If cleanup settles blocked search work before its pending pointer is cleared,
recovery archives that pointer from the durable operation without reading the
adapter again. It charges the search's observed cost once, abandons the active
block and records verification as control-only `INCONCLUSIVE`. The output is
not adopted, and the campaign remains blocked against further dispatch.
In-process bounded planning, editing and training are checked after return;
they are not forcibly preempted like subprocesses. Preflight freezing and initial
setup are outside this campaign meter, a remaining lifecycle-cost limitation.

Receipts bind candidate/adapter identities and content hashes. They detect
accidental mutation under a trusted host, not malicious-host forgery. Recovery
checks retained candidate bytes and never launches new work. Lost preparation,
training or copy receipts remain unresolved; no guessed-cost retry is available.
External process-liveness reconciliation needs a qualified authority.

When a reservation expires or its campaign is blocked before launch intent,
recovery settles it as `not_started` and releases its domain in one transaction.
Search recovery clears the pending operation and ends the current block. A
registered verification attempt gets a control-only
`INCONCLUSIVE` receipt, with no objective or evaluator PASS. No execution is
charged. A search whose limit has expired can then return its qualified incumbent.
If only the operation deadline expired, the remaining campaign may continue with
fresh claims. This exception does not apply to ambiguous launch-intent crashes.

Before claiming a final scope, `finalize` reads the completed deployment search
from the campaign store. It recomputes the winner from verified development
receipts, compares it with the recorded selection and the supplied candidate,
and verifies the retained candidate files against the selected artifact digest.
A root can enter final when a completed deployment selected it. Root qualification
alone, a training collection, and a forced continuation cannot supply that selection.
If several deployments completed, pass `deployment_search` to name the one used
for selection. The first claim freezes the deployment, winner and acceptance
rule at the same campaign revision, then closes search/training before final
data access.

For a new Python final, pass `acceptance=FinalAcceptance()` to require all
checks to pass with verified cleanup. With
`acceptance=FinalAcceptance(minimum_objective=1.2)`, the same checks apply and
the deployment’s designated objective must also reach 1.2. The claim records
the rule version, required checks, threshold and, for a numeric threshold, the
objective check. The Engine CLI uses its explicit `--minimum-final-score` when
comparing against the original baseline. For Skill, supply a **holdout-bound
adapter** and `Comparator.holdout_scope`, derived from frozen task membership. The raw SHA-256
separately pins each file's exact bytes. Root qualification and VATS search use
the development evaluator. Finalization checks that its comparator matches the
one bound to the recorded development evidence. After the final claim and before
any provider or grader call, the comparator parses the same verified bytes for
both splits, checks the declared membership, and rejects shared case IDs or
identical case inputs across splits. Changing JSON formatting, case order, IDs
or provenance gives the same set of inputs a single final allowance in the
shared store. Exact bounded radix utility keeps quality ahead of token use.

The finalizer holds a campaign-specific OS file lock in the shared RunStore
from before the holdout claim through the final commit. A concurrent finalizer
gets a lock error while that call is active. After an interruption, call
`finalize` with the original candidate and scope and omit `acceptance` to
apply the saved rule. If the owner exited before reserving a required check,
recovery records that check as `not_started: unreserved` with zero usage.
It reconciles registered work from its receipts. Once accounting is complete,
any unreserved check makes the final `INCONCLUSIVE` and preserves the
incumbent. The holdout remains consumed. For older claims that predate the
lock, recovery can certify an unreserved check once the original campaign
deadline has passed or the campaign has blocked further dispatch.

Supplying a different rule during recovery is rejected. Earlier Python
callers that passed an `accept_result` callback must select a declarative rule
for new finals. A historical claim without a verifiable rule can only settle
usage and cleanup. The same applies when its selection cannot be verified or
its candidate files have changed. Once reconciled, the final is INCONCLUSIVE
and the incumbent is preserved. A claim with a newer rule version stays pending
for a runtime that understands it. Each new receipt binds the physical operation ID. An older final
receipt without that ID needs its matching executor record from the claimed
operation, including the output path recorded at execution. Missing proof,
unknown usage or unknown cleanup keeps the reservation. Existing final results
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
`scope`, `task_count`). When preparing data, compute `task_set_sha256` with
`tools.speculative_skill.task_set_sha256(cases)` and include it in the holdout
descriptor before starting a campaign. The field is optional for development.
The comparator uses the existing private Git-index materializer and shared
process executor, and revalidates its independent retained report. Construction
does not load holdout bytes. Providers require explicit authorization and
credentials.

Older descriptors can still serve development. Search histories written before
comparator identity was recorded remain readable for reporting. A new Skill
final requires a completed deployment whose development evidence identifies
the same comparator. Upgrade all Skill controllers that write the shared store
together, since older controllers enforce raw-byte scopes. If the store contains
old `skill-data:` claims, bind each consumed claim to its archived input with
`tools.speculative_skill.migrate_holdout(control, raw_sha256, archive_path)`.
The migration verifies those original bytes and records the membership of the
already-consumed set. Missing archives keep new Skill final claims blocked.

## Relation to the paper and reference implementation

This is a constrained adaptation of the two-loop method, not a reproduction of
the reference model or experiments. The comparison below uses
[SpecRSI v2, section 3 and Algorithms S1-S3](https://arxiv.org/html/2610.16491v2#S3)
and the authors' [reference source](https://github.com/SpecRSI-GPR/SpecRSI/tree/ff0f0bb607e53ba76eebb9960df3d6942c33027e).
That source revision is research provenance, not an InferRSI campaign pin.

| Mechanism | This implementation | Alignment and limits |
| --- | --- | --- |
| Frozen search and acceptance | Immutable descendants, separate real evidence, DRAFT/VERIFY/ACCEPT, complete-root fallback | Follows the central control contract; intermediate parents need not pass |
| Natural group learning | Independent matched searches, leave-one-out advantage, recorded actor probabilities, clipped objective and fixed-reference KL | Same objective structure; updates a small CPU operator model |
| Value supervision | Actual paid-state suffix returns and optional paid pair differences; forced trajectories excluded from actors | Same separation of targets; continuation recovery must preserve the original remaining work limits |
| Drafter | Softmax over a caller-supplied exact-replacement vocabulary | The reference uses generated edit tokens with a trainable LoRA adapter on a frozen language model; this vocabulary cannot propose a new edit outside its supplied operators |
| Policy and Scorer | Separate linear weights over eight aggregate features | The reference uses separate relation/message-passing and attention branches with semantic and observed-evidence inputs; these linear features omit those inputs |
| Solver and refinement | Exhaustive unions of completion seeds, one job per candidate/check; optional pairwise seed-union scoring | The reference supports MILP covers, singleton check closures, shared setup and iterative job-closure extensions; this restricted planner is not a general substitute |
| Training recipe | Caller-provided initial checkpoint; direct CPU gradient updates | No supervised warm-up pipeline or language-model training adapter; the reference's warm-up, role architecture and optimizer configuration are not reproduced |
| Resources and evaluation | One worker, millisecond reservations, whole Engine/Skill checks | No equivalent campaign-wide token/currency cap, arbitrary setup execution, parallel-worker study or matched reference benchmark runs |

The architecture and training distinction can be inspected in the reference
[role model](https://github.com/SpecRSI-GPR/SpecRSI/blob/ff0f0bb607e53ba76eebb9960df3d6942c33027e/src/specrsi/learning/hf.py),
[relation heads](https://github.com/SpecRSI-GPR/SpecRSI/blob/ff0f0bb607e53ba76eebb9960df3d6942c33027e/src/specrsi/learning/heads.py),
[completion solver](https://github.com/SpecRSI-GPR/SpecRSI/blob/ff0f0bb607e53ba76eebb9960df3d6942c33027e/src/specrsi/planning/completion.py),
[menu construction](https://github.com/SpecRSI-GPR/SpecRSI/blob/ff0f0bb607e53ba76eebb9960df3d6942c33027e/src/specrsi/core/vats.py)
and [training recipe](https://github.com/SpecRSI-GPR/SpecRSI/blob/ff0f0bb607e53ba76eebb9960df3d6942c33027e/docs/REPRODUCIBILITY.md#training-the-reference-roles).
These were inspected as source, not executed as a reproduction experiment.

Two limits matter when interpreting learning results. First, at the same state,
verification bundles with equal total cap and job count have identical features
in `vats.features`, hence identical linear Scorer values and Policy preferences.
Their candidate identity, observed failures and check interactions cannot affect
that comparison. Parameter updates alone therefore do not demonstrate learning
the paper's complementary-check value function. Second, `Settings.refine_queries`
defaults to zero, and the Engine CLI exposes no override. Its search does not use
the trained Scorer to refine the menu; the supplied Engine/Skill evaluators also
expose one indivisible check per candidate. Python callers can enable the bounded
refinement, but that does not add the missing semantic or relational inputs.

Moving toward a reference reproduction requires explicit role/feature and menu
contracts, a qualified generative/trainable adapter with warm-up, lifecycle cost
accounting, and replicated frozen-versus-trained comparisons across tasks and
independent training checkpoints.
The existing recovery, evidence and holdout controls remain useful foundations;
passing them does not establish search efficacy or reproduce paper results.

## Measuring the contribution of GVO

Compare three deployment arms on the same task. A fixed-order serial control
measures a simple alternative search order. VATS with the initial checkpoint
measures what the search can find before training. VATS with the trained
checkpoint measures what changes after GVO. To isolate learning, compare the
last two arms at the same deployment seed, candidate budget and evaluation
protocol. Use the independently retested final candidate as the outcome.
Weight changes and development scores show what happened during training and
selection. The cost of obtaining a checkpoint includes every collection
search, even one that returned the root without an improvement.

The [Qwen diagnostic plan](../../evidence/qwen-vats-gvo-910b1-20261124/plan/plan.json) fixes one
worker, the two [allowed edits](../../evidence/qwen-vats-gvo-910b1-20261124/plan/edits.json), the
initial weights, limits, seeds and arm order. Both edits reuse existing
intermediates in the denoiser. One hoists the invariant text projection out of
the denoising loop. The other hoists shared scale and gate computations out of
the transformer-block loop. The serial control tests the first edit and then
the combination. VATS can also test the second edit independently, repeat an
edit choice on another branch, or stop early. Its five primitive attempts
include the imported root check, leaving room to draft two candidates and
verify both. The root qualification is physically executed once and shared.
Each arm can spend up to two new candidate checks and receives a fresh final.

The [experiment driver](../../evidence/qwen-vats-gvo-910b1-20261124/plan/run.py) calls the packaged
Engine evaluator for all three arms and uses the PR's unmodified `Search`,
`learn` and `finalize` for VATS. The serial control evaluates the declared
order directly through the same Engine evaluator. To repeat from the checkout
in an environment with one allocated Ascend NPU, the frozen runtime dependencies,
and an unused output path, run the driver from the repository root.

```bash
PYTHONPATH=src python evidence/qwen-vats-gvo-910b1-20261124/plan/run.py ./qwen-gvo-run
```

The output contains the shared RunStore, checkpoints, all task snapshots,
timings and per-step numerical checks. Arm order rotates across three blocks
so each arm runs first, second and last once. All three blocks
reuse one trained checkpoint. Their random seeds vary the search on the same
workload. The driver saves the full arm order before starting. A VATS arm
contributes a score only when `finalize` reports an overall PASS and promotes
the selected candidate, and the fresh task result passes with verified cleanup.
An interrupted or rejected arm retains its incomplete status, later arms retain
their unrun status, and the driver publishes paired ratios only for a complete
comparison. Training variability and transfer to other tasks require additional
independent runs.

### Ascend 910B1 diagnostic results

On 2026-11-24, all nine deployment runs selected the **same candidate bytes**
and each arm verified two candidates per deployment. Frozen and trained VATS
both drafted the two edits in the same order, then verified both candidates in
one bundle. The table reports independent-final speedups against the original
denoiser. The last column divides the trained score by the frozen score within
the same deployment block.

| Deployment seed | Fixed serial | Frozen VATS | VATS + GVO | Trained vs. frozen |
| ---: | ---: | ---: | ---: | ---: |
| 101 | 1.1496× | 1.1562× | 1.1656× | +0.81% |
| 202 | 1.1389× | 1.1457× | 1.1546× | +0.78% |
| 303 | 1.1542× | 1.1557× | 1.1434× | −1.07% |
| Geometric mean | 1.1475× | 1.1525× | 1.1545× | +0.17% |

The paired score difference was **+0.17%** for trained versus frozen VATS
and **+0.61%** for trained VATS versus the fixed serial control. Repeated
measurement of the same code produced all three values in each row.
The two edits delivered the observed denoiser speedup. This pilot found no
additional candidate-quality or evaluation-count benefit from GVO.
The default zero refinement queries also leave the Scorer outside deployment
action selection in this configuration.

One shared root qualification took 38.34 s. The six independent training
searches and one update took **297.99 s**, including nine candidate evaluations.
All three role weight vectors changed. Mean online time, including independent
final, was 97.35 s for serial, 96.42 s for frozen VATS and 95.30 s for trained
VATS. Over three deployments, collection, training and trained deployment took
**583.90 s**, compared with **289.26 s** for frozen deployment. Both totals
exclude the common root, queue, container startup and setup. The small online
timing difference does not establish a repeatable saving or break-even point.

The verifier replayed all 37 completed five-case task evaluations (1,998
compute calls) and the earlier device-initialization failure. An offline audit
of the archived RunStore also confirmed that all six VATS deployments promoted
their selected candidate and bound its final receipt to the measured files.
The three serial controls have direct independent task finals. Overall search
efficacy remains **INCONCLUSIVE**. The [evidence bundle](../../evidence/qwen-vats-gvo-910b1-20261124/README.md)
links the frozen inputs, checkpoint, per-trial index, archive availability and
raw-data verification instructions.

## Validation and issue completion

```bash
python -m pytest tests/harness/test_speculative_search.py tests/harness/test_verification_plans.py \
  tests/harness/test_work_control.py tests/apps/test_search_roles.py tests/harness/test_vats_runtime.py \
  tests/apps/test_search_benchmarks.py tests/campaigns/test_qwen_gvo_diagnostic.py
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
| AC-06 | Independent groups, actor/value updates, paid continuations, checkpoints, Reset/Carry | Replicated learning across checkpoints and tasks, and role qualification |
| AC-07 | Shared local claims, elapsed-time caps and cleanup-aware recovery | Host callback preemption, provider/device total accounting and production resource integration |
| AC-08 | One-time final scope and task promotion gate | Real independent final evidence and separate default-improver qualification |
| AC-09 | Packaged Engine evaluator and explicit Skill comparator bridge | Live Agent/Skill pilot and broader Engine coverage |
| AC-10 | Retained trajectories/costs and ablation switches | Replicated learning and bundle, Reset/Carry and worker comparisons with full lifecycle costs |

The maintainer accepted the single-worker local VATS/GVO runtime, its recovery
and final-evidence controls, and the bounded Engine diagnostic as a separately
reviewable delivery for PR #488. The software controls and the archived
measurements are the evidence for that slice. Issue #363 remains open for the
criteria in the last column. [Maintainer’s scope decision](https://github.com/InferMatrixLab/InferRSI/issues/363#issuecomment-7124911509).
