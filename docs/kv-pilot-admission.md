# One-pair KV pilot admission seam (offline)

`tools/kv_pilot_admission.py` is a narrow controller interface for the accepted
exploratory KV editing feasibility envelope: **one A2/A3 paired block**, at most
**8 provider attempts per arm / 16 total**, with a full-context worst-case
**USD 10.17 per request / USD 162.72 total**. These are spending bounds, not
scientific acceptance thresholds. One pair can establish implementation/execution
feasibility only; it cannot establish efficacy. No experiment is run by this module.

The module introduces no CLI, default transport, credential read, workflow launch,
ledger initializer, new ledger schema or automatic retry. Tests use in-memory
stores and injected clocks/launch callbacks only. A real launcher remains a
separate reviewed integration, not authority implied by this offline seam.

## Trust and immutable identity

Only reviewed controller/root configuration can create `PilotPolicy`. Never load
it, its stores/anchors, or `check_current` from candidate code, PR artifacts,
author-written requests, mutable labels or model output. `check_current(policy)`
must return exactly `True` only after independently verifying owner authorization,
repository/legitimate execution PR and exact head, frozen source revision, visible
input/K/verifier hashes, model/provider/pricing identity, and qualified isolation.
The plan SHA-256 must bind those accepted inputs and the single-pair sample plan;
the per-arm actor hashes bind the complete editing protocol/manifests. The source
author model/effort provenance remains distinct from the evaluated provider model.

`provider_json` is immutable canonical JSON and uses the separate editing protocol,
not the pre-existing read/submit agent. Existing `reservation()` recomputes the
full 1,000,000-token ceiling and 4,096-output bound; USD amounts are converted
without floating-point arithmetic. Plan and pricing expiration are enforced both
before admission and before every send. A frozen root-policy change must cause
`check_current` to deny; this API is not a way for candidate inputs to authorize
such a change.

The **existing global daily ledger entry is the durable campaign-binding record**:

- `Binding.run_id`: fixed `kv-reclamation-one-pair-v1:<campaign-id>` identity.
- `Binding.plan_digest`: SHA-256 of the complete immutable policy, including
  execution ID, repository/PR, exact head/source/plan, actors and pricing.
- `Binding.worst_case`: the entire USD 162.72 envelope.

Admission rejects *any* existing entry in this one-pilot namespace, not only an
identical digest. Thus changing the campaign ID, digest, run/attempt, PR, date or
expiry cannot create a new allowance. The unchanged global CAS arbitrates racing
first admissions. A later legitimate experiment would need separately reviewed
scope and code; this seam deliberately offers no reset, takeover or resume path.

## Durable ordering and accounting

`admit(...)` reads both existing verified histories, checks their identities and
requires the selected PR's retained global obligations to equal its cumulative PR
charge. An incomplete old PR tip cannot erase global imported charges. It computes
both cap checks before writing, then performs exactly:

```text
full daily reservation CAS → full PR reservation CAS
       → daily one-shot claim → PR one-shot claim
       → fresh verification of BOTH claims, live policy, price and Shanghai day
       → process-local supervisor session
```

All earlier audited charges, reservations, retries and unresolved obligations must
already be present in verified history. Absent/corrupt/unknown history blocks;
there is no missing-file-zero fallback. One immutable campaign on one PR subject
to the USD 200 lifetime cap is already strictly below the USD 1,000 pilot-task
ceiling; this does not introduce a global lifetime cap. Unrelated settled past-day
campaigns are not new pilot spending. The USD 1,000 Shanghai-day cap still includes
all charges for that day and unresolved historical carryover. No accounting
meaning is inferred from a successful test or claimed actual usage.

The synthetic regression fixture preserves USD 491.35 of unresolved historical
obligations, producing USD 654.07 retained after the complete reservation, USD
345.93 remaining that day, and USD 37.28 remaining on a fresh execution PR. The
new pilot itself moves from USD 0 reserved to USD 162.72 reserved, leaving USD
837.28 of its USD 1,000 task ceiling; the earlier USD 491.35 is global daily
carryover, not new pilot spend. These are fixture/audit amounts, **not a current
live ledger readback or invoice**.
Current verified refs/checkpoints and refreshed pricing remain launch prerequisites.

A stale CAS, partial reservation, lost response or crash never grants execution.
Unknown claim outcomes cannot be reconciled into a new grant. A caller receiving
an uncertain first daily write must stop rather than blindly retry; an absent
observation is not proof that the old write cannot arrive. The durable no-relaunch
guarantee applies once a campaign entry persists, with CAS preventing competing
first admissions from both winning. Reservations and
claims stay in the existing ledgers after success, failure, cancellation or process
death; there is no refund or terminal-settlement writer here. Shanghai rollover
stops new requests, even if admitted earlier. Outstanding entries carry over;
midnight does not refund or relaunch the campaign.

## Trusted supervisor interface

`run_admitted(..., launch=callback)` invokes a trusted callback only after both
claims and closes the session in `finally`. For finer integration, `admit(...)`
returns the same process-local, non-pickleable session. Do not expose this object,
its stores, policy checker or completion method to model/candidate code.

1. `start_arm(arm, absolute_deadline)` immediately **before disclosure/launch**.
   The deadline is at most 600 seconds away, cannot be renewed, and arms cannot
   overlap. The qualified external supervisor must enforce that same absolute
   deadline; in-process checks alone cannot terminate blocked code.
2. `authorize(grant, absolute_deadline) -> True` immediately before **one send**.
   The exact grant shape matches `anthropic_edit_agent.RequestSlots`: plan digest,
   execution ID, arm, slot, payload SHA-256, actor SHA-256 and per-request bound.
   Admission has independent counters, burns before live checks, verifies both
   durable claims and day/price after reads, and allows no ninth slot or borrowing
   from the other arm. The worker's local counters are an additional guard only.
3. `complete(same_grant, raw_usage)` after the trusted transport/worker has observed
   the response for that exact request. Raw usage requires all four integer fields:
   `input_tokens`, `output_tokens`, `cache_read_input_tokens`,
   `cache_creation_input_tokens`. All input classes count toward the 1M bound.
   Candidate-authored JSON, a narrative or unverified trace is not usage evidence.
4. `finish_arm(arm)` only when no request remains unresolved. Preserve failures
   and missing artifacts in the experiment evidence rather than discarding them.
5. `close()` irreversibly stops this process-local session. No new process can
   reacquire the already consumed durable claims.

There may be only one pending request across both arms. A lost grant/reply,
transport failure, unknown/malformed/over-bound usage, mismatched completion,
revoked authorization or inconsistent claims stops both arms; failed/ambiguous
work cannot replenish slots. The full cost stays reserved. Report and reconcile
any observed over-bound exposure through the existing trusted quarantine/accounting
process before other paid work; this module does not claim to settle provider bills.

`context(arm)` supplies an exact frozen context for the unchanged existing
`request_guard.authorization_broker`. No new network protocol is introduced.
The existing broker is a **trusted-client gate, not a candidate sandbox**. Real
wiring must keep provider credentials and GitHub authority outside candidate/test
execution, independently enforce exactly one send per grant/no transport retries,
and relay usage from trusted observation before the next authorization. Neither
this seam nor a green fake test proves that real isolation or billing is qualified.

## Verification

Run offline:

```sh
pytest tests/test_kv_pilot_admission.py tests/test_skill_eval_budget.py \
  tests/test_skill_eval_daily_budget.py tests/test_skill_eval_budget_git.py \
  tests/test_request_guard.py tests/test_anthropic_edit_agent.py tests/test_anthropic_agent.py
ruff check tools/kv_pilot_admission.py tests/test_kv_pilot_admission.py
```

Coverage includes stale CAS, partial/unknown writes, death after every durable
step, duplicate claims and relaunch, new digest/campaign/PR/attempt, cap overflow,
Shanghai carryover/rollover, pricing expiry, final exact-claim verification,
revocation, unknown/mismatched usage across arms, frozen deadlines and the hard
8-per-arm/16-total limit. These are controller regressions, not paid-model results.
