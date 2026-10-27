---
name: dwarfstar
description: "Investigate DwarfStar model fit, expert SSD streaming, session and vision cache correctness, speculative sampling and distributed execution using pinned source contracts and explicit native verification boundaries."
license: NO_LICENSE
disable-model-invocation: true
metadata:
  disco-role: operating
---

# DwarfStar inference engineering

Use this candidate to turn a DwarfStar capacity, state-correctness or execution
question into a bounded hypothesis and discriminating check. It distills
`antirez/ds4`, not an arbitrary GGUF runner. Start with the
[source and method contract](references/repo-provenance.md).

The operating guidance is source-derived. A local CPU build or bookkeeping test
does not validate Metal/CUDA/ROCm kernels, model output, a real service, physical
tensor parallelism or a performance gain. Required backend evidence remains
**BLOCKED_REQUIRED_BACKEND**; this candidate is not fully backend-verified.

## Route the question

| Question | Read next | Expected output |
| --- | --- | --- |
| A model fits on disk but not in RAM/VRAM; cache grows; more sessions fail | [runtime-memory](sub-skills/runtime-memory/SKILL.md) | Representation and phase/owner memory ledger, one causal hypothesis |
| A repeated prompt misses, reuses wrong image/tool history or corrupts a continuation | [serving-state](sub-skills/serving-state/SKILL.md) | Token/image/state identity and invalidation ledger |
| A draft is faster but changes results; a TP parser test passes; a backend falls back | [qualification](sub-skills/qualification/SKILL.md) | Matching correctness test, actual execution path and remaining native gap |

Use the bundled [request builder](scripts/request_template.py) when preparing a
minimal Chat Completions request. It prints JSON only: no engine, network,
credential, model download or service is started. Its options are deliberately
smaller than the upstream API.

## Establish the execution tuple

Record the engine revision and patches, model family/checkpoint/quantization and
artifact identity, selected native backend/build, device and transport topology,
RAM/VRAM/storage budget, context/prefill chunk/session count, image inputs,
sampling/seed and speculation policy. Add cold/warm/live/disk-cache state and
the workload's quality and service requirements. Unknown fields remain unknown.

Do not infer model support from a flag, shared quantization name, successful file
mapping or API model alias. The actual loaded GGUF and model-specific graph
select semantics. Flash, V4.1, PRO, GLM and Qwen routes differ.

## Native preparation, not automatic installation

DwarfStar is a native C engine, not a Python distribution. A prepared CPU
inspection build can expose CLI help without weights; accelerated builds require
their matching compiler/runtime. An operator with a compatible installed build
can inspect `ds4 --help` and `ds4-server --help` before choosing options.
For an authorized source installation, use the public repository at the
reviewed source revision and the native `make cpu` target for CPU inspection;
Metal/CUDA/ROCm require the matching native build described by this graph.
Building, downloading weights, exposing a listener and changing system memory
limits are separate actions requiring task authorization.

This extraction adapted AREX's Python-only environment fields to native C build
and CLI identity. It did not invent an installed Python package, run a DisCo
model backend or install into a managed DisCo skill collection.

## Work one bounded hypothesis

1. Select the relevant route and read its bundled mechanism and failure notes.
2. Separate source observations, upstream reports and proposed experiments.
3. Identify the owner, lifetime, validity key and release/rollback boundary.
4. Freeze controls before a comparison; change one mechanism or explicitly
   declare a coupled change. Numeric gates and campaign revisions belong in
   the acceptance issue, not in this reusable guidance.
5. Verify the smallest invariant before measuring performance; retain failures,
   refusals, fallback messages, cancellations and unavailable fixtures.
6. For a service claim, run the accepted model/workload/quality/concurrency
   protocol on the actual backend. Microtests are not service qualification.

## Stop and report

Return the executing tuple, observed signal, source-backed mechanism, alternate
explanation, proposed falsifier, actual check outcome and unresolved gap. Stop
at unavailable hardware/weights, unsafe exposure or the authorized budget.
Do not disable a memory guard to turn a refusal into a capacity claim.

Read [source notices](LICENSE) when redistributing adapted material.
`NO_LICENSE` is the AREX resolver's unauthenticated-CLI warning fallback, not a
claim that DwarfStar lacks a legal license; the pinned source license is MIT.
Model weights and retained third-party code have independent obligations.
