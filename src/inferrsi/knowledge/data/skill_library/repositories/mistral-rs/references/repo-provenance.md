# Repository and method provenance

Use this retained snapshot to judge freshness, not an unversioned latest URL.

```json
{
  "schema": "disco.repo-provenance.v1",
  "generated_at_utc": "2026-10-28T11:08:59Z",
  "repository": {
    "name": "mistral.rs",
    "remote_url": "https://github.com/EricLBuehler/mistral.rs",
    "vcs": "git", "branch": "master", "tag": null,
    "commit": "9459891e7697238225885518119682ac8209a612",
    "working_tree": "clean", "dirty_paths": []
  },
  "packages": [{"name":"mistralrs-paged-attn","version":"0.9.5","import_names":[]}],
  "evidence": {
    "source_roots":["mistralrs-paged-attn/src/metal","mistralrs-core/src/pipeline","mistralrs-core/src/paged_attention"],
    "docs":["README.md","AGENTS.md"],
    "examples":["examples/python/paged_attention.py"],
    "tests":["mistralrs-paged-attn/tests","mistralrs-core/src/paged_attention/metal_hnd_tests.rs"],
    "configs":["Cargo.toml","Cargo.lock","mistralrs-paged-attn/Cargo.toml"]
  }
}
```

[Structured identity/readset](source-identity.json) owns whole-file hashes and
explicit substantive analysis spans. Hashing a full file does not assert every
kernel/branch was deeply inspected; test definitions are not executions.

Workspace manifests and the paged-attention notice pin Candle
`66a8cf184a5a519671454066b1b9efd446ec9f5c`. The notice also identifies an MLX
ancestor prefix. These are preserved lineage, not an independent audit of
Candle/MLX internals or proof of exact installed native dependencies. No model,
tokenizer, weights or prebuilt artifacts are included/authenticated.

Method: compatible-agent portable use of AREX-Skill
[create/prepare/workflow/verify instructions](https://github.com/VectorSpaceLab/AREX-Skill/tree/ac3fe1afa80fb9a09775ecfb2b6cc3ba850a2db6/cli/packages/coding-agent/src/disco/skills).
Stable-ID author lanes directly wrote decode, prefill and qualification
resources; the main author reconciled the whole graph before verification.
Rust/Metal source plus standard-library support is an explicit partial native
adaptation. No DisCo CLI/model execution or managed DisCo import is claimed;
InferRSI owns packaged discovery and maintained matrices.

Current Linux inspection has Python support for offline helpers but lacks
Cargo/rustc, Swift/Apple SDK and a Metal device. No Rust package/toolchain was
installed, no compiler check or native source test was executed, and no live
Rust API signature was inspected. Source-derived declarations and helper
checks cannot make this a fully ready backend environment or auto-importable
verified engine. The required backend gap remains explicit.

Refresh if source/build/dependency/model/cache contracts change. Recheck source
guards, helper domains, native candidates and license boundaries; do not attach
newer source bytes or results to these retained identities. Upstream source,
local content revision and actual measured runtime revision are distinct.
