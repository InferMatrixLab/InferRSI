# 通信：复用真实测量底座，单独定义可优化实现

**任务例子：在固定多卡拓扑、消息大小和数据类型下，Agent 改进 AllReduce 实现或允许的配置，保持所有 rank 的归约结果正确，并减少真实通信耗时。**

当前状态：设计候选；本次没有新增编译、通信执行或设备资格。硬件未确定，因此只确定来源、候选边界和验收方法，不发布性能结论。

## 放在现有 SearchSpace 的哪里

引用既有 [SearchSpace Matrix](../../../searchspace-matrix.md) 的 Communication/Network 与相应加速器资源说明，不建立新的权威分类。实际归属取决于瓶颈：同机 GPU 互连实验不能自动充当跨节点网络覆盖。

区分通信原语性能、通信/计算重叠和完整服务收益。前者可从单个 collective 开始；重叠必须检查依赖及端到端阶段耗时；服务收益仍需要真实工作负载验收。

## 固定来源与采用范围

| 来源 | 固定身份、材料与本次决定 |
| --- | --- |
| NVIDIA nccl-tests | commit `afd59abab774a6a4b492eb344bd0c845a0b7bb4d`；[BSD-3-Clause](https://github.com/NVIDIA/nccl-tests/blob/afd59abab774a6a4b492eb344bd0c845a0b7bb4d/LICENSE.txt)；[README](https://github.com/NVIDIA/nccl-tests/blob/afd59abab774a6a4b492eb344bd0c845a0b7bb4d/README.md)、[AllReduce](https://github.com/NVIDIA/nccl-tests/blob/afd59abab774a6a4b492eb344bd0c845a0b7bb4d/src/all_reduce.cu)。作为正确性与真实性能测量底座，不能把跑一次硬件测试等同于给 Agent 一道优化题 |
| MSCCL++ | commit `f5643de98b0c174baa3af2b2e6126f93dd07dc06`；[MIT](https://github.com/microsoft/mscclpp/blob/f5643de98b0c174baa3af2b2e6126f93dd07dc06/LICENSE)；[AllReduce candidate/预期结果](https://github.com/microsoft/mscclpp/blob/f5643de98b0c174baa3af2b2e6126f93dd07dc06/test/mscclpp-test/allreduce_test.cu)、[测试框架](https://github.com/microsoft/mscclpp/blob/f5643de98b0c174baa3af2b2e6126f93dd07dc06/test/README.md)。作为可修改通信算法、channel 与 pipeline 的候选来源 |
| MSCCL-tools | commit `030a750fc56e03fb863ffe48268672d84d4cdc7b`；[MIT](https://github.com/microsoft/msccl-tools/blob/030a750fc56e03fb863ffe48268672d84d4cdc7b/LICENSE)；[DSL 及 Check 测试](https://github.com/microsoft/msccl-tools/blob/030a750fc56e03fb863ffe48268672d84d4cdc7b/tests/test_language.py)。可借鉴通信计划接口和 CPU 符号检查，不作为无设备的性能替身 |

方法参考：[MSCCLang 论文](https://arxiv.org/abs/2201.11840)解释拓扑与 collective DSL；[MSCCL++ 论文](https://arxiv.org/abs/2504.09014)解释细粒度通信抽象。这里采用接口设计，不复述作者数字为本地结果。

## Agent 可以改什么

首题在设备明确后从以下两种候选边界选一种，并在实验开始前固定，不能一次混改所有层：

- **配置题：** 使用固定通信库/二进制，Agent 提交被允许的算法、协议或调度配置。允许项必须经实际版本核对，不能修改 rank 数、消息量、正确性检查或测量命令。
- **实现题：** 从 MSCCL++ 的指定实现出发，修改通信算法或 pipeline；baseline、输入、预期结果生成和报告器保持受保护。

不可用空操作、跳过 rank、减少有效数据、关闭校验或只提交“带宽提高”的文字作为结果。更换通信库、拓扑、数据布局或精度会改变实验条件，需显式新任务/比较身份。

## 正确性、测量与 profiling

正确性需要所有参与 rank 完成，返回与受信参考相符的数据；覆盖不同消息尺寸、边界/非整块输入，以及该实现声明支持的 in-place/out-of-place 模式和数据类型。

nccl-tests 有独立校验路径与 `--check`；冻结时不得用零次检查获得合格结果。MSCCL++ AllReduce 测试在 host 生成 expected buffer，可作为适配来源；不能把候选自身返回的通过标记当 oracle。

设备测量固定进程/rank 映射、拓扑、软件版本、消息大小、dtype、warmup、重复次数、同步/graph 模式和计时边界。保留原始各次测量及失败，不挑最好一次。

报告 latency、algbw、busbw 时保留各自定义；busbw 是 collective 相关归一化，不是任意多 rank 带宽简单相加。CPU launch 时间与设备完成时间不能混用。

nccl-tests 此固定版本支持 JSON 和每次 CUDA event 计时；per-iteration 模式与 graph capture 的约束需按原文保留。上游可输出样本不等于我们已验证测量稳定性。

Profiling 单独查看各 rank 时间线、同步等待和暴露的通信时间。重叠实验应保留依赖、数据一致性及总阶段耗时，不能把各 stream 时长相加后声称加速。

## 无硬件时可以做什么

MSCCL-tools 的 CPU `Check()` 根据 chunk 来源和归约成员检查计划语义，可验证 AllGather/AllReduce 调度是否完成规定操作。

它不证明真实数据类型数值误差、GPU 执行、跨进程同步或链路性能。计划步数、传输量或模型估计必须标注为模型指标，不能换算成已实测 latency/bandwidth。

nccl-tests 的 CUDA/NCCL 运行以及 MSCCL++ 的 CUDA/ROCm 路径均需实际环境；多进程/跨节点场景还涉及 MPI、设备和网络。未具备这些条件时保留“未执行”，不提供 CPU fallback 性能分数。

## 怎样接入现有 InferRSI

使用目标拥有的构建、启动和解析脚本，把正确性命令与 baseline/candidate 测量命令接入既有 RunSpec/Workbench。保留进程退出状态、超时、原始输出、二进制/源码/配置身份及环境记录。

通用 Workbench 不会替代多 rank 启停、远端部署、拓扑资格或输出质量检查；这些须由目标脚本明确承担。现有 `numpy-axis1-v2` 和正式内置题 adapter 也不能直接执行通信题。

若之后接 SkillEval，两臂使用同一题目和测量规则，保留实际候选及完整成本；设备产物的执行隔离与生产 Agent 权限分别验证，不沿用 CPU sandbox 通过来推断 GPU 隔离。

## 最小资格实验与选择理由

1. 环境就绪后，运行固定 baseline 及已知正确实现，核对全部 rank、输入/输出和测量边界。
2. 以漏 rank、错误归约、遗漏尾部数据和缺失输出为负控制，确认独立验收拒绝；超时或设备不可用记证据不足。
3. 先跑同码/同配置对照，检验噪声和重复性；再比较候选，留存失败和原始样本，不以通用阈值代替具体实验约定。
4. 重叠与服务收益分别做额外实验，不能由单个 collective 的数字推导。

优先采用 nccl-tests 的成熟测量和 MSCCL++ 的明确可改对象，避免重建通信平台。暂不把旧 MSCCL runtime 整体移植为默认依赖，也不在硬件未定时同时实现 CUDA、ROCm、NPU 三条执行链。
