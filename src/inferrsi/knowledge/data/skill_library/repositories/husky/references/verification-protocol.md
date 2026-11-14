# Original verification protocol

The procedure below is proposed research guidance, not an observation of an
unavailable implementation. The author-report inventory is a separate evidence
class. None of these checks has been executed on the engine by this extraction.

## Claim card

Record:

- The exact claim and source/view date; what decision it is meant to support.
- Engine/build revision, compiler/runtime/device and source availability.
- Model, representation and complete payload/tokenizer/template identities.
- Workload, inputs, output budget, quality standard and expected failure policy.
- Compared modes, baseline, cold/warm state, concurrency and sampling contract.
- Timing boundary, units, repetitions, raw observations and exclusion reasons.
- Artifact availability and hashes actually checked from bytes, not merely
  copied from a report. Unknown fields remain unknown.
- Authorization, frozen validators/gates, evidence owner and stopping condition.

The bundled evidence-card helper checks only a small schema/identity projection
of this card. It neither authenticates the fields nor implements a campaign.

## Mechanism questions and discriminating checks

| Question | Proposed check when source/resources are authorized | Counter-explanation to retain |
| --- | --- | --- |
| Does a representation transformation preserve the intended values? | Compare independently decoded payloads and relevant numeric outputs under a frozen identity | Equal nominal precision or file size can hide a different layout or arithmetic |
| Is the target mechanism responsible for the difference? | Isolate one mechanism with matched inputs and execution controls; record the actually selected path | Cache state, workload repetition, different work or fallback can explain the result |
| Is accepted work committed consistently? | Trace logical position and owned state across rejection, interruption and continuation, then run the matching native fixture | Returned tokens alone do not prove backend state or rollback |
| Is host/device overlap useful under this workload? | Retain host submission/completion and device timing with the same quality/workload; separate instrumentation mode | A reduced dispatch count may leave the bottleneck unchanged or add synchronization pressure |
| Does a local counter-signal generalize? | Identify a changed condition and freeze a test that could reject the explanation | One no-gain or successful example does not establish all shapes/devices/workloads |
| Is there a useful user-visible improvement? | Measure the complete authorized task/service boundary with errors, quality and tail behavior | A component metric may omit loading, queues, output handling or failed requests |

Do not infer implementation details from a diagram or derive a validated model
of performance from a product page. A theoretical cost decomposition can guide
the next observation; it is not measured evidence.

## Preserve negative and missing evidence

Retain attempted configurations, failures, rejected/noisy samples, missing
artifacts and the source's original disposition. If exclusions are reported but
the excluded raw observations are unavailable, record that availability gap;
do not assume the remaining table is independently auditable. An observed
environment failure and a completed numerical rejection have different meanings.

A new hypothesis should name applicable signal, counter-signal, changed condition
and next falsifier. Never rewrite an earlier report or frozen validator to fit
the new story. Do not promote a research candidate through a helper's success.

## Minimal evidence request and stopping condition

Ask for one bounded, immutable bundle sufficient for the selected question:
implementation/build identity; compatible model/workload/output identities;
raw successful and unsuccessful attempts; measurement/quality validators; and
the actual native environment/commands needed to reproduce the relevant path.
Do not request credentials, private session logs, hidden reasoning or unrelated
personal data. Redact task-owned logs without changing their outcomes.

If the bundle, legal access, hardware, model or authority is absent, stop the
dependent experiment. Return the useful research question and exact missing
evidence. Missing reproduction remains unverified/INCONCLUSIVE; it is not an
automatic FAIL of the publisher or a PASS of a proposed adaptation.
