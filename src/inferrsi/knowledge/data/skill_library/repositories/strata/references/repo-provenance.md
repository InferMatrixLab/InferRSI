# Provenance and refresh boundary

This is a source-grounded candidate skill, not a certified engine release. The source CMake project version is **0.1.44.1**. `packages` is empty because Strata has no inspected installed Python distribution; its `setup.py` is an application installer. Native GPU compilation, model execution, numerical equivalence and performance were not validated during construction.

The method follows AREX-Skill's portable `distill-ml-knowledge` direct workflow, with repository graph conventions and selected `verify-repo-skill` checks. No DisCo CLI generation or managed import is claimed. The portable profile retains normal skill discovery rather than AREX's managed router-only visibility; it needs adaptation before a DisCo managed import.

AREX source: https://github.com/VectorSpaceLab/AREX-Skill/tree/ac3fe1afa80fb9a09775ecfb2b6cc3ba850a2db6

```json
{
  "schema": "disco.repo-provenance.v1",
  "generated_at_utc": "2026-10-14T02:49:43Z",
  "repository": {
    "name": "Strata",
    "remote_url": "https://github.com/Niko1221/Strata",
    "vcs": "git",
    "branch": "main",
    "tag": null,
    "commit": "296b59d2f73c8f04a805df29c2fa97655adace78",
    "working_tree": "clean",
    "dirty_paths": []
  },
  "packages": [],
  "evidence": {
    "source_roots": [
      "src/program",
      "src/core",
      "src/kernels",
      "src/prefill",
      "src/qwen35",
      "include/strata",
      "serve"
    ],
    "docs": [
      "docs/DETAILS.md",
      "docs/BATCHING.md",
      "docs/MULTI_GPU.md",
      "docs/VRAM_ELASTIC.md",
      "docs/QUANTS.md"
    ],
    "examples": [
      "tools/strata_bench.py",
      "tools/ab_engine.py",
      "tools/needle_bench.py"
    ],
    "tests": [
      "tools/test_setup_amd.py",
      "tools/test_setup_choices.py",
      "tools/test_setup_pins.py",
      "tools/test_strata_bench.py"
    ],
    "configs": [
      "CMakeLists.txt",
      "requirements.txt"
    ]
  }
}
```

## Refresh

Compare the target checkout's commit, dirty state, model dispatcher, option parser, backend gates and build targets with this snapshot. A changed commit is a reason to recheck affected claims, not proof that everything is invalid. Prefer implementation over a simplified README; do not copy Flash-Next dimensions into Qwen3.6.

Source paths above are provenance and native-test evidence. The skill's reasoning, tuning procedure and CSV helper are bundled and do not need the construction checkout. Building or modifying an engine and running its native tests naturally require a separately supplied target source tree and, for GPU tests, hardware and weights. This package does not bundle model weights or an engine binary.

The root and leaf `license: MIT` values were resolved through the GitHub license API at the source commit. Model weights and third-party components have their own licenses; the repository-level field does not override them.
