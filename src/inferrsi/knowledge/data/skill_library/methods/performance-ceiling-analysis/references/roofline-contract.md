# Pure Roofline helper contract

The bundled [helper](../scripts/roofline.py) implements the existing L1 formulas
and [bound discipline](papers-20261015/knowledge/bounds-predictions-and-decisions.md).
It is InferRSI-authored software, not copied upstream code. The procedure remains
candidate / empirical_validation=not_run; CPU arithmetic checks do not establish
campaign efficacy, model qualification or achievable acceleration.

## Calling and scope

Load the script as a Python module and call `analyze(workload, hardware)`. It uses
only the standard library, returns a new JSON-compatible mapping and neither
mutates the inputs nor reads/writes files, runs commands, discovers devices or
accesses the network. Loading/persisting attachments is the caller's separate
responsibility. This is an internal skill helper, not a new CLI or public API.

The first slice accepts one device, one homogeneous floating-point operation
class and one traffic tier. It does not walk a model, estimate work from shapes,
sum devices, pool capacity, model communication or perform Amdahl/E2E analysis.
The counts describe the stated algorithm: a different algorithm or cache policy
can change both work and traffic. Logical tensor sizes are not automatically
mandatory transfers across a particular memory tier.

## Input fields

Both arguments are JSON objects. Unknown facts are omitted or null, with a
`missing_reason` where available. Extra metadata is retained without interpreting
or verifying it. Units and condition strings are exact; there is no implicit
conversion, normalization or hardware-name lookup.

| Object | Required fields |
| --- | --- |
| `workload` | Nonempty `workload_id`, `shape`, `boundary`, `hardware_id`, `resource_scope`; `operation`, `work`, `traffic`, nonempty `assumptions` list |
| `hardware` | Matching `hardware_id` and logical `resource_scope`; integer `device_count=1`; `operation`, `peak_compute`, `bandwidth`, nonempty `assumptions` list |
| Each `operation` | `dtype`, `accumulator_dtype`, `op_class`, `sparsity`, `fma_flops`; all five must match |
| `work` / `traffic` | Finite positive `value`, exact `unit` (`FLOP` / `byte`), `source`; traffic also names a `tier` |
| `peak_compute` / `bandwidth` | Finite positive `value`, exact `unit` (`FLOP/s` / `byte/s`), `source`; bandwidth names the same `tier` |
| Each `source` | Nonempty `kind`, `locator`; nonempty `revision` or lowercase 64-hex `sha256`; caller-supplied `recorded_at` text, or `time_unknown_reason` |

Supported dtype spellings are `float64`, `float32`, `tf32`, `float16`, `bfloat16`,
`float8_e4m3fn`, `float8_e5m2`. This list does not certify hardware support.
`op_class` is exactly one of `scalar`, `vector`, `matrix`. `sparsity` is an
explicit condition string such as `dense` or `2:4`; no speed multiplier follows
from it. `fma_flops` is 1 or 2, matching the supplied count/rate convention; the
helper never converts between conventions.

Work/traffic source kinds are `derived`, `measured` or `synthetic`. Both hardware
rates must use `rated` sources, or both must be explicitly `synthetic` fixtures.
The first helper retains empirical (`measured`) rates and probes in its inputs
but returns insufficient evidence for their use as an L1 rated bound. A measured
component envelope is not a universal physical limit. A source label does not
verify the linked document: callers own source authenticity, applicability,
clock/power/allocation conditions and whether the work/traffic counts are valid.
Source timestamps are retained text, not a freshness or qualification decision.

## Output and failure semantics

`analysis_status` is `COMPUTED` or `INSUFFICIENT_EVIDENCE`, never a campaign
verdict. For compatible, sourced inputs:

- `arithmetic_intensity_flop_per_byte = F/T`.
- `conditional_roof_flop_per_s = min(P, (F/T)*B)`.
- `ridge_flop_per_byte = P/B`.
- `conditional_runtime_floor_s = max(F/P, T/B)`, not their sum.
- `analytical_limiting_factor` is `memory`, `compute` or exact-numeric `balanced`.

The floor is conditional on the supplied counts/rated rates; it excludes queueing,
launch, synchronization and communication. No observed baseline, attainable
utilization, speedup, SLO or goal acceptance is derived. `evidence_basis` preserves
the common hardware source kind, or null for mixed kinds; inspect status and
unknowns before using any number.

Missing sources/values, unsupported scope and incompatible conditions yield
explicit `unknowns` and null dependent outputs. AI may remain available when
only hardware evidence is missing. `inputs` retains independent copies of all
source facts/metadata; `assumptions` concatenates caller assumptions and `limits`
records interpretation boundaries. Malformed types, nonfinite numbers, booleans
in numeric fields, nonpositive numbers and derived overflow/underflow raise
`ValueError`. Zero-work or zero-traffic cases are outside this first slice; zero
never substitutes for unknown. Nothing executes or grants authorization.

## Worked caller-controlled attachment

[roofline-example.json](roofline-example.json) contains entirely synthetic facts,
not device specifications. Calling `analyze(example["workload"], example["hardware"])`
gives AI 6 FLOP/byte, roof 60 FLOP/s, ridge 10 FLOP/byte, conditional floor 10 s,
`memory` and `evidence_basis=synthetic`. These are dimensional test numbers.

A caller may retain the input and returned mapping at
`plan/attachments/<analysis-id>.json` before search, or in a separately versioned
attachment for a permitted row-4 revision. For example, the following caller
explicitly performs the file operations; replace the placeholders and choose a
new attachment path rather than overwriting frozen evidence:

```python
import json
import runpy
from pathlib import Path

owner = Path("<skill-root>")
helper = runpy.run_path(str(owner / "scripts/roofline.py"))
analyze = helper["analyze"]
example = json.loads((owner / "references/roofline-example.json").read_text(encoding="utf-8"))
attachment = {
    "helper_revision": "<knowledge-bundle-revision-or-helper-code-sha256>",
    "analysis": analyze(**example),
}
target = Path("<campaign-root>") / "plan/attachments/<analysis-id>.json"
target.parent.mkdir(parents=True, exist_ok=True)
with target.open("x", encoding="utf-8") as stream:
    stream.write(json.dumps(attachment, indent=2, allow_nan=False) + "\n")
```

The helper revision/digest is caller-supplied provenance, not a Git probe. Then
reference the attachment using existing campaign-plan fields:

```yaml
search_plan:
  - id: "<direction-id>"
    conditional_headroom: >-
      Synthetic component example only: conditional floor 10 s for the stated
      work/traffic. Exposed E2E time, baseline, noise and removable headroom remain
      unknown; no speedup or goal decision follows.
    evidence: "plan/attachments/<analysis-id>.json"
```

This is a row-4 excerpt; preserve all other required plan fields. The helper does
not create the attachment, modify the plan or freeze/accept goals. Frozen rows,
RunSpec, validators, historical records and goal-owner authority are unchanged.
