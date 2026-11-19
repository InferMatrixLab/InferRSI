---
name: lithos-metal
description: "Inspect Lithos Metal compilation and fusion, GPU-resident generation and DSpark state, or local serving and exact-prefix caches on Apple silicon; use when changing recipes, diagnosing stale state, or qualifying an inference claim."
metadata:
  inferrsi: |
    {
      "profile": "local-skill-v1",
      "schema_version": 1,
      "kind": "skill",
      "origin": [
        "external"
      ],
      "status": "candidate",
      "empirical_validation": "not_run",
      "tags": [
        "lithos-metal",
        "metal",
        "apple-silicon",
        "repository-guide"
      ],
      "sources": [
        {
          "type": "git",
          "url": "https://github.com/lithos-ai/lithos-metal",
          "commit": "6653b7df5f2c4392ec7b038960f2796b1499923f",
          "paths": [
            "kernels/common/spec_ops.metal",
            "monolith/backends/metal/base.py",
            "monolith/backends/metal/registry.py",
            "monolith/compiler/arena.py",
            "monolith/compiler/barriers.py",
            "monolith/compiler/coverage.py",
            "monolith/compiler/decoder_fusion.py",
            "monolith/compiler/emit.py",
            "monolith/compiler/region_fusion.py",
            "monolith/compiler/static_fusion.py",
            "monolith/core/step_state.py",
            "monolith/generate.py",
            "monolith/runtime/engine.py",
            "monolith/runtime/prefix_cache.py",
            "monolith/runtime/prefix_store.py",
            "monolith/serve.py",
            "monolith/serving/cache.py",
            "monolith/serving/lifecycle.py",
            "monolith/serving/setup.py",
            "monolith/spec/dspark/model.py",
            "runtime/src/metal_core.mm"
          ],
          "readset": "references/source-notes.md"
        }
      ],
      "applicability": {
        "scope": "Pinned Lithos Metal 0.1.2 source/API contracts; Apple silicon Metal runtime; model and recipe qualification required separately.",
        "prerequisites": "Access to the pinned package/API and selected compiler, generation or serving contracts; revision/API drift needs a fresh bounded inspection, and efficacy claims need campaign-owned gates and matching native/model evidence.",
        "input_contract": "Actual source/package version, backend/configuration, chip/core count and OS, target/draft checkpoint identities, context and prompt-token IDs, sampling/numerical options and the affected recipe/runtime/session/cache boundary.",
        "produced_artifact": "A routed region/dependency, committed-state or cache-identity/lifecycle ledger, followed by the smallest supported finding, missing checks and next bounded action.",
        "failure_modes": "Treating session adoption/cache hits as generation correctness, fewer dispatches as faster rounds, another chip recipe as the default, CPU cache checks as GPU rollback or health liveness as loaded/warm model state can yield unsupported conclusions."
      },
      "limitations": [
        "Source-derived candidate; empirical efficacy validation not_run.",
        "CPU/software and synthetic Metal contracts do not qualify full-model/DSpark numerics, quality or E2E performance.",
        "No model downloads, live DisCo deployment or inference backend integration is provided."
      ],
      "provenance_readsets": [
        "references/source-notes.md"
      ],
      "consumption_mode": "packaged",
      "license": "Apache-2.0",
      "disable-model-invocation": true,
      "metadata": {
        "disco-role": "operating"
      },
      "recommendations": [
        "Follow session replacement across recipe geometry, committed generation state and serving adoption/cache identity before interpreting a cache hit.",
        "Keep an unfused/native or target-only control with matching decoded weights, numerical mode, row bounds and sampling policy; verify dependencies and persistent state before timing.",
        "Distinguish package/CPU checks, synthetic Metal execution, model continuation and HTTP workload evidence; chip recipes and target-compute projections do not establish another device or E2E rate."
      ]
    }
---

# Lithos Metal operating guide

## Trigger and boundary

Use this entry for Lithos Metal compiler, generation-state and serving/cache
questions. Route the concrete question before suggesting a recipe or reset.
This is a **source-derived candidate** at upstream commit
`6653b7df5f2c4392ec7b038960f2796b1499923f`, distribution `lithos-metal` 0.1.2,
Python import namespace `monolith`. Empirical efficacy validation is **not_run**.

Source facts describe that snapshot; the decision procedures are proposed
applications of those facts. Package/CPU contracts and a synthetic Metal program
can be checked without model downloads. They do not qualify complete model
continuation, DSpark numerics, model quality or service performance.

## Choose a route

| Question | Read next | Output |
| --- | --- | --- |
| Missing op binding, fusion eligibility, tile/workers, barriers or scratch aliasing | [compile-fusion](sub-skills/compile-fusion/SKILL.md) | Region/dependency ledger, normalized control and fallback checks |
| Wrong continuation after rejection, active rows, ring overflow, stop or cancellation | [generation-state](sub-skills/generation-state/SKILL.md) | Committed-prefix/state ledger and bounded reproduction plan |
| Local startup, packs, HTTP state, prefix hits, disk integrity or idle reload | [serving-cache](sub-skills/serving-cache/SKILL.md) | Cache-identity/lifecycle decision and isolated checks |

A session replacement can cross all three routes: a recipe changes program
geometry, generation owns committed state, and serving owns adoption/cache
identity. Inspect that boundary before interpreting a cache hit as correctness.

## Establish the package contract

1. Record the actual source revision, package version, backend ID/configuration,
   chip identity and core count, OS, target/draft checkpoint identities, context,
   prompt token IDs, sampling and numerical options. Redact private paths and
   prompt content when sharing. Keep absent fields explicit.
2. Read [repo-provenance](references/repo-provenance.md) and the pinned
   [source readset](references/source-notes.md). Revision or API drift requires
   a fresh bounded inspection; do not transfer recipe qualification by name.
3. Read [package and API contract](references/package-api.md) for installation,
   namespaces, optional dependencies and CPU-versus-Metal boundaries.
4. Optionally run the bundled [inspect_contract.py](scripts/inspect_contract.py)
   in the selected installed environment. It reports software/API facts;
   `--check-contract` adds tiny CPU checks. It never creates a device, downloads
   weights, starts a server or runs automatically when this skill is read.

```bash
python <SKILL_DIR>/scripts/inspect_contract.py --check-contract
lithos-metal --version
lithos-metal serve --help
```

`<SKILL_DIR>` is this packaged skill directory. Locate the resource through the
library reader or package resources; the helper works from any current directory.
A successful diagnostic is limited to its reported checks.

## Work sequence

1. Name the affected owner: model graph, chip recipe, emitted `Program`, runtime
   buffers/control, serving session, pack cache or prefix checkpoint.
2. Reconstruct the earliest boundary whose inputs/outputs disagree. Use the
   relevant route's counter-signals before proposing a mutation.
3. Preserve an unfused/native or target-only control where applicable, matching
   decoded weights, numerical mode, row bounds and sampling policy.
4. Verify control/dependency and persistent-state correctness before timing.
   Separate source inspection, CPU fixtures, synthetic Metal execution,
   model continuation and HTTP workload evidence in the result.
5. Report the smallest supported finding, missing checks and next bounded action.
   Use campaign-owned frozen gates for any efficacy claim. Missing required
   model or E2E evidence remains unverified/`INCONCLUSIVE` for that claim.

## Counter-signals and limits

Layer-wise mixer fusion is not whole-model fusion; MLP regions can remain
separate. Fewer dispatches do not establish a faster complete round. A measured
recipe for one chip/core variant is not another variant's default. CPU cache
tests do not demonstrate GPU state rollback. `/health` liveness does not show a
model is loaded, correct or warm. A target-compute projection is not an E2E rate.

Read [troubleshooting](references/troubleshooting.md) for package/import and
cross-route failures. Source code and documentation occasionally differ in
generality: use the precise code path and preserve the documentation's scope.
No model downloads, device resets, live cache deletion, server launch or client
execution are implied by reading this guide.

## Attribution and reuse

Read [notices](references/notices.md) when adapting material. The bundled
[LICENSE](LICENSE), [upstream NOTICE](references/upstream-notice.md) and
[MLX license](references/mlx-license.md) preserve source attribution. This guide
adds no runtime dependency on Lithos Metal, MPK/Mirage, MLX or DSpark references.
