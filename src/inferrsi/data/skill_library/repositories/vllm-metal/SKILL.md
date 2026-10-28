---
name: vllm-metal
description: "Investigate vllm-metal Apple inference through platform and
  native-ABI selection, paged KV/offload ownership, speculative/deferred state
  and actual dispatch/serving evidence without upgrading source or CPU checks to
  backend qualification."
license: NO_LICENSE
disable-model-invocation: true
metadata:
  disco-role: operating
---

# vLLM Metal inference investigation

Use this source-derived **candidate** for the vLLM Apple Silicon plugin, not
for generic vLLM, MLX or Metal programming. Read
[source/method provenance](references/repo-provenance.md) before applying it to
a checkout. This graph is self-contained operating guidance with offline
support; it does not include an inference engine or authorize executing one.

## Route by the contract that can fail

| Question | Owner |
| --- | --- |
| Why does import succeed but Metal registration/build/model selection fail? | [platform-config](sub-skills/platform-config/SKILL.md) |
| Why is a setting ignored, the runner wrong, or a native ABI stale? | Same owner; selected-knob syntax helper and preparation references |
| Does host offload add RAM, which prefix is reusable, or why does wake fail? | [cache-lifecycle](sub-skills/cache-lifecycle/SKILL.md) |
| Are GDN drafts rolled back correctly, pending tokens owned safely, or GQA actually executed? | [qualification](sub-skills/qualification/SKILL.md) |
| Can a reported rate/parity result support a service or quality claim? | Same owner; frozen workload, execution-boundary and failure accounting |
| What is covered, excluded or differently licensed? | [scope and notices](references/scope-and-notices.md) |

Upstream vLLM supplies API/scheduler/block management, mlx-lm model layers,
and this plugin the request-aware native attention/runtime integrations.
Shared upstream interfaces do not automatically qualify every combination.
The MLX path, alternative MPS path, full-attention versus recurrent state,
cache capacity versus physical residency, and kernel versus HTTP timing are
deliberately separate throughout these procedures.

## Establish identity and authority

1. Record exact source/package/runtime/native artifact identities, Python,
   OS/chip/device, backend and executor, checkpoint/tokenizer/draft identities,
   format/dtype, effective feature flags and workload. Readsets identify source
   bytes and selected analysis spans, not native execution.
2. Match the intended claim to its owner. Resolve an unsupported pairing or
   stale artifact before tuning capacity or quoting throughput. A feature
   switch permits eligibility; it does not prove that the worker took that path.
3. Choose the smallest safe check. The bundled helpers parse explicit JSON
   and compute bounded arithmetic/summaries, without native imports, downloads,
   services, credentials or host mutation. No helper authenticates model data,
   proves memory fit or measures inference.
4. Separate empirical facts, source reports, test definitions and proposals.
   Retain unsuccessful paths and missing evidence. A successful Python import
   or CPU parser test is not a native accelerator substitute.
5. For actual engine changes or experiments, establish separate authorization,
   safe resource ownership, frozen correctness/quality/performance gates and
   cleanup. Never erase a user KV store or install toolchains as an implicit
   step in answering a diagnostic question.

## Public preparation boundary

The source snapshot supports Python3.12/3.13 and requires Apple Silicon/macOS15+
for engine execution. Stable users can use the project's Homebrew tap/formula;
development source setup additionally builds native artifacts with full Xcode/
SDK26.2+. Installation is not performed by this skill. After an authorized
installation, a minimal read-only package check is:

```bash
python -I -c 'import importlib.metadata as m; import vllm_metal; print(m.version("vllm-metal"), vllm_metal.__version__)'
```

That deliberately lazy import proves only selected package visibility. Read
the platform route for exact ABI/backend/runner distinctions and failure
handling before a separately authorized startup. Do not execute remote shell
installers, upstream development scripts or model downloads from this graph.

## Return a bounded conclusion

Report identity, selected route, source-supported invariant, actual safe check,
result, counter-signal and smallest next authorized native check. This delivery
has partial CPU API/parser evidence only. Required Apple MLX/Metal and MPS
kernel/model, real transfers/sleep/wake, output quality, HTTP serving/performance
and broad skill efficacy remain unverified (`BLOCKED_REQUIRED_BACKEND` where
required). Source-derived candidate status is not promoted by packaging,
independent content review, a merged PR or green scaffold CI.
