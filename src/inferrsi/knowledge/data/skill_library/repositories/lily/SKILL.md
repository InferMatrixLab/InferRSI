---
name: lily
description: "Investigate Lily's exact Qwen3.6-35B-A3B MLX-affine-Q4 contract, Metal state and kernels, strict greedy text API, token-prefix session cache and source-qualified validation or benchmark plans."
license: NO_LICENSE
disable-model-invocation: true
metadata:
  disco-role: operating
---

# Lily inference engineering

Use this source-derived candidate to investigate representation, state or
qualification questions in `perplexityai/pplx-garden/lily`. It is not a generic
Metal/MLX runner. Read [source and method provenance](references/repo-provenance.md)
before applying it to a different revision, model or device.

## Route the question

| Question | Route | Expected result |
| --- | --- | --- |
| A nominally 4-bit model fails to load, or memory/sequence capacity is unclear | [model-runtime](sub-skills/model-runtime/SKILL.md) | Exact architecture/layout and ownership/capacity contract |
| A request is rejected, or equal keys/history do not reuse state as expected | [serving-cache](sub-skills/serving-cache/SKILL.md) | Strict API, token-prefix and state-lifetime diagnosis |
| CPU references look green, a golden is ignored, or MLX comparisons disagree | [qualification](sub-skills/qualification/SKILL.md) | Matching native evidence, version and metric boundaries |

The focused routes bundle safe offline screening/request support where useful.
Those helpers do not invoke Rust, compile shaders, load tensors, tokenize a real
checkpoint or start inference. Their positive result is not native acceptance.

## Establish the execution tuple

Record engine/source and Cargo lock/toolchain, macOS/chip/GPU family, exact
checkpoint and tensor payload identities, config/affine layout, tokenizer/chat
template and output-stop identity. Add sequence/output budgets, greedy policy,
input history, prefix-cache state, workload and quality/measurement requirements.

Equal nominal bit width, file size, API name or `prompt_cache_key` does not
identify equivalent tensors, rendered tokens or valid recurrent/KV state.
Separate reported benchmark identity from the checked-out runner's version.

## Native preparation boundary

The source requires Rust 1.92, macOS 26 and Apple GPU family 10/M5 or newer.
For an authorized source build the public command is
`cargo build --release --locked`; shader source is compiled at runtime, not by
an offline metallib step. Inspect an installed binary's help before any model
run. Building a package does not supply its supported checkpoint or qualify it.

This extraction has neither Cargo/Rust nor a compatible Mac/model environment.
AREX's Python-package preparation was explicitly adapted to native Rust/Metal
identity and small offline helper checks. No installed Python distribution,
Rust test run or native backend success is fabricated.

## Work one bounded hypothesis

1. Read the selected bundled contract and failure notes.
2. Resolve exact input representation and actual API semantics before tuning.
3. Trace owner, logical token frontier, allocation, cache key and release or
   restore boundary. Matching visible text is weaker than exact token identity.
4. Preserve the source's extra request lookahead slot when budgeting; do not
   replace its checked arithmetic with only prompt-plus-visible-output length.
5. Freeze workload, checkpoint/version, numerical/quality controls and metrics
   before comparing. Gates and campaign revisions belong in an acceptance issue.
6. Distinguish source inspection, offline helper checks, compiled native tests,
   real Metal operators, matched-model goldens and service measurements.

## Stop and report

Return exact source/model/device identity, observation, invariant, alternate
cause, smallest falsifier, actual check result and remaining gap. Stop at
unsupported format/API, missing compiler/backend/checkpoint, unfrozen gates or
the authorized budget. Do not install a toolchain, download a model, alter the
API or weaken an ignored/golden test merely to obtain a green result.

Required native compiler/Metal/model evidence remains blocked. CPU reference
functions and Python screening are not GPU test execution; skipped or ignored
cases do not become passing evidence. No quality, performance, service or
behavioral skill-efficacy qualification is claimed. Final partial-candidate
admission is a separate informed decision, not automatic import.

Source [Apache-2.0 license](LICENSE) and [NOTICE](NOTICE.md) are retained.
`NO_LICENSE` is the actual AREX unauthenticated-CLI fallback, not a legal finding;
model weights and third-party material retain their own obligations.
