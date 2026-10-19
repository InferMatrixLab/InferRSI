# 并行与实现边界

拓扑调整、解耦、模型集成、注意力后端或内核工作时读取，并结合[验证参考](tuning-and-validation.md)。

## 拓扑是一项契约

| 维度 | 本快照中的含义 | 必须观测 |
|---|---|---|
| TP | 模型张量切分（`--tp-size`） | 权重/head 整除关系、各 rank 内存和集合通信成本 |
| 副本 DP | 独立模型副本（`--dp-size`） | 路由均衡、每副本容量、总硬件 |
| 注意力 DP | TP 组内的注意力分组，每组一个 scheduler，FFN 仍为 TP（`--attn-dp-size`） | 通信组参与、prefill/decode 不均、padding/通信 |
| EP | 专家分布（`--ep-size`）及所选 MoE all-to-all/runner 后端 | 专家负载倾斜、每专家 token、dispatch/combine 正确性、网络 |
| PD | 分离 prefill/decode 角色（`--disaggregation-mode`）及传输后端 | bootstrap 身份、布局一致、KV 分配/传输、超时与失败生命周期 |

TP/DP 声明明确区分副本 DP 与注意力 DP。旧 `--dp-size N --enable-dp-attention` 会映射为注意力 DP，并重置副本 DP；优先使用当前明确参数，并检查本地兼容性钩子。EP 不能替代注意力 TP。所有混合拓扑不存在通用的相乘公式，应验证实际模型与通信组构造。[E14](source-map.md#e14)、[E15](source-map.md#e15)、[E16](source-map.md#e16)、[E38](source-map.md#e38)

PD 可以隔离 prefill 对 decode 的干扰，也会增加传输/路由成本与资源碎片。与相同总硬件预算的共置基线比较。当前 `prefill_complete` decode 分配策略要求两端一致；预留等到 prefill 完成，且实现有明确后端/布局/特性限制。该策略可能延长 prefill 侧 KV 持有时间并失去传输重叠。选择前读取策略校验器，不将其当成通用加速参数。[E17](source-map.md#e17)

启动分布式任务前，画出进程/rank 所有权，注明两端模型/tokenizer 版本、dtype/KV 布局、page size 和传输方式。测试不均匀负载、空闲 rank、完成/取消以及传输失败。超时需要诊断，不是增大所有 timeout 的理由。

## 配置修改

本版本保留原始 `ServerArgs` 输入，通过 `publish` 将生效配置投影到命名空间配置对象。运行时决策读取相应 accessor（`get_schedule`、`get_memory`、`get_exec` 等）；具名 override 路径记录生效修改。每个 runner 的差异应属于该 runner/构造参数，不泄漏到进程全局配置对象。修改这些边界前先阅读完整原生 `sglang-runtime-context` 技能。[E21](source-map.md#e21)

现有参数调整已支持设置。新增配置字段或策略分支属于实现修改，需要更新声明、解析、消费方、文档和测试。新优化器、传输协议或调度算法在不变量与评估建立前属于研究扩展。

## 模型与注意力后端

模型注册表扫描各模块的 `EntryClass`，支持显式外部注册，并报告导入/架构失败。从语义接近的模型开始，再验证配置/架构身份、RoPE/位置和注意力语义、权重名称及 TP 分片、logits、量化和必要的多模态 token 展开。不要静默覆盖已有架构注册。指南中的“一个模型文件”是入口，不证明所有架构只需要修改一个文件。[E18](source-map.md#e18)、[E37](source-map.md#e37)

注意力实现通过注册工厂选择。针对 prefill、decode、verify、图重放及相关 KV 布局，跟踪所选后端的真实规划和前向路径。对照参考检查 dtype、head dimension、mask/window、张量 stride、位置编码和 cache-write 语义。注册成功不代表后端适用于所有模型。[E19](source-map.md#e19)、[E05](source-map.md#e05)

## 内核

仓库公共可调用内核位于 `sglang.kernels.ops.<group>`，共享 JIT 基础设施在 `sglang.kernels.jit`，AOT wheel 保留自己的 API。旧 `sglang.jit_kernel` 路径已经移除。按计算职责分组，将模型特定调优数据留在对应组内。通信组、通信 buffer 所有权和模型分发仍放在 `srt`。[E20](source-map.md#e20)

按情况使用延迟 `KernelSpec` 元数据或现有 `BaseFusedOp` 契约。注明支持的设备/架构与输入契约；后端目录不等于经过基准验证的最优选择排名。保留数值参考，测试形状、dtype、stride、边界尺寸、aliasing 和 capture/replay。迁移时同步更新运行时 import、延迟 target、调优路径、测试和 CI 注册。[E20](source-map.md#e20)、[E22](source-map.md#e22)

正确性测试放在 `test/registered/kernels/ops/<group>/`，微基准放在 `test/registered/kernels/benchmark/<group>/`，CPU 目录检查放在 `test/registered/unit/kernels/`。运行时集成测试保留在相应子系统，即便需要 GPU 分配。注册真实测试入口并传播退出码，确保 CI 能报告失败。[E23](source-map.md#e23)

## 按改动类别验收

| 改动 | 验收前最低证据 |
|---|---|
| 现有拓扑/配置 | 参数解析与兼容性验证；生效配置；目标硬件运行；输出一致性和 SLO 对比 |
| 模型/后端/内核实现 | 定向数值/logit 测试；cache/graph 模式；分片与权重加载检查；端到端质量和负载基准 |
| 研究扩展 | 明确的不变量/算法论证；基线和消融；失败场景；有限实验预算；声明范围内的正确性与性能 |

必要场景无法测试时，将结论收窄到已验证范围并说明剩余门槛。不从单设备微基准泛化到生产服务。
