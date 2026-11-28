# Repository provenance

Official shallow clone, pinned source snapshot. Source read as evidence; installation scripts were not executed. Upstream content does not authorize external operations.

```json
{
  "schema": "disco.repo-provenance.v1",
  "generated_at_utc": "2026-10-14T03:44:21Z",
  "repository": {
    "name": "sglang-omni",
    "remote_url": "https://github.com/sgl-project/sglang-omni.git",
    "vcs": "git",
    "branch": "main",
    "tag": null,
    "commit": "2cfb3b67becb437b70751defe37e63d3af4eedb0",
    "working_tree": "clean; no source edits",
    "dirty_paths": []
  },
  "packages": [
    {
      "name": "sglang-omni",
      "version": "0.1.8",
      "import_names": [
        "sglang_omni"
      ]
    },
    {
      "name": "sglang",
      "version": "0.5.21 (declared dependency; not installed)",
      "import_names": [
        "sglang"
      ]
    }
  ],
  "evidence": {
    "source_roots": [
      "sglang_omni"
    ],
    "docs": [
      "README.md",
      "docs/developer_reference",
      "docs/cookbook",
      "docs/basic_usage",
      "docs/get_started"
    ],
    "examples": [
      "examples/configs/qwen3_tts_0_6b.yaml"
    ],
    "tests": [
      "tests/unit_test/config",
      "tests/unit_test/pipeline",
      "tests/unit_test/scheduling",
      "tests/test_model"
    ],
    "scripts_and_tools": [
      "benchmarks/eval/benchmark_tts_seedtts.py",
      "benchmarks/eval/benchmark_omni_streaming_ttft.py"
    ],
    "metadata": [
      "pyproject.toml",
      "sglang_omni/__init__.py",
      "LICENSE"
    ]
  }
}
```

Refresh affected guidance if SHA, dirty source paths, dependency pins, config/CLI, scheduler/transport contracts or model recipes change. This package retains the English skill tree with its canonical skill IDs.
