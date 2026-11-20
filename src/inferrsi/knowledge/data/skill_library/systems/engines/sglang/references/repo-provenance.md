# Repository provenance

Read this before applying the graph to a checkout. Refresh the affected evidence when commit, dirty paths, package metadata, CLI declarations or implementation ownership differ.

## Snapshot

```json
{
  "schema": "disco.repo-provenance.v1",
  "generated_at_utc": "2026-10-14T03:51:09Z",
  "repository": {
    "name": "sglang",
    "remote_url": "https://github.com/sgl-project/sglang",
    "vcs": "git",
    "branch": "main",
    "tag": null,
    "commit": "16176278d0180f1a1a578e53e6eef432577876c2",
    "working_tree": "clean",
    "dirty_paths": []
  },
  "packages": [
    {
      "name": "sglang",
      "version": null,
      "import_names": [
        "sglang"
      ]
    }
  ],
  "evidence": {
    "source_roots": [
      "python/sglang/srt",
      "python/sglang/kernels",
      "python/sglang/benchmark"
    ],
    "docs": [
      "docs/docs",
      "test/README.md",
      ".agents/skills"
    ],
    "examples": [],
    "tests": [
      "test/registered/unit",
      "test/registered/kernels"
    ],
    "configs": [
      "python/pyproject.toml",
      "python/sglang/srt/arg_groups/fields"
    ]
  },
  "version_note": "Dynamic setuptools-scm version; shallow source checkout has no exact version tag or installed distribution. 0.0.0.dev0 fallback is not a release claim.",
  "source_license": {
    "spdx": "Apache-2.0",
    "path": "LICENSE",
    "url": "https://github.com/sgl-project/sglang/blob/16176278d0180f1a1a578e53e6eef432577876c2/LICENSE#L1-L25"
  },
  "dependency_snapshot": {
    "torch": "2.14.1",
    "transformers": "5.19.0",
    "flashinfer_python[cu13]": "0.7.1",
    "sglang-kernel": "0.4.9",
    "xgrammar": "0.2.7",
    "sgl-deep-ep": "0.1.2.post1",
    "sgl-deep-gemm": "0.2.2"
  },
  "verification_status": "portable-candidate; static/source/lightweight checks only; GPU/runtime gates unverified"
}
```

Source license is Apache-2.0; the complete upstream license is retained as [LICENSE](../LICENSE). Model weights, external kernel packages and storage backends have their own licenses and compatibility boundaries. Source dependency pins are declarations, not packages installed or validated in this extraction environment. Read [source evidence](source-map.md) and [native candidates](native-candidates.md).
