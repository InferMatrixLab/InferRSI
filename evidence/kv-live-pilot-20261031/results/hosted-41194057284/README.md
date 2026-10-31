# Single additional live attempt: HTTP 403, comparison incomplete

[Run 41194057284, attempt 1](https://github.com/InferMatrixLab/InferRSI/actions/runs/41194057284)
finished on 2026-10-31 at 10:48:38 UTC. The workflow completed its control and
retention steps; **both experimental arm grades are INCONCLUSIVE**. This is the
single additional pair, not a successful A2/A3 comparison or an efficacy result.

- Same-host preflight reports `prepared`; the pair's durable admission is `granted`.
- A2 consumed one slot. The retained closed diagnostic records one transport
  invocation and `http_403`, then stops. Usage/completion and actual billing remain
  unknown. The adapter observed HTTP 403 but discarded the error body: the issuer
  and account, gateway/WAF or model-entitlement cause cannot be determined here.
- Only unchanged baseline revision 0 and its receipt exist. No edited/final
  candidate or tool feedback was produced; A3 never started. Both grades are
  `INCONCLUSIVE: missing_or_invalid_artifact`. Missing trace/timing observations
  are not zero-duration measurements or passes.
- The first attempt's original evidence remains unchanged; its omitted cause
  cannot be retroactively identified from this second attempt's diagnostic.

## Retained cost and disposition

`cost.json` binds immutable PR/day ledger commits and the independent anchored
read-only audit. Both full $162.72 claims remain retained: **PR275/pilot $325.44**,
**daily $816.79** including older $491.35 carryover. These are liability ceilings,
not observed bills. Actual costs remain unknown; no refund, reset or third attempt
follows from remaining cap space. Other PRs retain their $200 default; the scoped
PR275 cap is $350, and daily/pilot ceilings are $1,000.

The next useful diagnostic is an existing service/account-side rejection and
billing record for 2026-10-31 10:46–10:48 UTC (Shanghai 18:46–18:48), obtained by
an authorized account operator without a test request. This archive does not
establish which service setting, if any, should change; no third call, credential
change or new account is implied. The original first-run window remains separate.

## Exact originals and scope

Executed [main source](https://github.com/InferMatrixLab/InferRSI/commit/ae0d32218949fd6b906c3e7819ba0d830955c196)
and the captured [public freeze](https://github.com/InferMatrixLab/InferRSI/issues/248#issuecomment-6542223785)
are bound in `manifest.json`, including the original 64-file dependency map.
The freeze's 12:00 UTC expiry and 11:38 latest admission were not extended.

`execute-artifact.zip` (artifact 13039479838) and `grade-artifact.zip`
(artifact 13040225189) preserve the two exact original downloaded ZIPs.
`execute/` and `grade/` contain their nine exact members. The manifest records
file sizes, hashes, source/run identity, missing observations and diagnostic
limits. File-byte hashes and canonical plan fingerprints are distinct domains.

The fixed package contains bounded public task/authorization/preflight/diagnostic
projections, not raw provider responses, arbitrary worker/environment logs,
private chat or credentials. Publication is limited to the independently checked
exact files; it is not a general-purpose redaction guarantee. Candidate/model
execution was not repeated to reconstruct missing first observations.

Archiving changes evidence data only, not source, main, frozen inputs or ledgers.
No performance, knowledge-efficacy, vLLM-conformance or service claim is made.
Agent-assisted provenance: Codex / gpt-6-astra [effort=xhigh], evidence retention;
independent byte/privacy review by the separate actor-isolation reviewer.
