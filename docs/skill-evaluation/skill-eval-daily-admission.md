# Global daily admission rollout (offline implementation)

The controller requires **both** the permanent USD 200 lifetime PR ledger and
one repository-wide USD 1,000 / Asia/Shanghai-day ledger. All PRs compete against
one immutable repository identity and one global ref, not separate per-day refs.
This code change does not activate paid execution or initialize any ledger.

## Public configuration migration

Schema 1 remains readable for historical evidence and free preparation. It is
ineligible for paid execution. Schema 2 preserves every existing field and adds
exactly this public, non-secret field (replace placeholders only after audit):

```json
{
  "daily_budget": {
    "currency": "USD",
    "amount": "1000",
    "timezone": "Asia/Shanghai",
    "anchor": {
      "ref": "refs/heads/skill-eval-budget/<repository_id>/daily",
      "genesis_commit": "<audited_genesis_commit>",
      "checkpoint_commit": "<independent_checkpoint_commit>"
    }
  }
}
```

The checked-in schema-1 configuration is deliberately unchanged. Missing daily
configuration/genesis, unknown obligations, corrupt history, expired rates or
unavailable live identity block paid execution, never imply zero spend. Free
planning and retained evidence do not require a new paid grant.

An authorized rollout must first quiesce all older paid writers and reconcile
**all** historical charges, existing PR reservations and uncertain/in-flight
work, including historical PR 159 and 160 run records. Preserve their existing
PR anchors, history and evidence byte-for-byte; do not reset/rebase their budgets.
Import conservative historical daily intervals and outstanding upper bounds into
an explicitly audited global genesis. Missing provider bills are not proof of
zero cost. Unknown upper exposure prevents activation. Pin the audited genesis
and independent checkpoint in reviewed configuration; no initializer, zero
bootstrap, ref write or config activation is supplied here.

## Durable admission and failure boundaries

The order is: verify both histories; commit a **new** daily reservation; commit a
**new** PR reservation; obtain a one-shot daily claim on the admission day; obtain
a one-shot PR claim; recheck all live authority; launch once in this process.
Any duplicate, conflict, lost response or crash stops that invocation. Partial
admission burns capacity. Observing an earlier committed reservation/claim never
recovers a launch grant. A genuinely new attempt needs a new full frozen binding
and new reservations; a workflow rerun or label toggle cannot reset old ledgers.

Before launch and every provider request, the existing ephemeral broker invokes
the controller to re-read current policy/label/configuration and both exact
claimed bindings, and verify the global ledger is not quarantined. The trusted
wall clock is sampled for admission, again for daily claim, and after live reads
for each grant. A changed Shanghai day denies all subsequent requests; no
cross-midnight continuation or automatic day rollover exists. A request already
in flight cannot be recalled. Its full unresolved bound remains counted on the
next day, so midnight does not free its capacity.

The existing trusted provider client enforces the frozen request count, payload
and output bounds and requires a fresh broker grant immediately before every
HTTP request; transport retries do not get a replay grant. The reservation covers
all calls using the full verified model-context ceiling, highest applicable
input/cache rate, maximum output and request fees, rounded upward. If those
upper-bound assumptions cannot be established, do not run.

## Conservative terminal policy and quarantine

The controller performs **no automatic terminal settlement or refunds**, even
when its worker returns successfully. Worker failure, cancellation, crashes and
missing/partial actual usage retain the entire PR and global bound. Unresolved
global reservations remain charged on every later day; exhaustion stops future
work instead of resetting at midnight. This deliberately trades availability for
safety in the initial bounded pilot.

A future settlement path must prove provider work and every retry are terminal,
sample a fresh trusted closing day **after** that proof, and retain unknown-cost
bounds. Never use a cached admission day as a settlement day. Do not interpret a
successful subprocess return or artifact's claimed usage as that proof.

Evidence of an exceeded upper bound or unknowable exposure requires persistent
global quarantine before further activity; ordinary unavailable actual billing
under a still-valid conservative bound is different. Quarantine is monotonic:
no automatic clearing/reset. The controller checks the persisted quarantine, but
does not itself ingest provider billing or invent evidence of terminal usage.
Activation therefore still requires the reviewed pricing/bounds, audited
history, compatible storage permissions and a trusted operational path to
record any externally discovered over-bound exposure. Git administrator rollback
limitations remain as documented in [the accounting core](skill-eval-budget-core.md).

## Offline validation

```sh
PYTHONPATH=src:. python -m unittest tests.test_skill_eval_daily_budget tests.test_skill_eval_auto_daily -v
```

The controller matrix covers all four durable admission writes under conflicts,
uncertain successful writes and crashes; replay after partial progress; rollover
before daily claim, after both claims and between provider requests; claim
revocation and worker failure after launch. Tests use only local in-memory state
and fake credentials, not provider requests, GitHub writes or paid experiments.
Full pytest validation requires the development dependencies; these unit tests
do not establish provider billing or evaluation efficacy.
