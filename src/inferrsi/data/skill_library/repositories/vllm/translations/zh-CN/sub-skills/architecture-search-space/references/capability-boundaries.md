# 已有控制项与新增能力

把调参结果称为引擎创新前先读本页。已有 flag 改变现成策略或实现；新增能力需要明确缺失行为、所属代码、不变量，以及相对于已有控制项可测量的优势。

| 机制 | 本快照已有搜索空间 | 需要实现或新增证据的内容 |
|---|---|---|
| Token/准入调度 | runner 输入 `max_num_batched_tokens` 与独立生效的 `max_num_scheduled_tokens` 预算；`max_num_seqs`、`max_num_active_seqs`、长 prefill 阈值、policy/async 配置 | 新公平性/SLO 策略、预算模型或准入状态转换；证明无饥饿、预算越界或陈旧输出 |
| KV/前缀复用 | prefix 开关/hash/match unit、cache dtype、字节预算、已有 offload | 新缓存身份、淘汰、存储粒度或 hybrid checkpoint 语义；证明隔离、引用生命周期和准确语义复用 |
| 投机解码 | 已支持 method、draft 模型、draft 数、兼容的 draft TP | 新 proposer/verifier 集成或接受策略；证明目标采样行为与 KV 回滚，再测净收益 |
| 并行 | TP/PP/DP/EP、PCP/DCP、通信后端和已有负载均衡 | 新 partition/collective/layout 或调度拓扑；证明 rank groups、权重映射、collective 次序与模型支持 |
| P/D 与外部 KV | 已注册 connector、role/configuration | 新传输或生命周期语义；证明 load/save 就绪、延迟释放、取消及部分失败 |
| 编译/kernel | 已支持 compile/graph 模式、capture sizes、attention 选择与量化格式 | 新 lowering/fusion/kernel/backend/量化格式；计时前证明 shape/layout/数值行为和 dispatch |

调度证据：[sched_config](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/scheduler.py#L48-L103) [custom_sched](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/scheduler.py#L238-L253)。缓存：[cache_config](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/cache.py#L102-L155) [cache_bytes](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/cache.py#L255-L272) [cache_match](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/cache.py#L74-L100)。投机：[spec](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/speculative.py#L393-L410) [spec_docs](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/docs/features/speculative_decoding/README.md#L1-L62)。并行与传输：[ep](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/parallel.py#L189-L233) [kv_transfer](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/kv_transfer.py#L56-L91)。编译与量化：[compile_mode](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/compilation.py#L37-L69) [graphs](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/compilation.py#L610-L654) [quant](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/model_executor/layers/quantization/__init__.py#L15-L114)。

scheduled-token 预算是实现/配置概念，本表不保证存在同名公共 CLI 参数。应核对目标版本的有效值和解析器，参见[运行时记账](runtime-and-invariants.md)。

## 避免无效方案的关键区分

- **分页 KV 是存储/所有权机制；前缀缓存是复用策略。** 优化其一不会自动改善另一个；保留更久的缓存还会与活跃请求争用显存。
- **编译与 CUDA graph 是不同轴。** `CompilationMode` 和 `CUDAGraphMode` 契约不同。piecewise graph 依赖兼容的分段编译，full graph 可以有编译或无编译。捕获 shape 消耗显存，也影响预热与启动。[compile_mode](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/compilation.py#L37-L69) [graphs](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/compilation.py#L610-L654)
- **权重量化与 KV 量化解决不同显存开销。** 注册表中存在格式名不代表所有 kernel/模型/硬件均支持。检查 checkpoint layout、后端支持、scale 处理及实际负载精度。[quant](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/model_executor/layers/quantization/__init__.py#L15-L114) [quant_docs](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/docs/features/quantization/README.md#L25-L99) [cache_config](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/cache.py#L102-L155)
- **投机包含 draft、目标验证和调度成本。** 净收益取决于接受长度和 offered load，不是只看提出 token 数。标准 rejection 逻辑区分 accepted、recovered 和 bonus tokens。synthetic acceptance 用于受控性能实验，不能证明目标输出正确性。[rejection](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/v1/sample/rejection_sampler.py#L46-L71) [synthetic](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/speculative.py#L529-L549)
- **P/D 是 SLO/拓扑决策。** 与调优后的 chunked prefill 比较，纳入传输和代理成本，不能宣称天然提高吞吐。固定版本功能文档明确反对该说法。[pd](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/docs/features/disagg_prefill.md#L1-L33)

新方案交付：(1) 已有控制项在哪些测量下不足；(2) 缺失行为及所有者；(3) 保持不变量的实现草案；(4) 能区分方案的负载与基线；(5) 拒绝条件。实测前，预期加速只标为假设。
