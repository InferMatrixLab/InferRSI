# 命令与测量

以下为已核对源码的 Bash 模板，不是已执行服务结果，也不是普遍推荐规模。目标环境必须有兼容的 vLLM/backend 安装和已授权模型。先查看实际版本 help。`MODEL_PATH` 是占位符，执行前解决模型访问与 tokenizer 行为。未经授权不能把公开 endpoint 用作负载测试。

```bash
# Inspect the actual target environment; no model launch here.
git rev-parse HEAD
python -c "from importlib.metadata import version; print(version('vllm'))"
vllm serve --help=all
vllm bench serve --help
```

```bash
# Illustrative baseline only. Replace MODEL_PATH with an approved local model.
vllm serve MODEL_PATH --host 127.0.0.1 --port 8000 \
  --max-model-len 4096 --max-num-batched-tokens 2048 --max-num-seqs 32 \
  --tensor-parallel-size 1 --enable-prefix-caching
```

```bash
# Illustrative random-token completion workload against that local server.
vllm bench serve --backend openai --model MODEL_PATH \
  --dataset-name random --random-input-len 512 --random-output-len 128 \
  --num-prompts 100 --request-rate 2 --save-result --result-dir results/baseline
```


Serve flags 对应 EngineArgs/config 字段，host/port 从 FrontendArgs 生成；benchmark flags 在 `serve.py` 与 dataset parser 注册。本预览静态核对选项存在性，没有导入 CLI parser 验证完整运行兼容性。此模板 `openai` backend 对应 completion 负载；chat 负载需要匹配的 backend/endpoint/template 及另行准备的代表性语料。随机 token smoke 不能替代生产负载或质量测试。[serve_flags](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/engine/arg_utils.py#L1708-L1750) [config_flags](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/engine/arg_utils.py#L1838-L1871) [frontend_flags](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/entrypoints/launchers/cli_args.py#L254-L286) [bench_flags](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/benchmarks/serve.py#L1590-L1667) [dataset](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/benchmarks/datasets/datasets.py#L1584-L1612) [lengths](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/benchmarks/datasets/datasets.py#L1885-L1903)

benchmark 默认 request rate 是无穷，即所有请求在零时刻同时发出。服务 SLO 实验应显式选有界 offered rate，再围绕饱和点扫描。每个结果记录速率、长度分布、生成设置和并发口径。保存原始 JSON 与错误；只有成功吞吐而无失败/准入拒绝数的结果不完整。[bench_rate](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/benchmarks/serve.py#L1697-L1772)

## 观测契约

| 记录 | 意义 / 比较约束 |
|---|---|
| 完整命令、配置、源码/包/模型/tokenizer 版本 | 复现选择，避免默认值漂移 |
| 硬件、拓扑、互联、运行库 | 解释计算/显存/通信差异 |
| 输入输出长度、prompt/tokenization 身份 | 控制工作量与缓存资格 |
| Offered request rate、并发、到达分布 | 区分空载时延、饱和及突发 |
| 成功 output tokens/s、requests/s；失败/拒绝数 | 测有用工作，不静默丢弃请求 |
| TTFT p50/p95/p99；可用时含 queue/prefill 分量 | 区分准入/排队与模型工作 |
| ITL、TPOT 分布及准确定义 | ITL 是逐 token 间隔；请求平均 TPOT 可能掩盖停顿 |
| 端到端时延、质量/等价性检查 | 避免更快但语义不同的结果 |
| KV 使用率、prefix queries/hits、抢占、显存峰值 | 诊断驻留、复用和重算压力 |
| 预热/编译/启动成本、预热后重复运行 | 避免混淆冷启动与稳态 |

metric logger 定义 `vllm:kv_cache_usage_perc`、prefix queries/hits、抢占和时延指标。编写查询前核对实际 endpoint/version 的 label 与单位，不能根据 `_perc` 名称替代对数值量纲的检查；不同负载 histogram 合并前应标明来源。[metrics_cache](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/v1/metrics/loggers.py#L619-L679) [metrics_latency](https://github.com/vllm-project/vllm/blob/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5/vllm/v1/metrics/loggers.py#L930-L979)

## 本预览验证范围

已审查并尝试原生元数据测试 `tests/test_zentorch_version_pin.py`，关闭 pytest 仓库 conftest 和自动插件加载。由于本地 Python 缺少 `regex`，collection 中止；未执行源码 setup 或安装依赖。本地也没有 Torch，因此未运行 engine/CLI/原生 GPU 测试。AST 解析及源码选项检查仅为较窄证据，不是推理验证。技能树外报告记录准确命令与结果。实现测试选择见[改动验证](../../extend-validate/references/change-boundaries-and-validation.md)。
