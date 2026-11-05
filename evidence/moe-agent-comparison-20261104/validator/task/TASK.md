# 双 NPU：带共享专家的 MoE FFN 完整 forward

目标是在保持结果正确的前提下，缩短两张 Ascend NPU 上完整 MoE FFN forward 的完成时间。输入是每张卡自己的 token，输出仍保留在输入所属卡。这是一层模型计算，不涉及模型下载、训练或 serving。

## 输入与数学语义

实现 `compute(x, params, *, config, group)`，返回与 `x` 相同形状、dtype、设备的输出张量。`group` 是已建立的两 rank HCCL process group；设备和物理卡号由评测器调度，候选不创建或销毁 process group、不修改设备可见性。

- `x`：本 rank 的 `[N_rank, H]` BF16 输入。两个 rank 的内容不同，token 数可能不同，也可能有一个 rank 没有输入。
- `config`：`world_size=2`、`rank`、`num_experts=8`、`experts_per_rank=4`、`hidden`、`intermediate`、`top_k`、`rank_tokens`。只包含结构信息。
- `params.router_weight`：FP32 `[8,H]`；`router_bias`：FP32 `[8]`。
- `params.expert_gate_up`：BF16 `[4,2I,H]`；`expert_down`：BF16 `[4,H,I]`。rank 0 只有 experts 0–3，rank 1 只有 experts 4–7。
- `params.shared_gate_up`：BF16 `[2I,H]`；`shared_down`：BF16 `[H,I]`。共享专家和 router 参数在两卡相同。

对每个 token，以 FP32 计算 `logits = x @ router_weight.T + router_bias`，选择最大的 `top_k` 项，再对选中的 logits 做 softmax 得到权重。每个专家执行 `W_down(silu(W_gate x) * (W_up x))`，其中 `W_gate`、`W_up` 是 `gate_up` 的前后两半。结果是选中专家输出的加权和，再加共享专家的输出。最终输出 BF16，保持本 rank 原始 token 顺序。

不丢 token；没有 dropout、capacity 截断、量化、residual 或额外 norm。生成输入排除了 top-k 边界近似相等的情况，避免以浮点舍入决定不同路由；路由仍必须根据本次输入计算。

## 候选边界

可以更改本实现中的计算、内存布局和通信组织，可以调用现有 PyTorch/torch_npu/HCCL 或自定义 NPU kernel。使用的工具必须来自当前已配置环境，不能更改共享软件安装。

输入和所有参数只读。不得使用评测 seed、输入生成器、oracle、其他 session 的代码或结果；不得根据评测阶段、文件名或计时器选择不同语义；不得省略任何 rank 的工作。不能获取或重建另一 rank 的专家权重并在未计时区内复制，以改变 EP 所有权。不能缓存输入相关的路由、专家计算或最终输出。

参数会变化，张量地址也可能复用。若实现中缓存权重排布或编译结果，必须正确失效；首次建立过程在首次调用中记录，其额外内存也要报告。输入相关工作全部在 `compute` 内。候选不允许外部后台计算、写结果文件、修改评测器或创建脱离评测器生命周期的进程。不得 monkeypatch PyTorch、通信库、oracle 或其他全局运行时状态以影响基线和评测器；本执行器接收经审查的可信源码，不是恶意代码隔离沙箱。

## 验收与计分

评测器使用独立 CPU FP32 数学实现，检查两个 rank 的全部输出、有限性、输入/参数保持和误差。用不同输入、权重变化、top-k=1/2、不等 token 数、空专家以及零输入 rank 检查正确性。数值容差以冻结后的 `task.json` 为准。

计时覆盖 host 调度、数据重排、路由、通信、专家计算、共享专家和输出完成。每次以最慢 rank 的完成时间计分；只提交通信或 kernel 而未完成输出不能获得较短时间。baseline/candidate 在同一组设备交错测量，每次计时输入都变化。各性能 case 的加速比用几何平均汇总，同时保留逐 case 数据；编译、首次调用、搜索墙钟和 token 消耗另报。

性能集合包含三种规模与路由分布，均为 top-k=2：

| Case | 每 rank token 数 | Hidden H | 专家 intermediate I | 路由 |
| --- | --- | --- | --- | --- |
| balanced-small | 64 | 512 | 1024 | 均衡 |
| skewed-medium | 256 | 1024 | 2048 | 偏斜 |
| balanced-large | 1024 | 2048 | 4096 | 均衡 |

每 case 的所有输入和 FP32 oracle 都在开始评测前共同生成，两种实现获得独立但相同的输入张量；避免只有先运行的一方在计时前经历昂贵的 CPU 参考计算。每次计时使用不同输入。探索使用两组 AB/BA 配对、每组 8 个样本，即每个实现每 case 16 个样本；最终复测使用四组、每个实现每 case 32 个样本。额外的小形状边界用例仅检查正确性，不计入速度分数。准备时间和首次调用时间另存；同进程首次调用受共享底层算子缓存影响，不能解释为两个实现各自在全新进程中的冷启动对比。

每个计时输入还配有一个**数值不同、专家数量相同的预热输入**。评测器在 router 权重的零空间加入标准差约 0.3 的噪声，量化为 BF16 后逐 token 检查选中专家集合不变、top-k 边界间隔至少 0.02、输入 RMS 差至少 0.15；不满足时重采样，不退化成原输入、token 排列或微小扰动。这样两种实现可以预热同样的动态专家矩阵形状，避免先执行的一方单独承担新形状的底层算子准备开销。每个预热输入仍需独立数学验收、只读检查和输出清零；预热与正式 oracle 的输出必须相差超过正式容差，防止直接复用预热输出。预热成本单列，不计入 forward 速度分数；输入相关计算和输出缓存仍然禁止。

本题的 baseline 是可读、完整的 AllGather/本地专家/ReduceScatter 实现，已经合并 gate/up 投影，并使用 NPU SwiGLU。它是正常算法基线，不代表 vLLM-Ascend 最新生产实现的性能；对它的加速比不得解释为对 vLLM 服务或整模型的同等加速。

任务结构参考 vLLM-Ascend 的 [AllGather preparation](https://github.com/vllm-project/vllm-ascend/blob/0f85ed44bbbbdc0f0447f83ce62a82a8ad55afb3/vllm_ascend/ops/fused_moe/prepare_finalize.py) 和 [MoE forward](https://github.com/vllm-project/vllm-ascend/blob/0f85ed44bbbbdc0f0447f83ce62a82a8ad55afb3/vllm_ascend/ops/fused_moe/moe_comm_method.py)。本任务的代码是独立编写的最小实现，不依赖整个 vLLM 服务栈。
