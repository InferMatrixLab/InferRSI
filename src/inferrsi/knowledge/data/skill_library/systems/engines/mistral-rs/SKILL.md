---
name: mistral-rs
description: "Investigate mistral.rs Metal paged-attention decode layouts, prefill coordinates and workspace, actual-model prewarm and native test evidence without treating static metadata or prepared pipelines as executed GPU correctness or performance."
license: NO_LICENSE
disable-model-invocation: true
metadata:
  disco-role: operating
  inferrsi: |
    {
      "schema_version": 1,
      "kind": "skill",
      "origin": [
        "external"
      ],
      "status": "candidate",
      "empirical_validation": "not_run",
      "license": "NO_LICENSE",
      "tags": [
        "mistral-rs",
        "metal",
        "candle",
        "paged-attention",
        "cache-layout",
        "prefill-metadata",
        "workspace",
        "prewarm",
        "native-evidence"
      ],
      "sources": [
        {
          "type": "git",
          "url": "https://github.com/EricLBuehler/mistral.rs",
          "commit": "9459891e7697238225885518119682ac8209a612",
          "version": "0.9.5",
          "license": "MIT root; identified paged attention portions Apache-2.0 with NOTICE",
          "readset": "references/source-identity.json",
          "paths": [
            ".github/workflows/ci.yml",
            "AGENTS.md",
            "Cargo.lock",
            "Cargo.toml",
            "LICENSE",
            "README.md",
            "docs/src/content/docs/guides/perf/paged-attention.mdx",
            "examples/python/paged_attention.py",
            "mistralrs-core/src/paged_attention/cache_engine.rs",
            "mistralrs-core/src/paged_attention/metal_hnd_tests.rs",
            "mistralrs-core/src/paged_attention/mod.rs",
            "mistralrs-core/src/pipeline/metal_warmup.rs",
            "mistralrs-paged-attn/Cargo.toml",
            "mistralrs-paged-attn/LICENSE-APACHE",
            "mistralrs-paged-attn/NOTICE",
            "mistralrs-paged-attn/build.rs",
            "mistralrs-paged-attn/src/metal/backend/mod.rs",
            "mistralrs-paged-attn/src/metal/backend/paged_attention.rs",
            "mistralrs-paged-attn/src/metal/backend/paged_prefill.rs",
            "mistralrs-paged-attn/src/metal/kernels/mod.rs",
            "mistralrs-paged-attn/src/metal/kernels/paged_decode_hnd.metal",
            "mistralrs-paged-attn/src/metal/kernels/paged_prefill.metal",
            "mistralrs-paged-attn/src/metal/mod.rs",
            "mistralrs-paged-attn/tests/metal_prefill.rs"
          ]
        },
        {
          "type": "git",
          "url": "https://github.com/VectorSpaceLab/AREX-Skill",
          "commit": "ac3fe1afa80fb9a09775ecfb2b6cc3ba850a2db6",
          "paths": [
            "cli/packages/coding-agent/src/disco/skills/create-repo-skill",
            "cli/packages/coding-agent/src/disco/skills/prepare-repo-skill-env",
            "cli/packages/coding-agent/src/disco/skills/workflow-authoring",
            "cli/packages/coding-agent/src/disco/skills/verify-repo-skill"
          ],
          "scope": "Portable compatible-agent native Rust/source adaptation; no DisCo CLI/model execution or managed import."
        }
      ],
      "construction": {
        "anchor_kind": "source",
        "distillation_form": "repository-operating-graph",
        "strategy": "arex-portable-meta-skills",
        "status": "partial-candidate",
        "native_import": "not-run",
        "method": "Stable-ID bounded decode/prefill/qualification author lanes, whole-graph reconciliation, hard cases and offline helper/static/scaffold/wheel checks; compiler and actual Apple evidence not_run."
      },
      "applicability": {
        "scope": "Selected native Metal paged decode/prefill layout/metadata/workspace and preparation/evidence investigation. Common catalog categorization is not CPU inference or hardware certification.",
        "prerequisites": "Access to the pinned Rust/Candle/MSL decode, prefill and qualification contracts; native comparisons need the matched Rust/Apple/Candle/shader stack and separately authorized frozen references.",
        "input_contract": "mistral.rs/Candle/native artifact revisions, Rust toolchain, Apple SDK/OS/device, actual model/cache dtype and representation, shape/strides/offsets, block table, context and execution limits.",
        "produced_artifact": "A source/build-bound route and invariant report with actual versus declared facts, safe support result, counter-signal and smallest next native check; unavailable Metal/kernel/model evidence remains blocked.",
        "failure_modes": "Equating element counts with physical alias/layout identity, transferring decode geometry to prefill, or treating prewarm/pipeline preparation as actual dispatch can misclassify eligibility and native correctness."
      },
      "limitations": [
        "BLOCKED_REQUIRED_BACKEND: actual Rust/Candle/Apple Metal compilation, native tensor/cache/dispatch/parity/model/quality/service/performance evidence not_run.",
        "Cargo/rustc and compatible Apple SDK/device unavailable; no Rust package/toolchain or native dependency installation, live Rust API inspection or source test execution claimed.",
        "Offline helpers screen caller declarations, source byte formulas or boundary enumeration only; no tensor authentication, GPU simulation, native eligibility, scratch-capacity or physical-fit proof.",
        "Generic model/loading/quantization/server/agentic/distributed/CUDA paths and unmined specialized kernels remain explicit long-tail gaps; broad skill efficacy unmeasured.",
        "NO_LICENSE is the actual unauthenticated gh resolver fallback, not legal absence; root MIT and identified component Apache-2.0/NOTICE retained independently."
      ],
      "provenance_readsets": [
        "references/repo-provenance.md",
        "references/source-identity.json"
      ],
      "consumption_mode": "packaged",
      "recommendations": [
        "Select decode, prefill or qualification by the failed contract, then follow cache/metadata bytes from producer through view to native consumer.",
        "Keep static predicates, pipeline preparation, kernel dispatch, numerical correctness and model/service outcomes as separate evidence steps; retain skipped or gated tests.",
        "Use the matched Candle revision and native shader/build inputs; broad workspace tests can require model fixtures, tokens and downloads."
      ]
    }
---

# mistral.rs Metal paged-attention contracts

Use this source-derived **candidate** for the Rust/Candle engine's native Metal
paged-attention path. It is a focused repository operating graph, not a generic
model catalog, a deployment guide or a verified engine. Read
[source and method provenance](references/repo-provenance.md) before using it on
a different checkout. Reading it does not authorize installation or execution.

## Route by the failed contract

| Question | Canonical owner |
| --- | --- |
| Does HND/packed K/V, FP8 scale, GQA/head geometry, sliding decode or scratch agree? | [decode-contract](sub-skills/decode-contract/SKILL.md) |
| Do packed/padded queries, absolute positions, masks/ranges and prefill workspace agree? | [prefill-contract](sub-skills/prefill-contract/SKILL.md) |
| Did model warmup prepare the intended pipelines, and what did native tests actually prove? | [qualification](sub-skills/qualification/SKILL.md) |
| Which other engine features, dependencies and licenses are outside this extraction? | [scope and notices](references/scope-and-notices.md) |

The selected source owns Rust shape/configuration/consumer code and actual MSL
attention, rather than merely naming an external backend. Candle supplies the
tensor/device integration. Shared ancestry with other Metal engines does not
make their cache layouts, scratch planners or synchronization interchangeable.

## Establish identity before proposing a change

1. Record exact mistral.rs/Candle/native artifact revisions, Rust toolchain,
   Apple SDK/OS/device, actual model/cache dtype and representation, shape,
   strides/offsets, block table, context and execution limits. Model and asset
   identities are separate from source version or advertised support.
2. Identify the producer, view and native consumer of cache/metadata bytes.
   Equal element counts, a layout setting and physical alias identity differ.
   Decode and prefill deliberately have different supported geometry domains.
3. Select the smallest matching sub-skill and its bundled helper. Helpers use
   explicit synthetic/caller-declared JSON and Python standard library only.
   They do not import an engine, compile Rust, read weights, allocate device
   memory, emulate GPU computation or establish native eligibility.
4. Separate a static source predicate, pipeline preparation, actual kernel
   dispatch, numerical correctness, model quality and service performance.
   None automatically implies the next. Preserve unsupported cases, failed
   observations, skipped/gated tests and required missing evidence.
5. For an actual change or experiment, obtain its separate authority, freeze
   controls/acceptance gates and select discriminating native references before
   running it. Do not use source crossover constants or test tolerances as
   portable performance/quality acceptance bars.

## Preparation and use boundary

This snapshot's workspace is version 0.9.5, edition 2021 and requires Rust 1.94.
The Metal feature requires a compatible Apple native stack plus matched Candle
revision and shader/build inputs. The source repository's broad workspace tests
can use model fixtures, tokens and downloads; they are not safe default checks.

This graph does not ship an installer. Use only an independently reviewed,
versioned upstream release/build procedure under separate installation
authorization. Do not execute remote shell installers or install Rust/SDKs just
to inspect this graph. If an authorized CLI is already installed, a bounded
identity/help check is:

```bash
mistralrs --version
mistralrs --help
```

Those public CLI invocations were **not run** here. Current inspection has no
Cargo/rustc or compatible Apple backend; no Rust compilation or live Rust API
inspection is claimed. The source/manual adaptation is explicitly partial.
Bundled helpers remain usable without the source checkout or inference package.

## Return a bounded result

Report source/build identities, actual versus declared facts, route, invariant,
safe support result, counter-signal and smallest next authorized native check.
Required Metal/kernel/model validation remains `BLOCKED_REQUIRED_BACKEND` until
separately executed; compiler checks are `not_run`. Candidate state is not
promoted by helper tests, packaging, independent content review or a merged PR.
Memory fit, quality, service performance and broad skill efficacy are unverified.
