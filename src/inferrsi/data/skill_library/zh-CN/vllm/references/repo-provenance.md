# 仓库来源

权威快照为 [repo-provenance.json](repo-provenance.json)，schema 为 `disco.repo-provenance.v1`；固定行号证据在 [evidence-map.json](evidence-map.json)。[repo-routing-metadata.json](repo-routing-metadata.json) 使用 AREX taxonomy 的原始分类契约。

- 来源：`vllm-project/vllm`，`main` 的干净浅克隆，提交 `2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5`，检查日期 2026-10-14。未观察到精确 release tag，浅历史不能证明最新发布版本。
- 包版本为 **unknown/null**：元数据使用动态 SCM 版本，本克隆没有构建安装包。缺少生成版本元数据时，`vllm/version.py` 回退为 `dev`。不能把回退值或其他本地安装包当成发布版本。[package](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/pyproject.toml#L1-L40) [version](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/version.py#L1-L12)
- Python 要求 `>=3.11,<3.15`。构建及 CUDA 依赖固定 `torch==2.13.0`；CUDA 另固定 `flashinfer-python==0.7.0.post1`。公共依赖包含 `transformers>=5.16.1,<5.20.0` 和 `compressed-tensors==0.17.0`。这些是源码事实，不是已验证安装矩阵。[package](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/pyproject.toml#L1-L40) [cuda](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/requirements/cuda.txt#L1-L31) [common](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/requirements/common.txt#L1-L46)
- 许可证：已在包元数据与 LICENSE 核实 Apache-2.0。原始上游许可证打包于 [LICENSE](../LICENSE)。[license](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/LICENSE#L1-L18)
- 旧 AREX 技能固定 `183a430c137db3d5cd0b9025b816f26ee87328e7`，并记录私有 CPU 构建 `0.1.dev1+g183a430c1.cpu`；二者均不当作本快照运行版本。其 Python 3.10–3.14 描述与当前元数据冲突。旧技能宽泛的 API 操作图和 helper 只用于范围参考，没有复制或假定其仍适用。

本次有意选取：V1 iteration/scheduler、KV/prefix、attention selector、parallel/speculative/transfer/compile/cache 配置、量化注册表、benchmark parsers、metrics 与代表测试。完整模型族、所有 backend/kernel、API payload、前端插件、训练及每种 connector 均不覆盖。源码/文档可能包含过渡性说明；架构参考专门指出历史 PagedAttention 警告和更细 hybrid prefix match 行为。

提交、工作树、config/CLI 字段、selector、connector 生命周期、依赖或测试改变时，刷新受影响结论并重新验证。本候选没有导入 live skills，也没有完成 DisCo 验证/导入验收。GPU 推理、原生 engine tests、CLI import、网络传输及实测性能仍未验证。
