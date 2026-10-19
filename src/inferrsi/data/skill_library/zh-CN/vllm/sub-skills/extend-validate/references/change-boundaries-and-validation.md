# 改动边界与验证

## 选择所属层

| 目标行为 | 起点 | 宣称成功前必须检查 |
|---|---|---|
| 公平性、token 预算或准入 | `vllm/v1/core/sched/`、`config/scheduler.py`、`engine/arg_utils.py` | 预算与 active sequence 上限、前进性、抢占、长/混合 prompt、取消、异步 placeholder、draft 槽位 |
| 前缀身份、复用或淘汰 | `vllm/v1/core/kv_cache_manager.py`、`block_pool.py`、`kv_cache_utils.py`、coordinator/group managers | 无无效命中、LoRA/MM/salt 隔离、共享引用、可写尾块、partial/hybrid groups、reset/invalidation |
| KV 传输 | `distributed/kv_transfer/kv_connector/v1/base.py` 及具体 connector | metadata 对应已分配块；使用前完成 load，释放前完成 save；异步完成、取消、部分失败、明确 fail/recompute |
| Attention/backend | `vllm/v1/attention/selector.py`、platform selector、实际 backend/kernel | dtype/head/block/layout 支持、mask/变长、prefill/decode、graph capture、分布式及数值参考对比 |
| 量化 | `model_executor/layers/quantization/` 和模型权重加载 | 格式/checkpoint dispatch、scale/layout、设备支持、逐层和端到端质量、TP/EP 权重布局 |
| 编译/fusion | `vllm/compilation/`、`config/compilation.py`、受影响 model/op | graph 边界/hash 因素、动态 shape、eager 等价、capture/replay、缓存失效、实际 kernel dispatch |

目录只定位可能所有者；编辑前检查目标模型/runner 版本。本快照一些模型专属路径位于 `vllm/models/`，因此旧的 model_executor-only 地图不完整。量化类注册或 custom proposer 只是扩展点，不是验证结果。scheduler 配置明确提醒自定义接口不是公开稳定接口。[custom_sched](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/scheduler.py#L238-L253) [attention](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/v1/attention/selector.py#L105-L225) [quant](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/model_executor/layers/quantization/__init__.py#L15-L114) [connector](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/distributed/kv_transfer/kv_connector/v1/base.py#L1-L41)

## 正确性门槛

1. 调度：已调度 token 不越预算，input budget 含 draft，RUNNING 准入有界。测试 prompt/output 达到上下文边界，以及带在途输出的抢占请求。[invariants](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/v1/core/sched/scheduler.py#L1403-L1415) [async_tests](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/tests/v1/core/test_async_scheduler.py#L539-L601)
2. KV：消费者不读未完成传输或已释放块；命中必须表示相同计算；不同语义身份不能错误共享。按改动测试冷/暖、零/新命中、压力/淘汰、取消及相关 hybrid groups。[kv_lifetime](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/v1/core/block_pool.py#L666-L795) [connector_finish](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/distributed/kv_transfer/kv_connector/v1/base.py#L371-L408)
3. 投机：保持 accepted/recovered/bonus 语义、终止与回滚。仅 greedy 相同不能验证随机采样正确性；应在支持的采样配置下使用目标分布和 seed 行为测试。synthetic acceptance 不用于输出正确性。[rejection](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/v1/sample/rejection_sampler.py#L46-L71) [rejection_tests](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/tests/v1/sample/test_rejection_sampler.py#L380-L416) [synthetic](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/speculative.py#L529-L549)
4. Kernel/量化：按 dtype/operation 制定容差并检查任务质量。不能要求所有 kernel 位级相同，也不能接受任意漂移。测试跨越 block、capture、partition 边界的 shape。
5. 并行/传输：在实际拓扑检查 rank/权重映射、collective 次序、layout、取消与故障恢复。单设备结果不能认证多节点行为。[context_parallel](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/parallel.py#L591-L629) [world_size](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/config/parallel.py#L946-L965)

## 原生测试候选，并非已通过测试

```bash
python -m pytest tests/v1/core/test_scheduler.py -q -k 'max_num_active_seqs_caps_admission or schedule_partial_requests'
python -m pytest tests/v1/core/test_async_scheduler.py -q -k 'kv_pressure_preemption_with_inflight_output or abort'
python -m pytest tests/v1/sample/test_rejection_sampler.py -q -k 'rejection_sampling_approximates_target_distribution or deterministic_when_seeded'
```

已在固定源码找到上述函数。运行需仓库实际依赖与合适加速器；collection 本身就导入较重的仓库 conftest。不能给这些 engine tests 加 `--noconftest` 来制造通过。prefix/cache 测试位于 `tests/v1/core/test_prefix_caching.py` 和 `test_single_type_kv_cache_manager.py`，按真实 group 选择。connector 单测位于 `tests/v1/kv_connector/unit/`，NIXL 集成位于 `tests/v1/kv_connector/nixl_integration/`。分布式、编译和量化改动还需相应测试目录和后端矩阵。[scheduler_tests](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/tests/v1/core/test_scheduler.py#L211-L281) [async_tests](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/tests/v1/core/test_async_scheduler.py#L539-L601) [test_deps](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/tests/conftest.py#L28-L48)

元数据原生候选 `tests/test_zentorch_version_pin.py` 比较 zentorch 与 CPU torch 依赖字符串，无需模型运行。Creator 使用 `--noconftest` 尝试后，因缺 `regex` 在 collection 受阻。这不能验证推理引擎。未使用依赖 shim，未执行 setup.py。[native](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/tests/test_zentorch_version_pin.py#L1-L77)

## 自查与远程交付

给出行为差异、固定源码/测试名、实际命令和结果、不支持的组合及待执行设备检查。自查配置传递和 graph hash、输出/取消次序、共享 KV 引用及释放时机。性能结论需要有效基线、同等工作量与质量、重复测量和适用负载区间。本地原生检查无法运行时，完成可行静态检查并提供远程命令，不宣称修复已证明。
