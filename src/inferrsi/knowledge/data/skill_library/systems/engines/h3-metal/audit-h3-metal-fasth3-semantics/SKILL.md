---
name: audit-h3-metal-fasth3-semantics
description: "Audit h3-metal FastH3 effective configuration, checkpoint tensor and schedule semantics, partial VSA tiles, sparse eligibility and dense-plus-coarse fallback without treating source or header checks as native parity."
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
      "license": "NO_LICENSE",
      "tags": [
        "h3-metal",
        "FastH3",
        "MiniMax-H3",
        "apple-silicon",
        "metal",
        "qkv-layout",
        "swiglu",
        "bf16",
        "vsa",
        "sparse-attention",
        "fallback",
        "effective-configuration"
      ],
      "sources": [
        {
          "type": "git",
          "url": "https://github.com/zuiho-kai/h3-metal",
          "commit": "4ba47a3eabdbebf801ac6664b31f8ec168bc57a8",
          "paths": [
            "LICENSE",
            "THIRD_PARTY_NOTICES.md",
            "Makefile",
            "README.md",
            "docs/USAGE.md",
            "h3.h",
            "h3.c",
            "main.c",
            "h3_host.h",
            "h3_host.c",
            "h3_dit.c",
            "h3_dit_schedule.c",
            "h3_gpu.m",
            "h3_shaders.metal",
            "tests/test_h3.c",
            "tests/test_vsa_coarse.c",
            "tests/test_real_dit_schedule.c",
            "tests/bench_dit.c",
            "tools/fasth3_keymap.py",
            "tools/fasth3_keymap.md",
            "bench/run_fox2.sh"
          ],
          "readset": "references/source-notes.md",
          "identity": "references/source-identity.json",
          "license": "MIT; selected shader-derived components separately BSD-3-Clause",
          "third_party_notices": "references/THIRD_PARTY_NOTICES.md"
        },
        {
          "type": "git",
          "url": "https://github.com/VectorSpaceLab/AREX-Skill",
          "commit": "ac3fe1afa80fb9a09775ecfb2b6cc3ba850a2db6",
          "paths": [
            "cli/packages/coding-agent/src/disco/skills/create-repo-skill",
            "cli/packages/coding-agent/src/disco/skills/prepare-repo-skill-env",
            "cli/packages/coding-agent/src/disco/skills/verify-repo-skill",
            "cli/packages/coding-agent/src/disco/skills/extend-repo-skill"
          ],
          "scope": "Portable source/CPU-only preparation, extraction, safe-script disposition, difficult cases and verification adaptation to InferRSI ownership; no DisCo CLI/model run or managed import."
        }
      ],
      "construction": {
        "anchor_kind": "source",
        "distillation_form": "capability-specific",
        "strategy": "arex-portable-meta-skills",
        "status": "partial-candidate",
        "native_import": "not-run",
        "method": "Bounded fork-specific source audit, bundled selected-declaration helper and assertion-backed cases. Native Apple/Metal/model evidence remains blocked; no numerical/performance/skill-efficacy claim."
      },
      "applicability": {
        "scope": "h3-metal FastH3 requested/effective configuration, checkpoint transformation and schedule/RoPE semantics, VSA prefix/partial tiles and dispatch/fallback audit. Common catalog placement is discovery, not CPU inference or Apple qualification.",
        "prerequisites": "Access to the fork-specific source and semantic contracts; native checks additionally need their matching Metal/model resources and separate execution authority.",
        "input_contract": "Source revision/patches, requested parameters and explicitly captured environment controls, checkpoint path/key-family/config identity, requested/aligned frames, latent dimensions, packed prefix segments and sparse-pipeline availability or unknown.",
        "produced_artifact": "A ledger of requested and normalized parameters, ambient overrides, source invariants, counterexamples, observed/unknown facts and the smallest discriminating next check.",
        "failure_modes": "Ignoring ambient overrides, mixing checkpoint identity switches, using global rather than per-head Q/K/V concatenation, pooling padded boundary rows, or double-adding coarse attention can invalidate the semantic audit.",
        "refusal_point": "Stop on conflicting configuration, mixed checkpoint identity, missing resources or the authorized boundary; name the missing native test/fixture and leave it blocked/not_run."
      },
      "limitations": [
        "BLOCKED_REQUIRED_BACKEND: native Apple/Metal, actual FastH3 checkpoint/schedule/sparse parity, audio/video quality, target memory fit, performance and service evidence not_run.",
        "Offline helper audits caller declarations and selected arithmetic only, not engine parameter validity, payload/dtype/conversion equivalence, attention numerics, actual environment or dispatch.",
        "Bounded file/range readset only; full kernels, model/config/weights, encoders/VAEs, device/runtime behavior and external FastVideo conformance are not established.",
        "Native coarse VSA and original-H3 schedule test definitions do not cover sparse fine or FastH3 BF16 schedule execution; no native tests were run.",
        "Key-map and benchmark source scripts are excluded from execution; checked-in reports, source comments and existing measurement documents are not new local evidence.",
        "NO_LICENSE is the actual unauthenticated machine-resolver fallback, not absence of licensing. Inspected MIT source and BSD-3-Clause notices are retained; model rights remain separate/unverified."
      ],
      "provenance_readsets": [
        "references/source-notes.md",
        "references/source-identity.json",
        "references/repo-provenance.md"
      ],
      "consumption_mode": "packaged",
      "recommendations": [
        "Record requested parameters, normalized values and later environment overrides separately, including requested versus aligned frame counts.",
        "Audit checkpoint transformations and schedule consumers beyond tensor names/shapes; tiny permutation fixtures can falsify mappings but do not establish model parity.",
        "Resolve sparse eligibility and the dense-fine-plus-gated-coarse fallback explicitly; preserve unknown pipeline availability."
      ]
    }
---

# Audit h3-metal FastH3 semantics

Use for the fork-specific four-step DiT path, a checkpoint-loader port, confusing
FastH3 flags, or sparse-attention fallback. This is a **source-derived candidate**,
not a generation/benchmark runner. Read the [source and scope](references/source-notes.md)
and [semantic contracts](references/semantic-contracts.md). Native Metal, model,
quality, memory-fit, performance and behavioral skill validation are **not_run**.
General h3.c residency remains with the separately registered
`audit-h3-runtime-residency`; the Apple measurement playbook is context, not new
evidence for these contracts.

## Inputs and output

Record source revision/patches, requested parameters, **explicitly captured**
environment keys, checkpoint path/key-family/config identity, requested/aligned
frames, latent dimensions, packed prefix segments and actual sparse-pipeline
availability (unknown is allowed). Keep model payload integrity, licensing and
native execution separate. Do not collect credentials or the complete environment.

Return a ledger with `requested`, `normalized parameter`, `ambient override`,
`source invariant`, `counterexample`, `observed/unknown`, and `next check`.
Finish with the smallest discriminating check, not an inferred speed/quality claim.

## Procedure

1. **Resolve the effective request.** FastH3 normalizes the API parameters to
   four steps, 50 layers, denoise/core reuse 1, token-reduction parameter 0 and
   SSD streaming 0 before validation. Ordered Ref2VA references are rejected;
   FL2VA first/last-frame anchors are a different input route. Capture ambient
   token-reduction controls: normalization does **not** erase their later effect.
   Record both requested and aligned frame counts; requested 49 aligns to 56.
2. **Check checkpoint identity before mapping.** The DiT's path-substring switch
   and schedule's key-presence switch differ. Identify both, reject mixed-family
   assumptions and inspect the complete intended config/schema. Matching tensor
   names/shapes or an inferred header is not conversion, dtype or payload proof.
3. **Audit transformations, not just names.** Separate Q/K/V tensors must become
   per-head Q/K/V groups, not one global Q-then-K-then-V concatenation. Swap FC1
   halves before quantization. Preserve mapped BF16-to-F32 consumers, the BF16
   timestep MLP/materialization order, separate audio/video sigma rows and the
   generated RoPE dependency. Use labeled tiny fixtures to falsify the wrong
   permutation; do not call such a fixture numerical model parity.
4. **Reconstruct VSA membership.** Merge adjacent same-kind prefix segments,
   then split each merged segment into at-most-64-row tiles. Target video uses
   ceil-divided 4×4×4 blocks on the patchified latent grid. Pool real boundary
   rows only. Prefix queries retain every key tile; video queries retain all
   prefix keys plus top-k video keys. Preserve score-descending/index-ascending
   ties, row/head-major distinctions and scatter order.
5. **Establish actual dispatch.** Top-k uses double-precision arithmetic; 120
   video tiles yield 12, not the float32 counterexample's 13. Sparse fine requires
   an available pipeline, no sparse-disable environment key, and a full sequence.
   The disable key's **presence**, even value `0`, disables it. Sparse fine already
   includes gated coarse; fallback is **dense fine plus gated coarse**, not base
   H3 and not a reason to add coarse twice. Unknown pipeline availability stays
   unknown. Check the [failure table](references/troubleshooting.md).
6. **Run only the authorized layer.** The bundled
   [offline audit](scripts/audit_fasth3.py) accepts a caller-declared JSON object
   and performs selected configuration/tile arithmetic, without probing this
   machine, loading weights or running source scripts. Its
   [input/output contract](references/preflight.md) includes executable examples
   and counterchecks. Native candidates and required resources are classified in
   the [source notes](references/source-notes.md#native-candidates-and-script-dispositions).
   No CPU helper replaces their missing Apple/Metal/model evidence.

## Stop and report

Stop at conflicting configuration, mixed checkpoint identity, missing resources
or the authorized boundary. Name the next native test/fixture needed and report
it as blocked/not_run, not passing. The key-map and benchmark scripts were
inspected but are **not** bundled execution dependencies. Reading this procedure
does not authorize downloading, conversion, generation, benchmarks, upstream
publication or candidate promotion. Missing acceptance evidence is INCONCLUSIVE.

The [provenance and licensing note](references/repo-provenance.md) explains why
the machine-resolver fallback `NO_LICENSE` does not negate the inspected MIT
source license or the retained BSD-3-Clause component notice.
