# Codex 用户优化 Qwen-Image 的 pytest 用例

设计与验收范围：[Issue #479](https://github.com/InferMatrixLab/InferRSI/issues/479)。
这是普通用户体验用例，不是 `benchmarks` 题包。测试入口在
[`e2e/qwen_image/test_user_journey.py`](../e2e/qwen_image/test_user_journey.py)，
不在默认 `pytest` 的 `tests/` 范围内，不增加 CI lane 或自动预约 NPU。

## 历史证据回放

在 InferRSI 仓库根目录运行：

```bash
python -m pytest -v e2e/qwen_image/test_archived_journey.py \
  --e2e-archived-evidence <actor-evidence-root> \
  --e2e-archived-retest <independent-attempt-directory>
```

第一个目录含 `plan/actor-plan.json` 和 `results/actor/`，第二个目录含
`sealed-source.json`、`independent-result.json` 和原始 PNG。回放只读取文件。
三个测试分别重算逐轮取舍与会话 final、独立复测的顺序/图像/计时、实际补丁与受测快照身份。
归档的格式调整即使保持 Python AST 相同，文件字节发生变化也会触发身份断言。
pytest 会展示具体文件和两份摘要。默认测试发现不会启动真实 Agent。

## 正式试跑的计时 A/A

将两臂均使用固定基线的测量放在协议冻结前完成，使用正式比较相同的工作负载、
预热次数、交叉顺序和配对数。准备记录的 `timing_policy` 引用冻结协议中的 JSON。
观察记录的 `timing_aa` 引用按执行顺序排列的 `[{step, result}]`。
`result` 是带相对路径和 SHA-256 的原始回执，含实际加载的源码摘要
`loaded_source_sha256`、起止时间、完整请求耗时及 PNG。回执与用例中的质量 A/A 分开。

当前支持的估计方法 `maximum_absolute_paired_change_pct` 取各配对组中
`100 × abs(B − A) / A` 的最大值，A、B 各取该组六次请求的中位数。
在冻结文件中记录 `estimator`、原始记录摘要 `aa_sha256`、实测噪声
`observed_noise_pct` 和 `adoption_threshold_pct`。采用门槛由本次执行计划决定，
须覆盖该噪声，并与 Harness 配置一致。将 `adoption_comparator` 设为
`current_best` 表示相对当前累计最佳也要达到采用门槛。若实际计划选用其他估计方法，
此检查返回 INCONCLUSIVE。缺少原始记录时同样保留 INCONCLUSIVE。

## 用户输入

交付补丁时由观察者保留 `submission` 回执，含 `candidate_id`、`attempt`、
`candidate_sha256` 和原始补丁字节的 `patch_sha256`。将回执以路径和摘要加入
`observer.json` 的 `submission`。独立复测在应用补丁前读取原始回执；
另一份能得到相同源码的合法补丁也会在计时前被拒绝。

准备好固定版本的 vLLM-Omni Codex 项目、InferRSI 插件和 A2 使用 skill 后，
唯一发送给 Codex 的用户输入是 [`request.txt`](../e2e/qwen_image/request.txt)：

> 请用 InferRSI 优化当前 vLLM-Omni 项目的 Qwen-Image-2.1-Turbo，在 Ascend A2 单卡上生成 1280×704 图片，保持出图质量，把单张生图耗时降到尽可能低。请多轮尝试、复测最优方案，并交付补丁和结果。

测试器不会给 Codex 提供 TASK.md、协议文件、候选实现、优化建议或重试提示。
Agent 自行准备并冻结内部协议，使用普通 `campaign start/round/final` 流程。
固定基线使用 #479 中规定的首次 Turbo 支持 PR 合入后的提交，作为运行参数传入，
不写入共享测试默认值。质量/采样/收益门槛以该次搜索前冻结的协议为准。

## 执行

安装 `python -m pip install -e '.[dev,image]'`。操作者先在独立、干净的项目目录
检出 `<baseline_sha>`，配置实际使用的 Codex 模型、插件和 A2 skill，验证同一用户
和执行环境能非交互登录、独占健康单卡、读取已核验文件字节的模型缓存。
连接信息和凭据留在现有 skill/环境，不传入测试配置。

当前自动启动适配器是 **Codex CLI**；显式指定模型，保存客户端版本、请求、
逐事件原始输出及接收时刻、最终回复和墙钟耗时。它使用现有权限设置，
不添加绕过批准或隔离的参数，不自动继续失败会话。
CLI 的结果不能用作 Codex Desktop 的宿主兼容性通过证明；Desktop 的原生会话
可以由看护者导出证据，再使用下文的只读复核入口。

```bash
python -m pytest e2e/qwen_image/test_user_journey.py --run-agent-e2e \
  --e2e-project '<prepared-vllm-omni>' \
  --e2e-baseline-revision '<baseline_sha>' \
  --e2e-model '<fixed-codex-model>' \
  --e2e-timeout-seconds '<wall-clock-budget>' \
  --e2e-artifacts '<new-private-output>' \
  --e2e-campaign-parent '<private-campaign-parent>' \
  --e2e-observer '<private-observation-directory>/observer.json'
```

这是会实际使用模型和机器的显式运行。看护者在运行中持续保留选择依据、
人工介入和环境回执，在结束后完成 `observer.json`。这些是**观察输出**，
不会传给 Agent。测试器只接收一个与本次项目及开始时间匹配的新 campaign；
出现多个尝试时要求先整理版本/尝试索引，避免挑选有利数据。

会话结束之后还需要独立复测**实际交付的补丁**。在已通过环境准备的执行宿主上，
使用 campaign 原始 InferRSI runtime 运行：

```bash
python -m e2e.qwen_image.retest \
  --project '<vllm-omni-git-repository>' --baseline-revision '<baseline_sha>' \
  --campaign '<campaign-directory>' --patch '<actual-agent-delivery.patch>' \
  --submission '<original-delivery-receipt.json>' \
  --output '<private-observation-directory>/independent' \
  --timeout-seconds '<independent-budget>'
```

该操作创建新的独立 Git 副本，从固定基线应用补丁，验证与已保存轮次/尝试的
完整源码身份一致，写 `seal.json` **之后**才调用现有 Harness 执行器。
不改变 Agent 项目的 HEAD、文件或旧实验记录。换行或权限差异不会被静默归一化。
如果基线最终胜出，session final 仍测基线；独立入口则测质量通过且测量完整的
最快 Agent 候选，同分取较早轮次。没有有效候选时保留缺口。

冻结命令必须适用于当前执行宿主。SSH、容器挂载、模型路径和设备分配继续由
原有 A2 skill/冻结命令负责；本用例不实现另一套远程调度器。
当 pytest 本身就在合格执行宿主时，可以为 live 命令增加
`--e2e-retest-locally --e2e-patch '<actual-agent-delivery.patch>'`。
超时只终止本次本地客户端；远端资源是否清理必须由看护者核实，未知不能写已清理。

保留原始结果后，可重复运行只读验收而不重新调用 Codex/NPU：

```bash
python -m pytest e2e/qwen_image/test_user_journey.py \
  --e2e-campaign '<campaign-directory>' \
  --e2e-observer '<private-observation-directory>/observer.json' \
  --e2e-artifacts '<new-private-report-directory>'
```

## 检查什么

| 输出 | 检查 |
| --- | --- |
| 每轮选择 | 方案事件先于首次编辑和测量；起点是上一轮最佳；有备选、所选措施、理由、预期、风险、引用和反馈 |
| 选择合理性 | 独立审阅者针对候选源码身份给出依据、差异引用及预期是否得到支持；缺失不能自动 PASS |
| 每轮优选 | 用 Harness 对原始结果重新判定质量、完整性、中位数和冻结门槛，再重算采用/拒绝、累计最佳；保留慢轮及失败轮 |
| 有效实验 | 不把相同源码/声明配置重复提交当新优化；检查真实 AB/BA 顺序，不能仅核对每侧样本集合 |
| 图片及原始时间 | 六组冻结 prompt，seed 42–47，1280×704；逐张读取 PNG 的 RGBA 字节与哈希，重算请求时间中位数 |
| 比较前提 | 搜索前跨独立进程的基线 A/A 像素相同；工作负载、环境身份、实际 scheduler 网格一致，不能只看请求的 steps 参数 |
| 最终结果 | session final 和独立实际补丁复测分别输出 B、F、B−F、百分比收益、正确性和性能结论 |
| 使用体验 | 是否需要看护者代操作，第一次卡住的步骤、介入时间/原因；普通用户回答或批准与代操作分开 |

源码、声明配置和运行所需的相对文件都必须在 campaign 的 include 范围内；
外部依赖/模型/设备仍需环境核验。单凭布尔质量结果、Agent 自述或宿主正常退出
不足以证明完整用例通过。该用例限定 warmed offline `Omni.generate` 到解码图片，
不能扩展成在线服务或 SLO 收益。

## 看护记录的输出契约

`observer.json` 位于私有观察目录。文件引用均为
`{"path":"relative/path", "sha256":"<actual-sha256>"}`，相对于这个目录；
不接受目录外路径或符号链接。它是看护过程中收集的证据索引，不是用户题包。
[`tests/campaigns/test_user_e2e_audit.py`](../tests/campaigns/test_user_e2e_audit.py) 中的完整合成示例
展示文件之间如何关联；示例时间、图像和身份仅为 CPU 负面控制。

| 字段 | 内容 |
| --- | --- |
| `preparation` | 准备回执 JSON 引用，字段见下文 |
| `round_choices` | 按 `candidate_id` 索引的三个宿主事件引用 `plan_event/first_edit_event/measurement_event` 和独立 `review` 引用 |
| `baseline_repeat` | `results` 为至少两次独立进程的基线 JSON 引用；对应 `fresh_process_ids/source_sha256`；以及 `search_started_at/effective_scheduler/environment_identity/workload_sha256` |
| `independent_directory` | 独立入口输出目录相对位置，包含 seal、实际补丁、重建源码、原始执行记录及 receipt |
| `interventions` | 全部介入，明确 `kind`（`assistance/answer/approval`）、`stage/at_seconds/reason/action`；没有介入时为 `[]`，缺失表示未知 |
| `final_reply` | 实际最终回复的文件引用 |

准备回执包含：`input_version/baseline_revision/plan_digest/protocol_frozen_at`；
`runspec` 的 `repository/revision/backend/device_class/device_count/model`；
`codex` 的实际 `client/version/model/configuration_sha256`；
`inferrsi.version/runtime_digest`；`a2_skill.name/sha256`；
`quality_cases` 引用 Agent 已冻结的六个 `{prompt,seed}`；
`workload` 引用冻结工作负载 JSON，包含 `width/height/dtype/batch_size/concurrency/`
`tensor_parallel_size/guidance_scale/num_inference_steps/timing_scope/requests`。
本例为 1280×704、bfloat16、batch/concurrency/TP/CFG 均为 1、原生 8 步，
`timing_scope` 为 `Omni.generate_to_decoded_image`，`requests` 与质量输入一致。
`expected_scheduler` 保存事前约定的实际 `num_steps/timesteps/sigmas`，与基线
跨进程复测及所有轮次对照；不能用仅记录请求 steps 的值替代运行网格。
`checks` 中的 `noninteractive_login/healthy_exclusive_device/model_bytes_verified/`
`baseline_repeat_before_search/owned_resources_cleaned`。未知字段保持未知，不能补造。
这些环境回执依赖可归属的看护/执行系统；CPU 复核不能重新证明远端硬件事实。

三个事件导出保留原始宿主事件 `raw`、一致的 `host_session_id` 和单调 `sequence`，
不要用文件 mtime 替代时序。
方案事件的 `choice` 包含 `starting_best_sha256/alternatives/chosen_measure/reason/`
`expected_effect/risk/sources/feedback_or_initial_analysis`。`review` 包含
`independent/reviewer/basis/diff_refs/candidate_sha256/verdict/expectation`；
`diff_refs` 为实际文件引用；`expectation` 为 `supported/refuted/inconclusive`。
作者自己切换角色不构成独立审阅。

质量/测量 JSON 继续满足 Harness 的冻结字段，并保留 `requests`，每个请求有
`seed/latency_ms/file/pixel_sha256`，组内 `median_ms`；以及实际
`effective_scheduler/environment_identity/workload_sha256`。
基线重复、逐轮、会话 final 和补丁独立复测的每个执行进程都要在结果中记录
`loaded_source_sha256`。从实际加载的源码定位纳入冻结清单的文件，用 Harness 的
`candidates.identity` 口径计算该组源码摘要。核查器按步骤比对所属组的基线或候选
快照摘要。缺少进程摘要时记为 INCONCLUSIVE，摘要不一致时记为 FAIL，并列出步骤。

A/A JSON 另保留 `process.id/started_at/finished_at`。这些补充字段由 Agent 或
观察系统的实际记录提供；旧记录缺少时报告证据不全，不补写历史事实。

## 判定及开发检查

实时运行会逐字节比对观察者留存的最终回复与本次 Codex 输出的 `final-reply.txt`。
只读回放核对留存文件的摘要与非空文本。验收人还须从该回复打开逐轮表、会话 final
回执、独立复测回执与补丁，并核对候选身份、基线和最终耗时、差值及百分比、
质量通过数与介入记录。pytest 报告列出回复摘要，供验收人定位原文。

`pytest-report.json` 保留 `PASS/FAIL/INCONCLUSIVE`、逐轮表格、两次最终比较及
介入情况。pytest 没有 INCONCLUSIVE 状态，因此证据缺失会让验收断言失败，
同时 JSON 中仍保留 INCONCLUSIVE，不能将它当质量失败或静默通过。
`test_completion_required_no_observer_assistance` 单独检查无代操作完成；
协助完成不改写质量/性能结果。无加速也不会凭空判使用流程失败，性能结论另列。
未显式选择 live 或 replay 时，两条昂贵用例跳过。

```bash
pytest tests/campaigns/test_user_e2e_audit.py
ruff check e2e tests/campaigns/test_user_e2e_audit.py tests/fixtures/user_e2e
```

这些 CPU 控制会启动真实 Harness 子进程，使用合成代码、PNG 和时间，覆盖优选链、
两份回执、换错合法补丁、交换 AB 顺序、事后补方案、缺审阅、环境缺口和人工介入。
它们通过只说明测试器行为得到检查，不说明本机完成了 Codex/A2 生图验收。
