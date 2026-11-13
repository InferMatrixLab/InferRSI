# Provenance

Incremental inspection on 2026-10-22: [abort acknowledgment and deferred transfer reclamation](../sub-skills/omni-validation/references/abort-acknowledgment.md), upstream `18c3bd5d2d4323bc7adca1ac3c465c4a53bbfb6e`. Source archive read only; bounded CODE/TEST-SOURCE evidence, native/model/service validation not_run. The original provenance snapshot below remains applicable to the earlier guide.

```json
{
  "schema": "disco.repo-provenance.v1",
  "generated_at_utc": "2026-10-14T03:50:21.525495+00:00",
  "repository": {
    "name": "vllm-omni",
    "remote_url": "https://github.com/vllm-project/vllm-omni",
    "vcs": "git",
    "branch": "main",
    "tag": null,
    "commit": "52194f24fa42e14d1c5e096f4bea4dc7f95cffa1",
    "working_tree": "clean",
    "dirty_paths": []
  },
  "packages": [],
  "evidence": {
    "source_roots": [
      "vllm_omni"
    ],
    "docs": [
      "docs/getting_started/quickstart.md",
      "docs/configuration/stage_configs.md",
      "docs/user_guide/diffusion/execution_modes.md"
    ],
    "examples": [
      "vllm_omni/deploy/qwen3_omni_moe.yaml"
    ],
    "tests": [
      "tests/config",
      "tests/engine",
      "tests/diffusion",
      "tests/distributed/omni_connectors"
    ],
    "configs": [
      "pyproject.toml",
      "requirements/common.txt"
    ]
  }
}
```

Source package version is dynamic (setuptools-scm); no installed distribution was verified. `pyproject.toml` permits Python >=3.10,<3.14; quickstart uses Linux/Python 3.12 and vLLM 0.31.0. At this SHA common requirements include transformers >=5.13.0,<5.15, diffusers==0.40.0, cache-dit==1.5.0. These are pinned-source facts, not universal installation advice.

Method: AREX-Skill direct distillation, generator commit ac3fe1afa80fb9a09775ecfb2b6cc3ba850a2db6. Existing AREX vllm-omni skill pins 35cacf020c823da56e5ad437128bc4e93a5a3ed1 and vLLM 0.26.0; its package/version guidance was not copied. License Apache-2.0 resolved via AREX license helper and source metadata.

Refresh the evidence when the repository revision, pipeline/schema, CLI, runner, protocol or backend changes. GPU inference, distributed transport and media quality remain unverified.

See [evidence](evidence.md).
