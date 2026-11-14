---
name: splash
description: "Investigate Splash model-format compatibility, automatic memory planning, Metal and ANE execution, DFlash2 verification, cache and request identity, and correctness-gated serving measurements."
license: NO_LICENSE
disable-model-invocation: true
metadata:
  disco-role: operating
---

# Splash inference engineering

Use this source-derived candidate to diagnose an inference or serving question,
select a bounded change and state the check that could falsify it. It is not a
complete upstream manual or a certified Apple backend recipe. Read
[source and method provenance](references/repo-provenance.md) before reuse.

## Route the work

| Question | Route | Expected result |
| --- | --- | --- |
| A format is rejected, a model will not fit or a cache cap is surprising | [runtime-planning](sub-skills/runtime-planning/SKILL.md) | Compatible representation and memory-owner ledger |
| Prefix reuse, persistent cache, request isolation or Responses history is confusing | [serving-cache](sub-skills/serving-cache/SKILL.md) | Identity, state-lifetime, admission and recovery ledger |
| Draft acceptance rises but speed/answers change; an ANE or precision path differs | [qualification](sub-skills/qualification/SKILL.md) | Semantic control, actual path and matching proof ladder |

Use the bundled [request builder](scripts/request_template.py) to prepare a
small Chat Completions body offline. It prints JSON; it never contacts a server,
installs Splash, launches a client or downloads a model. Its deliberately small
option set is not the complete upstream API.

## Establish the execution tuple

Record source/build revision, macOS and Apple device, target checkpoint/format/
quantization and artifact identity, compatible draft, tokenizer/template and
vision selection. Add context, cache/memory controls, KV and recurrent-state
precision, ANE setting, verifier-row policy, concurrency/priority, sampling,
prompt/output/quality controls and cold/warm/persistent-cache state.

An API model alias is not a new weight selection. Equal bit width does not
prove loader/kernel compatibility. A seeded request does not freeze cache,
batch/chunk or adaptive-verification scheduling.

## Native preparation boundary

The source targets Apple Silicon M3 or newer and macOS 26.4 or later. The public
release installation is `brew install incoai/tap/splash`; an authorized operator
can inspect `splash serve --help` before loading anything. Installation and
serving are separate actions: the normal serve path can download target/draft
weights. Do not run it solely to inspect an option.

Splash is a native Metal/C++ runtime with Python server/installer modules, not
a pip-installable project. This extraction adapted AREX's package inspection
to isolated, explicit source-module identity/signature checks. Linux Python
logic does not validate the actual Metal/ANE/model path.

## Work a bounded hypothesis

1. Read the selected route and nearest bundled mechanism/failure reference.
2. Separate source observation, upstream measurement and proposed experiment.
3. Identify representation, owner, validity key, lifetime and reclaim/rollback
   boundary before tuning a numeric control.
4. Freeze workload, semantic reference and measurement boundaries before a
   comparison. Keep campaign pins and gates in the acceptance issue.
5. Confirm the path actually activated; retain fallbacks, admission waits,
   evictions, cancellations and errors instead of treating them as warmup noise.
6. Correctness and model quality precede ranking. A cache/parser/codec check
   cannot establish GPU state, a distributional guarantee or service SLOs.

## Stop and report

Return execution identity, observation, source-backed invariant, alternate
explanation, smallest discriminating check, actual result and unresolved gap.
Stop at unsupported formats, unavailable backend/model resources, unsafe service
exposure or the authorized budget. Do not change system settings or launch an
external coding client merely because imported guidance mentions one.

Required Metal/ANE/model/actual disk-state evidence remains
**BLOCKED_REQUIRED_BACKEND**. Source and CPU checks do not qualify performance,
quality, service operation or behavioral skill efficacy. Final admission of a
partially verified candidate requires an informed decision, not auto-import.

The source [Apache-2.0 license](LICENSE) and
[third-party notices](THIRD_PARTY_NOTICES) are retained. `NO_LICENSE` is the
actual AREX resolver's unauthenticated-CLI warning fallback, not a legal finding;
models and external tools retain their own licenses.
