# Issue #529：10 查询检索对比

[2026-11-27 paired model pilots, budget checks and native Find control](pilots-20261127.md)

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
[文件校验和](sha256.json) 可用于核对共享摘要。其中 `implementation` 对应首次评估提交 `c457c85` 的文件路径与字节。
完整原文 payload 与早期运行保留在本地结果目录，未上传私有路径、完整会话或原始环境日志。

## PR 检视后的固定选材复验

最初评估的代码为 `c457c85`。从该提交到首次被检视的 `3f6d5d3`，改动的七个文件均在本报告目录，`src/`、`tests/` 和 `tools/` 内容相同。本轮用 `15b3459` 重放固定选择，沿用相同查询、预算与 tokenizer，单独保存[逐题结果](review-replay.json)。

逐个比对新旧目录的 135 对 ref/revision 后，在新快照提交冻结的 refs。10 题合计选择 25 个条目、递送 19 个。每题递送的条目顺序、版本、资源路径、原文哈希和字节数均与先前结果相同，9 条历史引文全部通过校验。另一个 [Qwen 1.35x 查询](https://github.com/InferMatrixLab/InferRSI/blob/2ebf99b40f46a7bde790b9bd02ca620b94f8858b/docs/reviews/catalog-selection-529/performance-20261120.json)选 5 个、递送 4 个，4 条引文通过。两组查询的条目级结构化 verdict 均与先前一致。此次复验只覆盖确定性读取；选材、设备和耗时没有重新评测。

检视点中的两个条目都完整递送了必需资源。对比历史原文与固定版本里的必需文件后，`vllm-ascend` 首次递送的 86,668 字节包含全部 4 份必需材料，超限的是后续可选的 `references/model-performance.md`（需 21,756 字节，剩余 9,828）。Day-0 的阶段所有权 Record 完整递送 3,044 字节的 `record.json`；其后的可选 `omni-architecture/SKILL.md` 展开需 18,293 字节，剩余 5,223。新记录给出被跳过的路径、来源链接与作用范围。

最初 9 条评估各自提交的 `claim` 和 `reason` 文本恰好相同。两个字段由调用方分别填写；回归测试用不同文本检查它们能够独立保留。对本轮代码运行目录、Find、读取、存储、CLI、Apps 和 smoke/claim 相关测试，244 项通过，2 项跳过，另有 2 个子测试通过。

如需重放本轮 10 题，可在包含本报告的 PR 提交中使用与 `15b3459` 相同的代码，读取本目录的检视结果，将冻结选择复制到临时文件。先确认整个知识库的版本映射，再绑定新的目录快照，随后把临时文件作为上文 `tools/compare_catalog_selection.py` 的 `--selections` 输入。

```python
import hashlib
import json
from pathlib import Path

from inferrsi.knowledge.catalog_selection import CatalogSelection

report_dir = Path("docs/reviews/catalog-selection-529")
checks = json.loads((report_dir / "review-replay.json").read_text())
snapshot = CatalogSelection().snapshot()
versions = {card["ref"]: card["revision"] for card in snapshot["cards"]}
data = json.dumps(versions, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
assert hashlib.sha256(data).hexdigest() == checks["source_revisions_sha256"]
assert snapshot["snapshot_id"] == checks["current_snapshot"]
rows = json.loads((report_dir / "selections.json").read_text())
for row in rows:
    assert row["snapshot_id"] == checks["old_snapshot"]
    row["snapshot_id"] = snapshot["snapshot_id"]
with Path("review-replay-input.json").open("x", encoding="utf-8") as out:
    json.dump(rows, out, ensure_ascii=False)
```
