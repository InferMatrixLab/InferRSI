# Persisting an incident quarantine

This is a trusted operator/controller stop operation, not paid admission or a
billing ingestion interface. Run only from the current reviewed implementation
with its trusted schema-2 daily anchor configuration and the existing GitHub
credential injected by the authorized environment:

```sh
PYTHONPATH=src:. python -m tools.skill_eval_quarantine \
  --repository <owner/repository> \
  --evidence https://github.com/<owner>/<repository>/issues/<incident-number>
```

The evidence must be a sanitized public GitHub issue/PR reference, optionally a
comment/review permalink. Do not pass raw bills, provider errors, credentials or
private payloads. No provider credential is needed or read. No model, dispatch,
ledger initialization, reset, settlement, clearing, or repository-setting API
is called. This CLI itself performs real Git ledger writes when invoked against
a live client; tests and delivery of its source do not authorize invocation.

Use this operation when a trusted incident establishes exposure above the
reserved upper bound or makes that upper bound unknowable. A missing actual
bill under a still-valid conservative bound does not by itself establish either.
No expiry/pricing/label check can prevent this safety-only stop: it loads only
the trusted repository identity and daily anchor from root configuration, then
the Git adapter verifies repository identity and full pinned ledger lineage.

The writer retries at most three verified read/compare-and-swap cycles, with a
final read-only verification. A concurrent admission is preserved and the stop
is recomputed against the newer history. An unknown/lost write receipt is
reconciled **only into a verified stop**, never into a launch grant. Existing
quarantine is sufficient; repeated calls preserve its first evidence and do not
rewrite history. Subsequent admission and per-request checks reject quarantine.
Already-issued or in-flight provider requests cannot be recalled by this write.

Exit zero and `{"state":"quarantine_verified",...}` mean fresh authenticated
readback established the durable stop. Merely receiving a successful CAS is not
enough. Nonzero exit / `Global quarantine NOT verified` means the operation is
incomplete: keep paid execution stopped, resolve storage/identity/anchor access,
and rerun this monotonic stop until verified. Do not restart paid work because
retries were exhausted, and do not change/reset anchors to bypass failure.
If storage is inaccessible, this CLI cannot claim it stopped other processes;
that requires the separately authorized operational response.

There is no unquarantine command. Resuming after an incident requires separately
reviewed reconciliation; deleting a ledger/ref or lowering a checkpoint is not
reconciliation. This operation does not prove provider billing, undo spend or
provide administrator-resistant rollback protection.

Offline tests:

```sh
PYTHONPATH=src:. python -m unittest tests.test_skill_eval_quarantine -v
```

They cover concurrent admission, lost successful write receipt, repeat-stop
idempotence, conflict exhaustion, failed readback, expired pricing, rejection of
raw/private evidence inputs, and nonzero CLI failure without a success report.
