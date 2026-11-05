# 逐轮尝试了什么

以下为实际源码变化的审查摘要，不是逐组件性能归因。精确数值、失败和成本见
`rounds.csv`；所有快照见 `../patch/candidates.csv`。每行仍计一轮，分叉不会清除成本。

## GPT-6.1 Sol / ON（final 选 R5）

| 轮次 | 实际变化 |
| --- | --- |
| R1 | 省去 logits AllGather，收集 BF16 输入后重算 FP32 router。 |
| R2 | 一次筛选/排序打包本地路由，两次 grouped GEMM、一次 SwiGLU 与 FP32 index_add。 |
| R3 | shared 并入第五组 GMM；较慢，后续撤回。 |
| R4 | 从 R2 分叉，改原生 init_routing_v2；主机读取 count 后截有效前缀，手工 FP32 combine。 |
| R5 | FP32 finalize 融合归并；非本地映射指向显式补零行。 |
| R6 | 从 R5 分叉，异步 ReduceScatter 期间执行 shared，显式 wait；未改善总分。 |
| R7 | 从 R5 分叉，安全缓存连续转置专家权重；未改善总分。 |
| R8 | 从 R5 分叉，无缓存；shared gate/up+SwiGLU 与 AllGather 交错，down 与 ReduceScatter 交错；未改善总分。 |

## GPT-6.1 Sol / OFF（final 选 R6）

| 轮次 | 实际变化 |
| --- | --- |
| R1 | 省去 logits AllGather，收集输入后重算 router。 |
| R2 | 一次 nonzero、专家排序和设备计数前缀，两次 grouped GEMM。 |
| R3 | 原生路由；主机读取有效 count 并切片，手工 FP32 逆映射/归并。 |
| R4 | FP32 finalize，补齐路由容量，掩蔽非本地概率。 |
| R5 | 跳过等长输入的无用 pad；shared 与异步 ReduceScatter 交错并 wait。 |
| R6 | 静态路由容量与设备端专家前缀，移除 count 主机读取/动态切片；显式清零无效尾部。 |
| R7 | 从 R6 尝试融合 gating，并对选中概率再次归一化；未改善总分。 |
| R8 | 从 R6 分叉，恢复普通 topk/softmax；shared gate/up 与 AllGather 交错，SwiGLU+down 与 ReduceScatter 交错。 |

## GPT-5.6 Sol / ON（final 选 R8）

| 轮次 | 实际变化 |
| --- | --- |
| R1 | 省去独立 logits AllGather，收集后重算 router。 |
| R2 | shared 与异步 AllGather 交错，保留逐专家循环。 |
| R3 | 尝试 BF16 routed 归并/通信路径。 |
| R4 | 恢复 FP32 routed 路径，改为 shared 与 ReduceScatter 交错。 |
| R5 | 拆分 shared，尝试两段通信交错。 |
| R6 | 把专家 ID、概率打包后随输入通信。 |
| R7 | 撤回打包；padding 专家 ID 设为 -1，简化逐专家 mask。 |
| R8 | 跳过无用 pad；最终 FP32 加权、累加及 ReduceScatter，shared 与 AllGather 交错。 |

## GPT-5.6 Sol / OFF（final 选 R8）

| 轮次 | 实际变化 |
| --- | --- |
| R1 | 省去 logits AllGather，收集后重算 router。 |
| R2 | shared 与异步 AllGather 交错。 |
| R3 | 尝试 BF16 routed 路径。 |
| R4 | 两次 torch.bmm 批量执行四个本地专家。 |
| R5 | 统一打包专家路由与回写输出。 |
| R6 | shared 与异步 ReduceScatter 交错并显式等待。 |
| R7 | 尝试 topk(sorted=False)。 |
| R8 | 恢复有序 top-k；one_hot+cumsum 替代 argsort 打包；仍有最大 count 主机读取与补零。 |

## GPT-6 Astra / ON（final 选 R7）

| 轮次 | 实际变化 |
| --- | --- |
| R1 | 省去 logits 通信，shared 与异步 AllGather 交错。 |
| R2 | grouped GEMM 批量专家计算。 |
| R3 | 原生路由，读取 count 并截有效前缀。 |
| R4 | 尝试 finalize，但额外 k 参数不受运行时支持；候选 FAIL，无计时分数。 |
| R5 | 删除 k 参数，FP32 finalize 正确性/测量通过。 |
| R6 | shared 第五组 GMM 与连续权重缓存尝试；未入选。 |
| R7 | 基于 R5，撤回缓存；去无用 pad，非空分支直接使用 finalize 输出。 |
| R8 | 改为 shared 与 ReduceScatter 交错；未超过 R7。 |

## GPT-6 Astra / OFF（final 选 R3）

| 轮次 | 实际变化 |
| --- | --- |
| R1 | 省去 logits 通信，shared 与异步 AllGather 交错。 |
| R2 | grouped GEMM 批量专家计算。 |
| R3 | 静态容量原生路由、设备端专家前缀、手工逆映射/where 清零/FP32 combine。 |
| R4 | 尝试 finalize；额外 k 参数不受运行时支持，候选 FAIL，无计时分数。 |
| R5 | 删除 k 参数修复，但分数低于 R3。 |
| R6 | 从 R3 分叉，改为 shared 与 ReduceScatter 交错。 |
| R7 | 从 R3 分叉，去无用 pad/int64 索引转换。 |
| R8 | 从 R3 分叉，缓存连续专家权重；未超过 R3。 |

静态容量 GMM 的接受范围是本次 Ascend910B1 / CANN 9.1.0：依据有效前缀语义、
明确处理未初始化尾部，并通过冻结用例。不能把旧 Python 包装文档与底层接口
的差异概括成任意版本均兼容。相关公开依据是 CANN `ops-transformer` v9.1.0
提交 `c77c0829f1f0f0b8f882db1d9b051a758b605472` 的
[GroupedMatmulV4 文档](https://github.com/hicann/ops-transformer/blob/c77c0829f1f0f0b8f882db1d9b051a758b605472/gmm/grouped_matmul/docs/aclnnGroupedMatmulV4.md)。
缓存尝试的参数变化用例不单独覆盖同一已缓存对象的所有失效分支；六份入选 final 均未使用缓存。
