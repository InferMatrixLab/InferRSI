# 第五类候选：服务配置与运行时优化

**首选任务：固定模型、精度、请求流和硬件资源，让 Agent 优化服务配置，在质量约束下改善服务指标。**
本页是 2026-11-04 的源码调研与任务设计，尚未适配或执行；硬件未定，不报告性能收益或 Agent 能力提升。
它考察服务配置、批处理和运行时行为，与修改单个 kernel 的题目分开；采用时沿用已有 Workbench，不复制另一套 runner。

## 任务要解决什么问题

用户给定模型与典型请求流，原配置可能让长输入响应慢、长输出生成慢，或高并发时排队严重。
Agent 先运行基线和 profiling，再调整声明允许的配置，提交可复现的 launcher；工具独立验收质量和服务性能。
任务允许直接使用目标项目的 benchmark，不要求真实用户的模型先进入固定题库。

| 项目 | 拟定规则 |
| --- | --- |
| 首个场景 | 从长输入、长输出、高负载中选一个，以实际模型与可用环境决定，不一次覆盖全部 |
| 固定内容 | 模型与 tokenizer 身份、权重/精度、输入与到达序列、输出长度规则、质量数据、资源和评测版本 |
| Agent 产物 | 首选 `start_server.sh` 或等价 launcher；若明确允许修改运行时，则单列提交 repo patch |
| 可改范围 | 经任务声明的 batching、prefill、并发或缓存配置；配置题和源码策略题分开比较 |
| 不可改内容 | 受信评测器、请求工作量、质量标准和资源额度；不能少处理请求、截短输出或换模型来获得分数 |
| 基线 | 固定版本服务引擎的明确配置；必须经过相同质量检查和测量流程 |
| 主指标 | 按目标选择 TTFT、decode 吞吐或满足 SLO 的 goodput；方向、单位和阈值由该实验冻结 |
| 辅助指标 | 错误/超时率、完成请求数、实际输出长度、ITL/TPOT、尾延迟、资源使用及原始逐请求记录 |

## 首选参考：InferenceBench

固定源码为 `aisa-group/InferenceBench` @ `108ec747fab0bd92fd9de501f62157d074c50ed5`，Apache-2.0。
[README](https://github.com/aisa-group/InferenceBench/blob/108ec747fab0bd92fd9de501f62157d074c50ed5/README.md) 明确：Agent 在固定时间预算内写 launcher，最终在 fresh container 测量，并与 PyTorch 参考比较答案质量。
它区分输入密集、输出密集、高负载和综合场景，还提供相同时间预算的 random/TPE/SMAC 配置搜索基线。
这比仅测算子速度更接近 InferRSI 要支持的服务目标；采用的是任务设计和验收分工。

本页首版固定模型精度、缩小可调配置，是拟定的派生任务边界。上游允许更开放的框架、量化和运行时选择；以后扩大这些范围时，需要相应质量与资源验收，不能把本页限制说成上游规则。

- [场景 A 定义](https://github.com/aisa-group/InferenceBench/blob/108ec747fab0bd92fd9de501f62157d074c50ed5/src/eval/tasks/inference_scenario_a_input_heavy/scenario.json)：输入/输出长度、请求数、并发和负载模式均显式声明。
- [工作区规则](https://github.com/aisa-group/InferenceBench/blob/108ec747fab0bd92fd9de501f62157d074c50ed5/src/eval/tasks/_shared/workspace_conventions.txt)：launcher 可编辑，测试入口与评测产物由 benchmark 持有。
- [质量检查](https://github.com/aisa-group/InferenceBench/blob/108ec747fab0bd92fd9de501f62157d074c50ed5/src/eval/inference/quality_gate.py)：核对质量样本完整性、参考准确率与声明门槛；答案质量不是耗时指标的副产品。
- [运行入口](https://github.com/aisa-group/InferenceBench/blob/108ec747fab0bd92fd9de501f62157d074c50ed5/src/eval/inference/runner.py)：分别保留速度、质量及执行完整性结果；未合格结果不能作为有效改进。

原生环境需要 H100 80 GB 或 A100、模型和数据缓存、Apptainer；完整流程还有 Claude 裁判审查捷径。
不把这些平台依赖、付费裁判或论文默认阈值整体搬入 InferRSI。模型权重与数据许可也须另行核对。
development/evaluation seed 分开可减少调参泄漏，但同一公开任务换 seed 不自动形成独立能力验证集。

## 备用与辅助来源

| 来源、固定版本及许可 | 具体借鉴 | 不能据此声称什么 |
| --- | --- | --- |
| [llama.cpp / llama-bench](https://github.com/ggml-org/llama.cpp/blob/149f5641b931aaf33697d70f9abc90c3e5300247/tools/llama-bench/README.md) @ `149f5641b931aaf33697d70f9abc90c3e5300247`；MIT | 硬件未定时的 CPU 备用：固定模型，调整 threads、batch、ubatch；复用 warmup、重复样本及 JSON 输出 | 性能 benchmark 自身不提供完整质量 oracle；采用前须补输出/logit 或任务质量验收，CPU 结果不代表加速器 |
| [vllm-evolve](https://github.com/JiusiServe/vllm-evolve/blob/43cc82c2c649699fb166339f85de2c8f79f2db4e/README.md) @ `43cc82c2c649699fb166339f85de2c8f79f2db4e`；[LICENSE 正文 Apache-2.0](https://github.com/JiusiServe/vllm-evolve/blob/43cc82c2c649699fb166339f85de2c8f79f2db4e/LICENSE) | 窄策略题、SLO goodput、多 seed 比较，以及候选策略实际被加载/调用的检查 | 当前原生后端是 vLLM；simulation、更多 KV/routing 目标仍是 roadmap，不能当成现成通用模拟器 |
| [NVIDIA/SWE-Serve](https://github.com/NVIDIA/swe-serve/blob/84d8fd92739a4a76ceddba56e5a70605921c4ad2/README.md) @ `84d8fd92739a4a76ceddba56e5a70605921c4ad2`；Apache-2.0 | 生产工程任务、独立 verifier、参考修复/no-op 控制；可辅助检验运行时状态和容量逻辑 | 53 题以工程正确性为目标；任务名称含 perf 不代表有速度评分，不能替代本类的性能验收 |

vllm-evolve 的 [plugin_template.py](https://github.com/JiusiServe/vllm-evolve/blob/43cc82c2c649699fb166339f85de2c8f79f2db4e/targets/scheduling/plugin_template.py) 主要按策略结果重排 FCFS waiting deque；priority heap 会跳过。
`invoked` 只证明调用，`reordered` 才表明 admission 顺序改变；两者都不直接证明收益。其 [evaluator](https://github.com/JiusiServe/vllm-evolve/blob/43cc82c2c649699fb166339f85de2c8f79f2db4e/src/vllm_evolve/bench/evaluator.py) 拒绝无法证明插件被调用的性能结果。
SWE-Serve 的 [adaptive-allocation-safety 评分器](https://github.com/NVIDIA/swe-serve/blob/84d8fd92739a4a76ceddba56e5a70605921c4ad2/tasks/ss-sgl-adaptive-allocation-safety/tests/score.py) 仅在全部 F2P/P2P 节点通过后给 1 分，无速度评分；CPU 任务也可能要求较大内存和容器空间。

## 与现有 RSI 的接入流程

1. 在目标环境固定任务、模型、输入、质量标准和资源；准备可审核的服务启动、停止、质量及测量脚本。
2. 运行基线并独立 profiling：保留队列、prefill/decode 分段或设备 trace，说明所改配置针对哪个观测瓶颈。
3. Agent 提交 launcher 或声明允许的 patch；记录真实产物身份和全部尝试，不接受文字自报成绩。
4. 受信入口确认产物实际生效，执行质量检查，再组织正式性能比较；profiling 开销不混入计时。
5. 将 baseline/candidate/validation 脚本接到已有 Workbench，保留样本和报告；主 Agent 引用证据决定下一步。

上述是待适配流程，不能据此声称现有通用 runner 自动先验质量再计时；它当前在测量后执行独立 validation。
质量预检应显式接入受信脚本；最终质量门槛仍需保留。服务生命周期由审核后的目标脚本处理，不另建执行平台。
独立执行 Agent 产物的环境与权限仍需资格验证，当前 NumPy 产物 sandbox 不能直接承担任意服务源码。

## 必须完成的验证与当前状态

| 验证 | 需要保留的证据 |
| --- | --- |
| 质量控制 | 正常基线通过；损坏输出、漏请求、超时或实际输出长度不足被拒绝；基线/参考缺失保持证据不足 |
| 生效检查 | 实际进程、引擎/模型/配置身份与候选匹配；改变 launcher 却没有生效的情况不能记作候选收益 |
| no-op 对照 | 同代码同配置重复比较，检查漂移与噪声；不能因一次测量差异就宣称改进 |
| treatment 对照 | 预先声明一个会改变执行行为的配置，确认行为变化，并报告性能结果；不预设该配置一定更快 |
| 结果使用 | 一份从 profile、假设、产物、质量、计时到主 Agent 决定的完整记录，保留负结果和不确定性 |
| 能力评测 | 另行固定 Agent/skill 条件、预算与任务集；单个 launcher 变快不能直接归因于 skill 或搜索策略 |

目前完成源码、许可与接口设计调研；未选定模型、硬件、质量数据或性能门槛，未新增 adapter，未运行上述控制。
下一实施顺序：确定一个可用环境和场景 → 资格验证基线与质量检查 → 接已有 Workbench → 运行上述控制 → 再做真实 Agent 对照。
