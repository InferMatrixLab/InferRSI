# Production P1 offline assessment

`inferrsi.benchmark.assessment` implements the accepted D023 / `t108-v4`
family: `p1-fixture@1`, `p1-rules@1`, operation `evaluate`, scope `p1`.
It consumes the same frozen preparation as
[production prepare](production-prepare.md). The public ports are
`assess(prepared, evidence, *, artifacts)`, `encode`, `decode`, and
`validate_assessment`. `AssessmentService(clock=...)` supports reproducible
assessment timestamps; its default clock is real UTC.

```python
from inferrsi.apps.api import assess as apps_assess
from inferrsi.benchmark.assessment import assess, encode, validate_assessment

output = apps_assess(
    saved_assess_request, workspace=workspace, storage_config=storage_config,
    assess_benchmark=assess, encode_assessment=encode,
    validate_assessment=validate_assessment,
)
```

Apps reads one fixed record and its preparation, checks the primary key against
the frozen protocol, and supplies its read-only artifact capability. Benchmark
does not import Apps, Harness or Knowledge, register a worker, execute a process,
use a network/device, archive results, or rewrite execution facts. Its encoder,
decoder and result validator perform no artifact reads.

## Binding and byte authority

The port snapshots the JSON inputs and checks the complete canonical record
against its RecordRef hash, size, attempt and revision. It checks task,
operation, scope, semantic `prepared_id` and `protocol_digest`. It does not
compare archived reference locations as identities. The actual frozen protocol
bytes are read and validated with the prepare port's pure validator; unsupported
task, grader or claim-rule revisions are explicitly refused.

Every opened artifact is independently checked against its declared size and
SHA-256. The capability may supply bytes or a binary stream; assessment closes
streams it opens. Portable `UnsafeArtifactPath`, `ArtifactUnavailable` and
`ArtifactIntegrityError` exceptions are recognized by their exact `code`, without
depending on another module's exception class. An affected proof becomes a
claim-level evidence gap. Unknown host programming exceptions propagate.
Failure to obtain the protocol itself is a port error: missing rules cannot be
replaced by a guessed assessment.

An input's actual hash is accepted only with matching retained bytes and a fixed
capture fact. Proof-declared candidate IDs/hashes do not authenticate themselves.
Check identity, revision, subject, phase, attempt, operation, scope and artifact
schema must match a frozen requirement. Producer kind/domain must be allowed;
the domain must match the actual target binding. Worker and sample evidence must
also match the observed runtime entry/revision/code pin and a started step bound
to that input. Caller assertions cannot substitute for those facts.

## Frozen P1 decisions

- F and C consume their own trustworthy format/grader proofs. A complete passed
  proof yields PASS, a matching failed proof yields FAIL, and missing/invalid
  evidence yields INCONCLUSIVE. Another claim's missing evidence does not erase
  an independently supported result.
- M validates four positive Decimal samples in A1/B1/B2/A2 order with their
  frozen round, role and `ms` unit. It also needs a completed successful process,
  known closed steps, confirmed process cleanup, confirmed acquired-lease
  releases and a matching cleanup proof. Missing terminal facts remain
  INCONCLUSIVE; there is no independent-error exception for this terminal claim.
- Contradictory trustworthy proofs are aggregated into one INCONCLUSIVE claim
  with a conflict reason, including conflicting sample values. No first/last
  winner or duplicate claim key is emitted. P1 eligibility is ineligible for a
  failed claim/conflict, unknown for incomplete evidence, and eligible only when
  all three frozen conditions pass. It is not an overall verdict.
- This protocol freezes no metric definitions or assessment comparison target,
  so metrics/comparison arrays remain empty. M is measurement validity, not a
  claim of a service gain.

Raw proof bytes retain their original hash. Their JSON need not use the DTO's
canonical whitespace: parsing still rejects duplicate keys, floating/nonfinite
numeric tokens, invalid Unicode and invalid P1 fields. New EvaluationResult
bytes follow `inferrsi-json-v1`. Its semantic ID excludes only the declared
clock/self-ID fields and schema-typed ArtifactRef locations, including nested
candidate references. All other supporting content participates.

## Acceptance boundary

The Apps primary-key order, missing-result-key error and archive-failure behavior
remain Apps responsibilities. Cross-tests use real production prepare/assess
ports, Apps archive/read/publish code and retained software-test record/proof
fixtures. They cover T35/T39/V21–V23, including isolated-process identity and
fixed-clock bytes. They do not claim that the production Harness evaluation
worker has run. That target and T37/T40 belong to #429; joint production CPU
acceptance remains necessary before #371 can be completed.
