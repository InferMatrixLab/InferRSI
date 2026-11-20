# Issue #529：10 查询检索对比

结果是 **INCONCLUSIVE（任务收益）**。这次展示各查询实际检索/递送了什么，
不作检索优越性、优化收益或服务性能声明。

- 基线：`1b826b5f9666a8b734000e1eb2990e582cdef876`（已合入 #516）；代码候选：`c457c85`。
- 知识数据完全相同，动态计数为 80 Skill + 48 Record + 7 Case = 135；主技能单独加载。
- 题面来自仓库 `tests/fixtures/find/layout-queries.json` 的七类任务，及
  `labelled-queries.json` 前三个 case 的 question 题面。详见 [冻结题面](queries.json)。
- 基线 Find top-5；候选由当前 Agent 查看全部 135 个 ID/简述后自主选择，
  再检查条件、引用扩展和实际读取；没有词法预筛。Agent 选择不是离线固定规则生成。
- 同一会话、非盲测，无法隔离历史；Agent 实际查看了全部简述，随后查看相关原文摘录。
  完整 JSON 输入的 tokenizer 预算测量不代表实际会话输入 token；实际模型用量和选择耗时未知。
- 每题每臂一次检索决策。候选决定在代码修正前保留；修正引用闭包后只重放确定性读取，
  复用同一基线及选择。早期读取结果本地保留，以下为修正后的结果；无挑选更有利的模型重跑。
- 完整选择输入按 `tiktoken/o200k_base` 为 77,086–77,113 token/题，
  预算 128,000，预留 4,096。读选中材料预算 131,072 字节，扩展一跳、5 项、32,768 字节。

Find 返回 50 条、成功递送 39 个 owner；新模式选中 25 条、递送 19 个 owner。
返回数量不同不是精确率/召回率比较。没有新增跨 owner 条目成功递送；部分 Record
通过 owner-local 技能资源扩展获得原文，详见 JSON 的 expansion_paths。
缺少独立人工标注，首次有效证据时间、错误迁移率和有效新增证据率未量化。

## 每题材料

下面列出基线全部 top-5、新模式全部选择及实际递送数。技能 ID 使用短名；
[机器结果](comparison.json) 保存完整 qualified ref、遗漏、扩展路径、预算与耗时。

| # | 查询 | 无 PR：Find top-5 | 启用新模式：选择 | 递送 owner（旧/新） |
|---|---|---|---|---|
| 1 | Ascend Omni Day-0 | `ascend-model-adaptation`<br>`vllm_omni.ascend.diffusion.qwen_image_21_eager_t2i`<br>`sglang_omni.common.audio.serving_and_streaming_quality`<br>`vllm_omni.common.audio.streaming_serving_measurement`<br>`ascend-video-diffusion-optimization` | `ascend-model-adaptation`<br>`vllm_omni.common.omni.stage_ownership_and_search`<br>`vllm_omni.common.diffusion.production_integration_gates` | 5/3 |
| 2 | Diffusion 单卡性能 | `ascend-video-diffusion-optimization`<br>`vllm_omni.common.diffusion.measurement_and_profiling`<br>`inference-benchmark-design`<br>`video-diffusion-optimization`<br>`host-overhead-optimization` | `vllm_omni.common.diffusion.measurement_and_profiling`<br>`performance-ceiling-analysis`<br>`host-overhead-profiling` | 4/2 |
| 3 | ROCm graph hang | `case.qwen-b300-rejected-directions`<br>`ascend-graph-mode`<br>`pytorch.cuda.compiler.cudagraph_shapes_and_lifetimes`<br>`flashinfer.cuda.llm.paged_decode_dispatch`<br>`ascend-aclgraph-capture-replay` | `pytorch`<br>`pytorch.cuda.compiler.cudagraph_shapes_and_lifetimes` | 5/1 |
| 4 | TTS 音质回归 | `inference-benchmark-design`<br>`qwen3_tts_engine.ascend.audio.fixed_customvoice_prompt`<br>`qwen3_tts_engine.ascend.audio.codec_constants_and_state`<br>`qwen3_tts_engine.ascend.audio.graph_batching_state_ownership`<br>`torch-npu` | `inference-benchmark-design`<br>`sglang_omni.common.audio.serving_and_streaming_quality`<br>`vllm_omni.common.audio.streaming_serving_measurement` | 4/2 |
| 5 | 引擎/插件版本对齐 | `vllm-ascend`<br>`vllm-metal`<br>`vllm_omni.ascend.diffusion.minimax_h3_reference_kv_reuse`<br>`ascend-model-adaptation`<br>`audit-afd-p2p-exchanges` | `repository-evolution-analysis`<br>`vllm-ascend`<br>`torch-npu` | 1/2 |
| 6 | DeepInfer 衍生引擎 | `deepinfer.common.llm.zero_overhead_deferred_scheduling`<br>`deepinfer.common.llm.bounded_windowed_replay`<br>`vllm-metal`<br>`host-overhead-optimization`<br>`deepinfer.common.llm.speculative_verification_budget` | `deepinfer.common.llm.zero_overhead_deferred_scheduling`<br>`vllm.common.llm.runtime_and_kv_ownership`<br>`vllm.common.llm.extension_correctness_gates`<br>`repository-evolution-analysis` | 4/4 |
| 7 | Windows XPU 独立引擎 | `inference-benchmark-design`<br>`project-maya`<br>`weight-loading-optimization`<br>`strata.common.llm.engine_validation_contract`<br>`cann-attribution-overlap` | `inference-benchmark-design`<br>`kernel-writing-guide`<br>`claim-contract` | 3/2 |
| 8 | Qwen 四卡 B300 融合 | `case.qwen-b300-rejected-directions`<br>`vllm_omni.ascend.diffusion.qwen_image_21_eager_t2i`<br>`case.qwen-ascend-rejected-directions`<br>`vllm_omni.cuda.diffusion.minimax_h3_qk_norm_rope`<br>`inference-benchmark-design` | `case.qwen-b300-rejected-directions`<br>`inference-benchmark-design` | 4/1 |
| 9 | Qwen 910B1 RoPE 缓存 | `vllm_omni.ascend.diffusion.qwen_image_21_eager_t2i`<br>`case.qwen-ascend-rejected-directions`<br>`case.qwen-b300-rejected-directions`<br>`ascend-graph-mode`<br>`ascend-model-adaptation` | `case.qwen-ascend-rejected-directions`<br>`vllm_omni.ascend.diffusion.qwen_image_21_eager_t2i` | 5/2 |
| 10 | 整图质量门槛已失败 | `case.qwen-b300-rejected-directions`<br>`inference-benchmark-design`<br>`case.drama3-rejected-directions`<br>`vllm_omni.ascend.diffusion.qwen_image_21_eager_t2i`<br>`ascend-operator-tuning` | 空选择 | 4/0 |

## 逐题边界与退化

1. 更集中于适配、阶段契约和上线边界；版本/真实权重未知。
2. 性能上限技能必需材料 213,952 字节，超过 131,072 字节预算，未递送；不应把选中视为已读。
3. PyTorch 材料占用大部分预算，选中的 CUDA graph Record 未递送；泛化方法不能证明 ROCm 根因。
4. benchmark-design 必需材料 320,040 字节而未递送；实际读到的是两套音频测量方法，目标引擎未知。
5. 读到历史分析与 vLLM-Ascend；torch-npu 未递送。具体兼容组合仍缺版本。
6. 补充了 vLLM KV/state 所有权与扩展正确性；DeepInfer 离线调度不能直接迁移为服务调度。
7. 仅有通用方法，缺 Windows/XPU 原生证据；没有把其他平台材料升级为目标支持。
8. 命中同 cohort 案例：初始融合算子通过、整图失败并回退；benchmark-design 未递送。
9. 命中同 cohort 案例和 Record：缓存 cos/sin 图像一致但更慢；仍为 author-reported，不是本地复验。
10. 空选择：题面已经确认质量门槛失败，不能以算子通过或额外案例覆盖该失败。

[原文确认记录](assessments.json) 为 9 个非空查询分别保存 exact ref/revision/path/quote、
判断理由、缺口和下一步；接口检查引文确实存在于递送字节中。引用检查不是对判断真实性的独立证明，
也不改变来源验证等级。机器结构化判断大多仍为 unknown，因为知识源缺少可直接比较的字段。

## 验证和复现

- 相关测试：168 passed、2 skipped；Ruff `src tests tools` 与 `git diff --check` 通过。
- 独立代码工作树检查通过；不是正式 GitHub Approve，也未评判检索效果。
- 全仓测试尝试在 1,143 passed、12 failed、12 skipped 时中断。现有 Git 2.33
  不满足部分测试 Git >=2.45 的要求，Node 12 的两项浏览器脚本测试失败，
  benchmark compare 的假任务评估也失败。三类代表用例均在未改动基线复现。
  因此没有宣称全仓通过，其余未执行部分仍未验证。
- 未运行设备优化、GPU/NPU性能或独立会话模型对照；这是按请求执行的知识检索对比。

在代码候选 checkout 中安装 dev 与 tiktoken，准备固定基线 checkout，执行：

```bash
python tools/compare_catalog_selection.py --baseline <baseline-checkout> \
  --selections docs/reviews/catalog-selection-529/selections.json \
  --output <new-output-directory>
```

脚本重放已保存的 Agent 选择，不会再调用模型。知识来源变化后旧 snapshot 会拒绝读取。
使用 [文件校验和](sha256.json) 验证共享摘要和实现文件；完整原文 payload 与早期运行
保留在本地结果目录，未上传私有路径、完整会话或原始环境日志。

## 2026-11-20：检索接口性能修正

针对重复构建全目录和共享资源重复校验，新增按文件内容与成员清单检查的目录复用，
以及 reader 内共享资源摘要。读取前后仍检查来源变化；恢复时间戳的修改、未选中资源变化、
store 更新均会使旧快照失效。符号链接或目录重定向会禁用目录复用，回退到完整构建。
目录返回值独立复制，完成或出错后释放缓存；metadata 与依赖版本继续逐次校验。

同一主机、相同知识与预算、每次新进程，交替运行原 Find、优化前 catalog-select 和优化后
catalog-select。复用先前 Agent 选择，没有重新筛选。下表为**接口构建至原文递送**的平均秒数：

| 查询组 | 原 Find | 优化前 catalog-select | 优化后 catalog-select | 新模式耗时减少 |
| --- | ---: | ---: | ---: | ---: |
| `qwen2.1-image 优化到1.35x加速`，各 5 次 | 1.075 | 6.923 | 1.598 | 76.9% |
| 原来的 10 个固定查询，每题每臂 1 次 | 0.985 | 6.613 | 1.599 | 75.8% |

Qwen 查询的目录准备均值为 2.238 → 1.284 秒，校验/读取为 4.685 → 0.314 秒。
所有查询优化前后的 snapshot ID、递送原文字节、版本、判断、遗漏和展开路径摘要一致。
完整输入和所有计时样本、阶段均值、精确版本及失败尝试说明见
[性能记录](performance-20261120.json)。原先的结果文件保持不变。

计时排除进程启动、import、tokenizer 初始化、输出序列化和 Agent 选材；操作系统页缓存未控制。
两边都没有外部知识调用。这些数字不代表模型选择提速、Qwen 达到 1.35x 或推理服务收益。
相关回归测试 236 passed、2 skipped、2 subtests passed；Ruff 和独立内部代码检查通过。
未重新运行全仓测试，前述环境限制仍然适用。

复现时使用干净、固定版本的三个 checkout，以及原先保留的选择文件：
10 题使用本目录 `selections.json`；Qwen 单题的完整选择保存在性能记录的
`qwen_five_repeats.retained_selections` 数组中，可导出为独立 JSON 文件。

```bash
python tools/time_catalog_selection.py --baseline <original-find-checkout> \
  --before <catalog-before-checkout> --after <catalog-after-checkout> \
  --selections <retained-selections.json> --repetitions <count> --output <new-output-directory>
```
