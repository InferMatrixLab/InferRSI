# Issue 215: bounded PR159/160 deployment record

This is an owner-authorized, issue-scoped deployment configuration, not a portable
provider default or a claim that live execution passed. Governing issue:
[#215](https://github.com/InferMatrixLab/InferRSI/issues/215).
Only the two audited PR anchors in `tools/skill_eval_auto_config.json` are enabled;
other PRs have no usable ledger anchor. The sole authorized label operator is the
public repository owner `Dong1017`, using `skill-eval:execute`. Current repository
write/maintain/admin permission, open non-draft PR state, current main/head,
matching plan/configuration and a durable claim remain mandatory runtime checks.

## Audit and price provenance

[Reviewed evidence](https://github.com/InferMatrixLab/InferRSI/issues/215#issuecomment-6467531341)
contains the retained-workflow historical-spend reconciliation and the fresh
public price observation. Its machine-readable companion SHA256 is
`0cf72dd857d642ab9f6e810c100bb8d661cbb4c28568455dc49eca6c58cea501`.
The audited carry-forward is conservatively rounded upward: PR159 **$0.68**;
PR160 **$63.53**, including the entire failed-run reservation. It is not an exact
invoice or a universal claim about deleted/outside executions. Each genesis has
only `ledger.json`, revision zero and no entries; genesis/checkpoint identities
are pinned in the deployment file. Never initialize a replacement or reset spend.

Observed 2026-10-28 10:53:48 UTC at [public pricing](https://yibuapi.com/pricing),
with [public API](https://yibuapi.com/api/pricing) pricing version
`a42d372ccf0b5dd13ecf71203521f9d2`: exact `claude-opus-5-5`, default group,
USD per million input **8**, output **40**, cache-read **0.4**, cache-write **10**.
The account's default group is separately owner-confirmed, not inferred from the
logged-out public page. `request_fee=0` is the reviewed token-tariff inference
(`quota_type=0`, `model_price=0`), not a contractual no-surcharge guarantee.

Both price and authorization expire **2026-10-29 10:53:48 UTC** (1793271228),
24 hours after observation. This is an explicit conservative **operational
freshness deadline**, not a vendor quote-validity promise. Expiry blocks new
requests; refresh requires new reviewed evidence and configuration, not silently
extending the timestamp. No provider/model/Codex fallback is authorized.

## Hard cost bound

The existing Messages client uses its known 1,000,000-token context ceiling;
reservation charges every input token at the largest input/cache rate ($10/M).
Six requests per trial, 4,096 output tokens per request and a complete two-trial
pair give:

- Raw request bound: `(1,000,000 × 10 + 4,096 × 40) / 1,000,000 = $10.16384`.
- Upward cent rounding: **$10.17/request**, **12 requests**, **$122.04/pair**.
- Cumulative $200/PR leaves **$199.32 / $136.47** before this round, and
  **$77.28 / $14.43** after reserving one pair each.
- Only these two PRs can reserve. Their combined remaining capacity is
  **$335.79**, strictly below this round's $400 total ceiling; no separate global
  ledger or additional authorized PR is implied. One pair each reserves $244.08.
- Reservations never refund on success, cancellation, uncertainty or head change.
  A second full pair on either PR is rejected even with a different plan/run.

Request bytes (131072), read bytes (32768), tool calls (12), and the soft
`token_stop_new_trials=200000` stop match successful PR160
[run 40499987048](https://github.com/InferMatrixLab/InferRSI/actions/runs/40499987048),
plan artifact 12731459808, plan SHA256
`fc8b6978e2f176e5c1999fcd0fab34d649096ebf1226d87196d4677c36bba0ab`.
The soft stop is not a spending guarantee; the independent hard bound above is.
The historical expired price record is not reused.

The deployment retains the existing `SKILL_EVAL_YIBUAPI_KEY` runtime injection;
no secret value is read or stored here. Tests use offline mocks, not provider
requests. Config presence changes real plan preparation, so synthetic-repository
CLI tests explicitly isolate their own absent configuration rather than bypassing
production guards.

## Activation prerequisites and stopping

Deployment is not complete merely because this file exists. The trusted main
controller, all blocking review fixes, authenticated Git-data non-force CAS,
audited anchor readback and exact-head checks must pass before a label is added
or any paid request is launched. This local preparation performs none of those
external mutations, does not dispatch a run, and does not claim token/storage
permissions have been live-tested. Keep existing protection/settings unchanged.
Remove the label to revoke authorization before the next request; never delete
or roll back a ledger to recover capacity. Retain all ambiguous reservations.
