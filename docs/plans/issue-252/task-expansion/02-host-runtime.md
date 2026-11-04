# 候选类别 02：CPU 侧数据处理与运行时开销

状态：2026-11-04 来源检查与任务设计；尚未导入题包、构建环境或运行性能实验。用户已将当前试点指定为 NPU，先完成 [RMSNorm NPU 通路](../npu-pilot.md)；本页保留为后续 CPU 仓库补丁方向，不再是下一项必须交付的试点。

## 要测什么

让 Agent 在真实仓库中发现并减少推理前后的 CPU 开销，同时保持输入输出语义。
若后续开展这一类别，首题建议选择 **大量 added tokens 时的 Tokenizer.encode**。
它关联现有 SearchSpace 中的主机侧处理与运行时优化；具体矩阵归属仍需评审，不据此新增已验证覆盖。
这类题测试真实 repo 的分析和补丁能力；单题结果不代表服务 TTFT 或整个 RSI 能力提升。

## 可核查的题源

| 对象 | 本轮核对结果 |
| --- | --- |
| benchmark | [GSO](https://github.com/gso-bench/gso/blob/32d78b331d59ed689b1238789dc20d36576951c0/README.md)，代码 commit `32d78b331d59ed689b1238789dc20d36576951c0`，MIT |
| 具体任务 | 官方数据中的 `huggingface__tokenizers-076319d`，API 为 `Tokenizer.encode`，4 个测试 |
| 目标仓库 | `huggingface/tokenizers`；目标版本 [LICENSE](https://github.com/huggingface/tokenizers/blob/076319d542f87e9f72db379d7e47b29b1ce7bd87/LICENSE) 为 Apache-2.0 |
| baseline | `fb837b4adb130dfc89104aa09b1ae223da120278`，由官方 expert commit 的 parent 核对 |
| expert | [`076319d542f87e9f72db379d7e47b29b1ce7bd87`](https://github.com/huggingface/tokenizers/commit/076319d542f87e9f72db379d7e47b29b1ce7bd87)，Aho-Corasick 处理大量 added tokens |
| 数据版本 | 已下载并读取 `gso-bench/gso` revision `c2e4f1a58427cccd15e0e542f136bd204fb19284` 的 `data/test-00000-of-00001.parquet`，102 行中该 task ID 唯一、包含 4 个测试；数据许可声明 MIT |
| 来源记录 | [下载与任务行身份](gso-source-audit.json)保留文件 SHA-256、行选择、canonical JSON 哈希及 base/expert 身份；这是源码检查，不是任务执行证据 |

初始发现来自实时 datasets-server；随后以固定 revision 的 parquet 完成任务行复核。正式导入还需归档所选资产及许可，锁定最终派生题包身份。
上游参考改动主要位于 `tokenizers/src/tokenizer/added_vocabulary.rs`，并增加了 Rust 测试。
Agent 从 baseline 开始修改仓库并提交 patch；expert patch 用于评测资格对照，不默认提供给 Agent。

## 输入、正确性和允许改动

GSO 的公开问题脚本使用 GPT-2 tokenizer、约 4000 个 added tokens 和多个文本片段；4 个测试还含其他构造及 BERT tokenizer，不能把问题脚本等同于全部测试。性能区间为编码调用。
当前脚本会下载浮动 `resolve/main/tokenizer.json` 和在线 Gutenberg 语料。导入时必须固定版本与内容哈希，提前准备输入；安装、下载不计入编码耗时。
数据行的 setup 还包含通用系统安装命令及 `upt upgrade` 拼写问题；本轮未执行这些命令，需要单独整理并验证最小可重建环境。
任务应固定 tokenizer、added-token 集、文本及线程条件；允许修改实现，不允许替换 tokenizer 定义、测试、输入或参考结果。

- 保留 GSO 对 token 序列、token IDs、输出数量及长度的比较。
- 复用上游 [added_tokens.rs](https://github.com/huggingface/tokenizers/blob/076319d542f87e9f72db379d7e47b29b1ce7bd87/tokenizers/tests/added_tokens.rs)，覆盖 single_word、lstrip、rstrip、重叠匹配及 offsets。
- 补充不同文本长度、Unicode、空输入、无命中与多命中的条件；具体检查须经 baseline/expert 双方验证。
- 基线输出等价检查与固定语义断言并用。基线结果不是完全独立的实现 oracle，不能把相同输出测试称为全语义证明。
- 同一进程连续处理不同文本，保留输入和结果证据，检查状态缓存或复用结果造成的假改进。

## profiling 与测量流程

1. 准备固定仓库、Rust/Python 构建工具链与数据，验证 baseline 能重建、测试能通过。
2. 独立 profiling：定位 Python/Rust 编码调用的时间；需要原生栈时使用支持 Rust 的 profiler，不能仅凭 cProfile 判断 Rust 内部热点。
3. Agent 写出诊断依据和改法，交付真实 patch；工具审核适用范围并独立验收。
4. 在声明的 CPU、线程、编译选项和工作负载下重复比较，安装和构建时间单独记录。
5. 报告每个工作负载的正确性、原始耗时、波动、版本及预算，再解释是否足以保留候选。

GSO 的 [执行脚本](https://github.com/gso-bench/gso/blob/32d78b331d59ed689b1238789dc20d36576951c0/src/gso/harness/grading/evalscript.py) 对该仓库使用一次外层迭代；不能直接把这一设置当作 RSI 的可靠性能资格。
重复次数和可接受误差来自本次实验的冻结条件，不照搬排行榜分数、阈值或无测量支持的默认值。

## 先证明题目有效，再评 Agent

| 对照 | 需要检查什么 | 本轮状态 |
| --- | --- | --- |
| baseline 对 baseline（A/A） | 同码波动是否让实验错误判断为改进 | 未运行 |
| baseline 对 expert patch | 已知优化在当前输入和机器上是否仍有稳定信号，并通过正确性检查 | 未运行 |
| 故意错误 patch | 省略 added-token 规则、错误 offsets 或复用前次结果会被拒绝 | 待编写、未运行 |
| Agent 候选 | 在前述资格建立后检查正确性与性能，不以代码改动或测试 PASS 代替优化成功 | 未运行 |

[跨机器可靠性研究的数据](https://github.com/chenzhi-cz/performance-optimization-benchmark-reliability/blob/44a1cb86a9f765b0375b4cfb479641f3c19f0774/data/gso_cross_machine_valid_tasks.csv)包含此 task ID；这是作者报告的筛选线索，不是我们的本地资格证明。

## 怎样接入 InferRSI

需要的是 **repo-patch adapter**：固定 baseline checkout，接收并留存 patch，构建候选，调用独立测试和测量脚本，产生 Workbench 可读结果。
此 adapter **尚未实现**；现有 `numpy-axis1-v2` 与 `implementation.py` 入口不能直接承担它。
优先复用现有 Workbench 的外部命令和证据机制；正式 SkillEval 的 patch 交接、执行隔离与报告复核需要另外适配，不将任意生成代码送入可信宿主 worker。
Rust 工具链、历史依赖、容器及原生编译让它的接入成本高于当前 NumPy 题，但仍不要求 GPU；实际可重建性待验证。

## 借鉴与不采用的边界

- [SWE-fficiency TestSpec](https://github.com/swefficiency/swefficiency/blob/12d32a2d6800824a7d84bdb6797b5708e7b7957f/swefficiency/harness/test_spec.py)将 workload、guarding tests 和 profiling 分开，适合作为流程参考；不引入另一套排行榜总分。
- GSO 的 `tokenizers-fc76ad4` 优化 UnigramTrainer.train，属于训练任务；不能因为仓库与推理相关就纳入本类别。
- [ISO-Bench 固定数据说明](https://huggingface.co/datasets/ISO-Bench/ISO-Bench/blob/24ef5d04b4993aca5e0d2cfa64b51cb40fc4cb55/README.md)提供更直接的 vLLM/SGLang repo 任务，可作为后续引擎运行时题源。其数据声明 H100／多 GPU 条件，不能据 CPU 局部测试宣称复现。
- 例如 vLLM [`22d33baca2c0c639cfd45c48e99803e56c3efa74`](https://github.com/vllm-project/vllm/commit/22d33baca2c0c639cfd45c48e99803e56c3efa74)优化单请求的 merge_async_iterators；本轮仅核对官方 diff 身份及实时数据的 H100 标记，未验证该题的性能与 lm-eval 命令。

完成标准是固定来源、可重建环境、可靠对照和真实消费者接入均有证据；本页只完成来源选择与设计。
