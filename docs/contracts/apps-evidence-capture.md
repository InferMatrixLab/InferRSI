# Apps evidence capture assembly

`inferrsi.apps.api.EvidenceCapture` is defined in
`apps/handoff/evidence_capture.py`. It is the thin host adapter accepted in
[#565](https://github.com/InferMatrixLab/InferRSI/issues/565#issuecomment-7064458592).
It imports no Benchmark business module, performs no grading and writes no
archive or RunStore. It passes the injected projector's result through unchanged.

## Host configuration

After reading the fixed preparation and protocol through their existing archive
ports, the host constructs the supported B projector and configures role mapping:

```python
from inferrsi.apps.api import EvidenceCapture
from inferrsi.benchmark.proofs import ProofProjector
from inferrsi.harness.api import Harness

projector = ProofProjector(prepared, protocol_bytes)
capture = EvidenceCapture(
    projector.project,
    candidate_role=prepared["candidate_contract"]["input_role"],
    report_role=prepared["recipe"]["outputs"][0]["role"],
)
harness = Harness(store, target, artifact_reader=reader, evidence_capture=capture)
```

The supported frozen P1 recipe has exactly one report output. Roles come from
validated frozen metadata; Apps defines no task name, report schema, predicate,
sampler or producer policy. The normal Apps execute port submits its saved
request to `harness.execute`. Existing callers can keep their configured ports.

## Data and failure boundaries

The callback snapshots H facts, selects this attempt's configured candidate
input, and reads only through the H capability. In finalizing it also selects an
available configured report belonging to this attempt and its enclosing step.
An absent family is passed as explicit `None`; multiple sources are refused as
IdentityMismatch instead of choosing the first or last. A configured candidate
role that differs from actual facts is also refused.

Opened streams are closed, including failed reads. Reads are bounded to size+1
and bytes are independently checked against fixed Ref size/hash. Capability
refusals keep their original portable code for H's lifecycle handling. Unknown
host/type errors propagate; they do not become fabricated report absence.

The injected B projector receives only supplied bytes and a defensive context
snapshot. It owns proof construction and independent family outcomes. H validates
the returned drafts, retains raw/derived bytes and seals their actual provenance
before its record commit. Apps never adds a check to a committed record.

Standard manifest/result publication, assessment and view/trace all retain the
same committed RecordRef. Output publication failure preserves that reference;
replay uses the original attempt and skips capture. These mechanics tests do not
accept a real task/grader/sampler specification or missing measurement evidence.
