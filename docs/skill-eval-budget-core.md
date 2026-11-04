# Cumulative PR budget and Git ledger

Refs [#215](https://github.com/InferMatrixLab/InferRSI/issues/215).
`tools/skill_eval_budget.py` implements pure accounting transitions.
`tools/skill_eval_budget_git.py` implements the GitHub Git-data adapter using the
existing authenticated `GitHub.request` client and injected `GITHUB_TOKEN`.
The adapter never loads credentials or executes PR code. Tests use mocks only.

## Accounting

- Key: immutable repository ID plus PR number; never branch name, repository
  name, head revision, workflow run or label epoch. Renames, pushes, retries and
  label removal/reapplication cannot create a fresh PR allowance.
- The requested ceiling is USD 200 per PR, represented as 200,000,000 integer USD
  microdollars. Trusted pricing calculations must round worst-case costs upward.
  Floats, booleans, negative costs and zero-cost reservations are rejected.
- A trusted frozen-plan digest covers all revisions, mapping, exam, provider,
  pricing, retries, request/token limits and other cost-relevant inputs. The core
  receives its independently computed worst-case total; it does not derive cost
  or prove that the plan producer is trustworthy.
- Reserve the entire plan before execution. Charge = audited legacy obligation
  plus **every reservation**, including cancelled, failed, interrupted, completed
  and ambiguous executions. Actual cost is evidence only; there are no refunds.
- An exact plan/run/cost binding is reserve-idempotent. Reusing a plan with a
  different run, or a run with a different plan/cost, fails closed. This first
  version deliberately does not support rerunning an identical plan. A distinct
  authorized attempt must have a distinct frozen identity and a fresh reservation.
  Run identity includes workflow run attempt, not just workflow run ID.

```text
verified genesis → reserved → claimed → finished
                       └───→ cancelled
```

Claim is non-idempotent: at most one process can obtain a successful claim CAS.
No takeover, lease expiry, automatic retry or reset exists. A process crash after
claim burns capacity even when no request happened. `claim_once` returns only on
an explicit, durable CAS success for that invocation. Its return is **not** a
replayable execution credential. The trusted caller must execute at most once,
respect all frozen bounds (including provider retries), and not expose a result
that another worker can reuse to execute again. An actual-cost overrun is rejected
and requires external quarantine/reconciliation before further paid activity;
preventing overruns depends on the future bounded executor.

## Genesis is an audited migration, never a missing-file default

`Genesis(evidence, legacy_charge)` requires an explicit audit reference and an
explicit integer charge. Zero is acceptable only when the authorized audit proves
no earlier paid obligations. Include settled legacy spend and conservative upper
bounds for all outstanding/ambiguous legacy runs; quiesce or reconcile older
writers before migration. Unknown obligations block genesis. If the obligations
exceed the ceiling, initialization fails and the PR is ineligible.

Constructing this value is not authorization or cryptographic proof. The separately authorized
trusted initializer must verify the audit and atomically create only for a key
that has **never** had a ledger. There is intentionally no genesis initializer in the core or Git adapter. Missing/corrupt existing state, HTTP 404, expired artifacts, empty
workflow history and label reapplication are never permission to initialize.

## Atomic storage contract

`AtomicStore.read_verified(key)` returns a `Snapshot(history_token, ledger)` only
from authenticated, durable, current history. `decode` validates schema and local
invariants, **not provenance, rollback resistance or history completeness**.
The backend retains an independently configured genesis/checkpoint anchor that
survives ledger ref deletion. A ledger's own revision cannot detect its reset.
See the precise rollback trust boundary below.
Missing, corrupt, untrusted or discontinuous history must raise and block work.

`compare_and_swap(snapshot, successor)` must atomically append exactly one
successor against the current immutable history token, using
`validate_successor` as well as key/lineage checks. All writers use the same CAS
boundary. A matching body already stored by another request is **not** this
caller's successful commit. On conflict, reread verified state and recompute;
never overwrite a newer charge. On unknown write outcome, do not execute.

Reservation writes can reconcile by rereading the exact binding and charge.
Claim writes cannot reconcile into a new execution grant: an observed `claimed`
entry may already have executed. Duplicate/ambiguous claims stay blocked. If a
verified read still shows `reserved`, a new CAS can compete safely only against
that current token; a delayed earlier write must conflict with the same boundary.
Terminal evidence retries are idempotent only when identical; no terminal update
changes charged capacity.

## Git-data adapter and trusted bootstrap

Each PR uses exactly `refs/heads/skill-eval-budget/<repository_id>/<pr_number>`.
A trusted `LedgerAnchor` supplies immutable repository/PR identity, expected
`genesis_commit`, and independently retained `checkpoint_commit`. These values
must come from reviewed root configuration, **never PR files, artifacts, labels,
comments, caller-selected refs or ledger contents**. The API repository ID is
checked on every verified read; repository renaming does not refresh capacity.

Before activation an authorized operator must quiesce previous paid writers,
audit settled **and outstanding/ambiguous** legacy obligations, and create a
genesis commit with exactly `ledger.json` holding revision-zero state and the
explicit `Genesis(evidence, legacy_charge)`. The genesis may be parentless or have
exactly one explicitly audited existing-main parent when the authorized Git API
requires a parent. Its tree must still contain **only** `ledger.json`; do not
inherit the main tree. Pin the complete genesis commit SHA and checkpoint in
trusted root configuration. That immutable SHA binds the genesis parent as well
as its state. Parent ancestry before genesis is provenance, not ledger history:
verification stops at the pinned audited genesis and never interprets main commits
as budget transitions. Merge genesis commits are rejected. All commits after
genesis still require exactly one parent and one valid accounting transition. An empty ledger is valid only after an explicit no-prior-spend
audit; unknown obligations block bootstrap. Bootstrap/ref creation is deliberately
not automated by this patch and no missing-ledger fallback exists. If the PR had
an earlier ledger, recover/reconcile that history rather than creating new zero
capacity. Unknown/reset history requires operator investigation, not retry-reset.

Reads fetch the exact ref, every single-parent commit and exact ledger tree/blob
back to pinned genesis. They check all accounting transitions and require both
the configured checkpoint and the last tip observed by that store instance to
be ancestors. Missing refs/objects, merges, extra tree entries, corruption,
discontinuous transitions, divergent roots, rollback behind the checkpoint,
identity changes, racing reads and excessive history all block execution.
History verification is bounded to 10,000 commits and 4 MB per ledger; reaching
bounds fails closed, never truncates accounting or resets capacity.

Writes create an immutable tree and a single-parent child of the verified tip,
then PATCH the existing ref with `force: false`. The
[GitHub reference API](https://docs.github.com/en/rest/git/refs#update-a-reference)
requires a fast-forward when force is false. Under append-only writers, two
children of the same tip cannot both become the next tip. A random nonce makes
even identical state transitions different commits, preventing two identical
claims from receiving successful idempotent updates for a shared commit SHA.
Stale snapshots return conflict; failed/uncertain writes return unknown, including
permission/rules rejection. No automatic PATCH retry or claim reconciliation
confers execution permission. Unreachable trees/commits after a crash do not
change accounting; a committed reservation/claim remains permanently charged.
No branch creation, force update, deletion or repository-settings API is used.

### Trust boundary: not protection against malicious administrators

Git refs are mutable by sufficiently privileged principals. The security model
requires trusted root configuration/code and repository administrators, plus no
out-of-band force writes/deletion/recreation of the ledger ref. Use independently
administered append-only restrictions where available; this implementation does
not change settings or bypass rules. A static genesis pin detects a replaced
root but **cannot detect rollback to a valid later ancestor across new processes**.
A trusted checkpoint detects rollback before that checkpoint, and process memory
detects rollback behind a tip already seen in that process. Neither is an external
monotonic witness. The tests explicitly demonstrate this limitation.

Absolute rollback resistance against malicious repository administrators would
require separately authorized, independently durable monotonic storage or an
independently administered enforcement boundary. Do not claim this Git branch
provides it. Retain and advance reviewed checkpoints as audit evidence; never
lower or replace a checkpoint to make a failed verification pass. This document
does not authorize any settings changes, migration, or remote writes.

## Verification and integration boundary

`pytest tests/test_skill_eval_budget.py tests/test_skill_eval_budget_git.py`
covers cumulative limits, permanent reservations, legacy charges, duplicate
plan/run bindings, malformed state, reservation/claim races, unique claim commit
identities, crashes/lost responses, rules rejection, history corruption/deletion,
checkpoint rollback detection and its explicit administrator limitation. The
mock Git API enforces non-force fast-forward semantics. CPU tests do not prove
provider billing or live GitHub rules/permission compatibility.

The adapter does not create a plan, grant label authority, run a provider or
reconcile actual billing. The trusted controller must reserve and claim before
executing, revalidate admission, enforce all worst-case plan bounds including
retries, and keep credentials away from untrusted PR code. A returned claim is
process-local permission for one execution, not a reusable workflow output.
Live activation still requires the audited genesis/root configuration and
successful permitted writes; absent prerequisites fail closed.
