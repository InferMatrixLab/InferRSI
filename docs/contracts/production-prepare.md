# Production P1 preparation

`inferrsi.benchmark.preparation.PreparationService.prepare` implements the
Benchmark preparation port for the accepted D023 / `t108-v4` task family:
`p1-fixture@1`, `p1-rules@1`, operation `evaluate`, scope `p1`.

The trusted host configures a **Benchmark-owned frozen ProtocolV1** and a
read-only resource capability. Neither is supplied inside PrepareRequest.
The task configuration includes an explicit resource role for the actual worker
code bytes. Its ArtifactRef digest must equal `worker_recipe.code_sha256`.
Preparation verifies the exact supplied bytes; it never treats the historical
documentation worker digest as an available executable.

```python
from inferrsi.benchmark.preparation import (
    PreparationService, encode, decode, validate_prepared,
)

service = PreparationService(
    frozen_protocol, resources=open_fixed_resource, worker_role="worker-code",
)
prepared, protocol_bytes, open_resource = service.prepare(request)
```

`open_fixed_resource(role)` is a host-supplied capability returning bytes or a
fresh binary stream for an authorized role. The caller owns closing each returned
stream. It does not interpret a request-provided location as a filesystem path.
The frozen resource metadata is verified during preparation. The returned
`open_resource` accepts only roles in that preparation's closure and reopens the
resource through the same capability. It does not write or archive bytes.
Provisional source locations may alias: byte authority is the configured role,
not a lookup or de-duplication by that location. Apps assigns a distinct final
archive path to each role and verifies the bytes against that role's metadata.

The first task keeps the P1 candidate, claims, evidence rules, worker recipe
shape and sampling conditions. PrepareRequest can bind its candidate expectation,
P1 task parameters, budget references and additional resource pins. A supplied
pin cannot replace a frozen role's hash, format or required use. The first task
accepts an empty `comparison_conditions`: comparison conditions are configured
in the frozen task definition, rather than silently accepting unknown overrides.
Unknown task, grader, worker or claim-rule revisions are refused.

The protocol contains its declared resources and optional baseline/reference/
quality-reference resources. PreparedEvaluation carries the complete closure,
sorted by unique role. Duplicate roles across any of these positions are refused.

## Identity and pure codecs

`encode(prepared)`, `decode(bytes)` and `validate_prepared(prepared,
protocol_bytes)` perform no artifact reads, worker imports, execution or writes.
They preserve the canonical `inferrsi-json-v1` byte contract.

- `prepared_id` excludes its own value, `created_at`, `display_notes`, and
  locations in its schema-declared outer ArtifactRefs. Moving both the outer
  protocol and outer resource references preserves this ID.
- `protocol_digest` excludes protocol display notes and locations only in the
  declared resource references, including baseline/reference/quality-reference.
  It preserves an arbitrary ref-shaped value inside Parameters.
- Moving a reference **inside** the protocol changes the protocol's canonical
  bytes and byte digest. The changed digest changes `prepared_id`, even when
  `protocol_digest` remains equal. Other semantic changes affect both identities.

## Apps boundary and failures

Inject the bound port and pure functions into the existing Apps API:

```python
from inferrsi.apps.api import prepare

output = prepare(
    {"schema_version": 1, "request": request},
    workspace=workspace, storage_config=storage_config,
    prepare_benchmark=service.prepare,
    encode_prepared=encode, validate_prepared=validate_prepared,
)
```

Apps assigns its final outer locations, invokes the Benchmark pure codecs,
verifies bytes independently, then commits the full closure before publishing
a PreparedRef. Benchmark imports neither Apps nor Harness.

The prepare port returns a portable PublicError wire object for a declared
rejection. Missing resources produce `ArtifactUnavailable` at `prepare`;
incorrect retained metadata produces `ArtifactIntegrityError`. No preparation
is archived by Benchmark. If the resource disappears after preparation, the
Apps archive reports `ArtifactUnavailable` at `prepared_archive`; changed bytes
are rejected by its independent integrity verifier. Neither case publishes a
PreparedRef or a partial prepared closure.

This port does not register the configured worker with a Harness target or
execute/assess it. The H evaluation-mode path and production offline assessor
remain separate deliveries under #429 and #434. The packaged engineering-task
registry is unchanged. A host must supply the reviewed P1 task definition and
actual worker/resource capability; no default fixture backend is silently
selected. Ordinary CPU regressions do not establish a model/service gain.
