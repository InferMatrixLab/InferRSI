# 实验记录约定

使用 Python 3.10+ 运行捆绑工具，仅需标准库：

```text
python <skill-root>/scripts/summarize_trials.py trials.csv
```

CSV 必须包含以下表头：

```csv
trial_id,config_id,experiment_id,hardware_id,workload_id,baseline_id,ttft_ms,decode_tps,peak_vram_mib,peak_ram_mib,quality_ok,valid
```

在单独实验清单中定义四个比较 ID，其背后固定模型和 pack 哈希、源码/构建/工具链、tokenizer、采样、实际输入输出 token、并发、缓存/预热策略、质量参考及资源上限。所有行必须具有相同且非空的比较 ID，混入其他条件会拒绝整个文件，即使该行质量检查失败也一样。

每行代表一次实测。trial ID 不重复，config ID 对应保存的配置或 patch。发现任何重复的非空 trial ID，会在过滤前拒绝整个文件，不受行顺序影响。`quality_ok` 表示约定的正确性/质量检查已实际通过；`valid` 表示运行完整满足上下文、输出、并发要求及所有资源上限。只接受字面值 `true`（忽略大小写），不能因为速度快就标记通过。

TTFT 是客户端收到首 token 的毫秒数。decode 吞吐以模型 token/s 计，每行必须用相同计时口径，不能混用流式分片、客户端估算及引擎 token 统计。内存列记录单次峰值，单位 MiB。数值必须有限，TTFT 和吞吐为正，内存非负。

工具报告描述性中位数、有效样本数及拒绝原因。同一配置存在任何被拒绝记录时，即使其他记录通过，也不进入 Pareto 集。Pareto 目标为更低 TTFT、更高 decode 吞吐；两个目标均不变差且至少一个变好，才构成支配。内存会报告但不参与 Pareto 目标，汇总前必须通过 `valid` 检查每次运行的内存上限，中位数不能证明峰值满足要求。

本工具不计算置信区间、质量得分、功耗、p95 或显著性，需保留原始日志另行分析。没有合法候选不能算优化成功。工具为本 Skill 新写，不是从 Strata 复制的脚本。
