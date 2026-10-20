---
name: ascend-distributed-parallel
description: 'Select and validate distributed parallelism strategy on Ascend NPU: topology-aware  card-group selection, USP/CP/TP/PP strategy choice, communication masking setup and  verification, attribution of parallelism gains, and diagnosis of strategies that appear  to activate but have no effect. Covers AlltoAllV defect workaround and HCCL bandwidth  verification.

  '
---

# 分布式并行策略选择与验证

## 卡组拓扑规则（强制前置）

任何多卡运行前必须满足拓扑规则：判据来自 `npu-smi info -t topo` 的互连分域。

- **合法卡组**：
  - 2 卡 = 一对同域相邻卡（topo 显示同 UB/HCCS 域）
  - 4 卡 = 一个完整同域组
  - 8 卡 = 全部卡
  - 跨域拼组**不合法**——若因卡健康需跨域，必须显式注明「非同一互连域、带宽次优」

- **执行要点**（强制四步 smoke 验证）：
  1. 选卡前 `npu-smi info -t topo` 核对目标组内互连为 UB（同域）
  2. `npu-smi info` 核 Health；Alarm 卡弃用；被占用卡不可用
  3. 多卡 run 必须**4 步 smoke 验证 per-step 时长均匀性**（per-step 时长整组均匀抬高约一个量级即 SIGKILL 残留态，须驱动复位或换组；`npu-smi Health=OK` 不能证明组可用）
  4. **卡组变更 = 契约变更**：换卡组后锚点行必须在新卡组同窗重测，不得混用旧卡组数值

## 并行策略一览与选型

| 策略 | 适用场景 | 通信模式 | 关键参数 |
|------|---------|---------|---------|
| Ulysses 并行 (USP) | 多模态扩散模型序列维度切分 | all-to-all | ulysses_size |
| CFG 并行 | classifier-free guidance 开启 | 双分支独立推理 | cfg_parallel |
| 张量并行 (TP) | 单层参数超单卡显存 | all-reduce / all-gather | tp_size |
| 环状序列并行 (RSP) | 长序列通信可被计算掩盖 | P2P 环形传递 | world_size |
| 流水线并行 (PP) | 层数多、单层显存可承受 | send/recv | pp_size |

## USP (Ulysses) 激活要求

**核心机制**：Ulysses 的 all-to-all head-parallel 切头路径**不会自动生效**。仅给 attention processor 设置序列分片时会走非 CP 路径（profile 只有 allGather，无 allToAll）。

**触发条件**（已观测）：必须给每个 `attn.processor._parallel_config` 显式设置 `ParallelConfig(context_parallel_config=cp_cfg)`（注意是 `ParallelConfig` 包装，不是 `ContextParallelConfig`），才会触发 all-to-all 切头路径。

**生效验证**：profile 级证据——`allToAll` 必须出现，不仅是 `allGather`。

## 通信掩盖机制与上限判定

### 分块流水掩盖原理

把集合通信放在独立流（comm stream）上，与计算流上的 AI-core 算子并发执行。分块流水掩盖将一层里的整块通信按头维度切成 `n` 份，逐块「通信 → 计算」形成流水。

### 上限公式与判据

三个关键量（都按每层口径）：

| 量 | 含义 |
|---|---|
| `C` | 通信总量（被掩盖对象）= 被掩盖那一族的 kernel 耗时 ÷ 层数 |
| `F` | 可与之并行的计算量 = 被掩盖侧计算耗时 ÷ 层数 |
| `n` | 分块数（实现参数，必须整除每 rank 本地头数） |

派生量：每块通信 `c = C/n`，每块计算 `f = F/n`。**判据核心是比值 `c/f`（等价 `C/F`）。**

### 情形 1：`f >= c`（等价 `F >= C`）

通信流始终能被计算流喂饱，暴露量 ≈ 填充（第一块通信）：

```
掩盖率上限 = 1 - 1/n
```

此时理想界成立——"切 n 组头最佳掩盖 1-1/n、只暴露 1 组头的通信"。

### 情形 2：`f < c`（等价 `F < C`）

真实上限更低。每块通信都大于该块计算，稳态每块净暴露 `c - f`：

```
暴露下限 ≈ c + (n-1)*(c-f) + drain
掩盖率上限 = 1 - 暴露下限 / C
```

**要点**：
- 稳态项与 `n` 无关：`(n-1)(c-f) = (1-1/n)(C-F)`，所以 `F<C` 时提高 `n` 几乎没收益
- 要提升掩盖率，唯一出路是**压通信分子或抬计算**（量化、减跨岛流量、合并集合、搬独立计算）
- **判定顺序**：先算 `c/f` → 再看实测掩盖率占上限的多少

## 通信掩盖实现要点

生效判据（缺一不可）：

1. 该族算子**次数上升 ≈ n 倍**（次数没变 = 没生效）
2. 侧流 AI-core 核数 = 0
3. `Communication(Not Overlapped)` 下降（列名精确匹配）
4. 产物 md5 与不开时**逐字节一致**（纯置换无规约 ⇒ 掩盖是完全置换）
5. 回退分支需留命中/回退计数器（防止"开了门控但每次都静默回退"）

**下发顺序 = 调度**：同一 communicator 的集合通信按下发顺序串行执行。前向 a2a 全发完再发反向会让反向落在本层计算之后。修法是**软件流水式下发**（把第 g+1 片前向排在 g 片反向之前）。

## AlltoAllV 缺陷与绕过

部分 CANN 版本上 `HcclAlltoAllV`（split 路径）**SIGSEGV**（等分 `HcclAlltoAll` 正常）。

**绕过方案**：**pad + 等分**——把 input 各块 pad 到 `S_PAD`（128 倍数，由全局 `max(out_sizes)` 推导，全 rank 一致），用等分 `HcclAlltoAll(count=S_PAD×row_elems)` 交换，再 slice 各块前 `out_sizes[j]` 行。

**生效判据**：kernel 名从 `hcom_alltoallv` 变为 `hcom_alltoall`（等分），且交换结果与参考实现逐位对齐。

## 并行作用域「到底有没有生效」的判定

### 常见静默失效模式

并行代码最常见的失败方式**不是报错，而是静默降级**：

- 分片 hook 没生效 → 每个 rank 冗余地算整条序列 → 结果"看起来正常"，只是慢
- 作用域深度记账失配 → 小规模无异常，大规模才越界  
- 日志打了"Applying parallelism"但打印发生在真正注册之前 → 看日志会得出完全错误的结论

**核心原则**：不要从"结果对不对"开始，要从"分片有没有发生"开始。

### 状态量探测方法（vLLM-Omni 约定）

在可疑位置打印状态量（不是日志字符串）：

```python
import sys
from vllm_omni.diffusion.distributed.parallel_state import (
    get_sequence_parallel_world_size as _gsw,
    get_sequence_parallel_rank as _gsr,
)
from vllm_omni.diffusion.forward_context import get_forward_context as _fc

sys.stderr.write(
    "[probe] tensor=%s sp_world=%s sp_rank=%s sp_active=%s depth=%s\n"
    % (tuple(x.shape), _gsw(), _gsr(),
       getattr(_fc(), "sp_active", "n/a"),
       getattr(_fc(), "_sp_shard_depth", "n/a"))
)
sys.stderr.flush()
```

**判读规则**：

| 观测量 | 含义 |
|---|---|
| `x.shape[0] == seq_len` | **未分片**（危险） |
| `x.shape[0] == seq_len // sp_world` | 已分片 ✓ |
| `_sp_shard_depth == 0` | 处于分片作用域之外 → 该处看到整序列 |
| `_sp_shard_depth >= 1` | 处于分片作用域内 ✓ |

**`_sp_shard_depth` 是唯一可靠的判别量**（`sp_plan_hooks_applied` 常常读不到）。

### 常见误判：拓扑派生参数没跟着变

并行度一变，从旧拓扑派生的参数（每 rank 的局部头数、每 rank 的分块数、每卡的分片长度…）必须**一起重算**。否则守卫判假，整条优化**静默失效**，结果与性能都"看起来正常"。

**操作**：并行度一变，先列出"从拓扑派生"的参数并逐个重算；不要沿用交付档的取值。

## 拓扑相关选型

同一并行形态在不同互连拓扑下排名可能反转——别无条件复用历史结论。

**读取与应用**：
- `npu-smi info -t topo`：UB=HCCS 同域、SYS=跨 PCIe/NUMA
- 同域单组 → USP4 **bulk** 最优（comm busy 最小）
- 跨域组 → **head-parallel** 更优（本组合观测：rank0 clean-window 更快）

**注意**：compile × head-parallel 不兼容（Dynamo recompile_limit 静默回退 eager）。

## 显存受限时的并行解锁

更优并行策略常因单卡显存不可行。两步递进：

1. **先在无损阶段尝试 offload 类特性**降显存解锁（`--enable-cpu-offload` / `--enable-layerwise-offload` / `--enable-distributed-layerwise-offload`），而非直接放弃。注意互斥与副作用——部分框架/模型档拒绝任何 offload；**部分代际上普通 layerwise offload 会触发 OOM killer**（用 DLO 而非普通 layerwise）；**DLO 的 no-AllGather 路径明显更慢** → 选 AllGather 路径

2. **有损（量化等）完成后复查被显存卡住的通信组合**：降显存会解锁新并行。每个量化档落地后回跑「并行×显存余量」候选快测

## 少步 × 多 rank 验证协议

**问题**：用少步跑多 rank 验证并行配置，结论能否外推到全步长？**答：能，但有闸门。**

**口径（强制前置）**：并行对比指标**只取 DiT 去噪阶段**（`<Pipeline>.diffuse` 阶段墙钟，每 rank 一行取 min）；VAE 解码、文本编码、权重装载、warmup 一律排除（固定开销的波动远大于并行差异）。

**判据**：`r = DiT单步(锚点档) ÷ DiT单步(少步档)`
- `|r−1| ≤ 5%` 且各格离散度 `≤ 3%` 且两档排序一致 ⇒ 少步排序可外推
- 排序翻转 ⇒ 一律以锚点档（或更高）为准
- 任一格离散度 > 3% ⇒ 判据不成立，先修噪声

**必须回较高步复验**：排序翻转、单步漂移超阈、未重叠通信占比漂移、特性叠加改变单步结构、显存解锁类改动改变并行可行域。

## 并行方案差异归因

### 阶段 Δ 分解

从 `step_trace_time.csv` 逐行对比两臂（精确匹配列名）：

| 列 | 含义 |
|---|---|
| `Computing` | 计算流上的 AI-core 总线时 |
| `Communication(Not Overlapped)` | 暴露通信（关键路径上） |
| `Overlapped` | 已与计算重叠的通信 |
| `Stage` | 该步墙钟 |

**判读顺序**：
1. 先看 `ΔComm(未重叠)` 与 `ΔFree` — 直接载体
2. 再看 `ΔComputing` — 形态自带的额外计算（plumbing），不会被掩盖
3. `ΔOverlapped` 变化但 `ΔStage` 不变 ⇒ 通信量变而暴露没变（掩盖已饱和）
4. **优先用占比而非"省了多少"**：重叠占比 = `Overlapped ÷ Communication`。占比高 ⇒ 继续压这块收益上限低

### 小集合通信成本规则

小集合通信（rendezvous 类）**不能按字节外推**；看它给**别的流**造成的 **WAIT**。**隔离微基准只给下界**，真实代价必须在该拓扑的流水线内实测。

**规则**：小集合通信在关键路径上的代价**不小于**它自身时长，且随 rank 数与到达偏斜放大；因此按**等待**判、不按字节判。

### 4 → 8 卡线性度

增加卡数时，通信体积、通信步数、依赖关系都会变化。线性度评估须同时考虑：

- 通信量与计算量的缩放
- 阿姆达尔定律与同步点影响
- 拓扑与带宽变化

不得用跨卡数对比冒充形态对比。

## 限制

- MindIE-SD / MiniMax-H3 特定内容：本文件针对扩散 DiT × 序列并行形态回填；模型架构改变时判据需重新标定
- 框架侧机制检验：若目标框架自身无 comm-stream 机制且 monkey-patch 不可行 → 属框架侧补齐，走 framework-integration
- 无本地 NPU 验证：所有阈值与常数都与硬件 + 拓扑 + 栈版本强绑定，迁移时必须本地重测

## 维护与更新

当新的并行策略经验证有效、多卡互联拓扑发生变化、发现新的分布式训练陷阱或 CANN 版本缺陷时，按本技能的复盘流程更新。

