# 来源与更新边界

本 Skill 是有源码依据的候选版本，不是已认证的引擎发行版。源码 CMake 项目版本为 **0.1.44.1**。`packages` 为空，因为没有经过检查的已安装 Python distribution，Strata 的 `setup.py` 是应用安装器。本次构建未验证 GPU 编译、模型运行、数值等价或性能。

采用 AREX-Skill 的可移植 `distill-ml-knowledge` direct 流程，结合仓库图结构规范及部分 `verify-repo-skill` 检查。不声称运行过 DisCo CLI 生成或 managed import。本便携版本保留通常的 Skill 发现方式，未采用 AREX managed collection 的仅路由可见策略，导入该集合前需适配。

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

## 更新检查

将目标 checkout 的提交、修改状态、模型分派、参数解析、后端条件和构建目标与此快照比较。提交变化意味着应复查受影响内容，并不表示全部失效。实现优先于简化 README；不能把 Flash-Next 维度套到 Qwen3.6。

上述源码路径用于来源记录和原生测试证据。Skill 的推理知识、调优流程与 CSV 工具已捆绑，不依赖构建时的 checkout。构建或修改引擎、运行原生测试当然需要另行提供目标源码，GPU 测试还需硬件与权重。本包不含模型权重或引擎二进制。

根和子 Skill 的 `license: MIT` 来自固定提交上的 GitHub 许可证 API。模型权重和第三方组件各有许可证，仓库级字段不会覆盖它们。
