# [RFC] 全量接入 cannbot-knowledge：MCP 常驻查询通道设计

> **Status: Proposed — 形态已选定，实施设计待评审。** 形态选择已由维护者确认（见 §0）；本文余下部分定义接入契约与切片，仍待评审接受。接受本文不等于授权实施、代码搬家或对外发布。
> Governing dependency: [#388](https://github.com/InferMatrixLab/InferRSI/issues/388)（外部技能/知识依赖治理）。本文是其"外链或 submodule 待决"的候选实现，落实为选定的第三方机制，但**不关闭 #388**。
> 接口依赖: [#387](https://github.com/InferMatrixLab/InferRSI/issues/387)（`read` / `collect` 公开接口，仍为 Proposed）。
> 文中所有上游 revision 与统计值都是**写作时的实测观测值**，不是本仓 pin，也不是验收基线。

## 0. 决策摘要

| 项 | 决定 | 位置 |
| --- | --- | --- |
| 接入形态 | **只读 MCP 常驻查询通道**（方案 D 升格为主接法）；内容永不进入本仓、wheel、`evidence/` | §5.1 |
| 触发语义 | **平台门控命中即查**，与本地是否命中无关；不再"零命中才补漏" | §5.2 |
| 平台门控来源 | 显式声明（`--backend` 或 grant），**不推断**；`--backend` 只接受单值 | §5.2 |
| 结果呈现 | **分栏并列**，外部结果不进 `items`，分数带 `score_scale`，不跨通道合并 | §5.3 |
| 每通道条数 | `cannbot-knowledge` 10 / `mindie-agent` 5 | §5.4 |
| `find` 默认 | **默认带外部查询**；CI 与单测必须显式 `--no-external` | §5.4 |
| MCP 面 | **透传**上游 `discover` / `search` / `read_card`，不收窄 | §8.5 |
| 证据 | receipt 只存 `locator` + `card_sha256` + `revision`，不含正文 | §7 |

### 为何从"候选比较"走到"选定 MCP"

前几轮评审已比较过五种形态（包内转换、submodule、外链锁缓存、MCP、混合）。选定 MCP 的决定性理由有两条，其余形态无法同时满足：

1. **许可**：上游为 CANN OSL v2.0，本仓为 Apache-2.0。MCP 让内容永不落盘，许可冲突从机制上消失。
2. **产能**：上游已有 10,550 张卡与自身的 ingest/lint/index 生产系统。任何"复制或缓存进本仓"的形态都在与一个数量级的产能赛跑。

## 1. 现状：InferRSI 的 Ascend / CANN 知识极度匮乏

这是本 RFC 的起因。在 `main` `6c7e237935a22cc5e90e954d4f397376e753e7d8`（2026-11-16）上实测 `src/inferrsi/knowledge/data/`：

| 项 | 实测值 | 说明 |
| --- | --- | --- |
| 打包知识数据总量 | 7.8 MiB / 850 个 md+json / 921 个文件 | 含全部 skill、引用与记录 |
| 知识记录总数 | 128 | `repo_packs` 108 + `knowledge_packs` 20 |
| 其中 Ascend 记录 | **22** | 占 17.2% |
| Ascend 记录中真正的内容卡 | **6** | 3 条 Qwen3-TTS audio、3 条 vLLM-Omni diffusion |
| Ascend 记录中仅是 skill 指针 | 16 | 只指向 `skills` 组件，不承载技术结论 |
| Ascend 硬件 skill | 14 / 143 个 `SKILL.md` | 380 KiB，43 个文件 |
| Ascend skill 正文 | 131,860 字节 | 14 篇 `SKILL.md` 合计 |
| Ascend skill 引用资料 | 174,559 字节 / 29 个文件 | 含 3 份上游 LICENSE 抄本 |
| **per-API 粒度知识卡** | **0** | 全仓没有任何一张卡对应单个 CANN/AscendC API |
| 出现 `aclnn*` / `__aicore__` 签名的文件 | **1** | `frameworks/torch-npu/.../references/development.md` |

对照上游 cannbot-knowledge 的同一维度：

| 项 | 上游实测值 | 倍数 |
| --- | --- | --- |
| 知识卡总数 | 10,550 | 内容卡 6 → 10,550（约 1,758×） |
| `ops/ascendc` 领域卡 | 6,804 | — |
| `API` 类型卡 | 3,875 | 本仓 0 |
| 其中 Ascend C API 卡 | **2,993** | — |
| `runtime` API 卡 | 516 | 本仓 0 |
| `Operator` 卡 | 903 | 本仓 0 |
| `Runbook` 卡 | 2,362 | 本仓无对应类型 |

**这是粒度差，不只是数量差。** InferRSI 现有 Ascend 知识是**技能粒度**：14 篇 `SKILL.md`，讲"怎么设计 tiling""怎么抓 ACLGraph""怎么诊断算子瓶颈"这类流程。上游是**API 与算子粒度**：单张卡讲清 `CeilDivision` 的参数、单位、平台约束、失效边界。两类内容不可互相替代——技能粒度无法回答"这个 API 在 a3 上是否支持、参数语义是什么"，而现有仓恰好完全缺失后者。

**为什么既有路径补不上。** [#91](https://github.com/InferMatrixLab/InferRSI/issues/91) 的蒸馏路径是"人力策展 + 逐条 PR"，本仓至今累计 6 条 Ascend 内容卡；按同一速度覆盖 2,993 张 API 卡在工程上不成立。而且这 6 条内容卡全部绑定具体模型 campaign（Qwen3-TTS 音码、MiniMax-H3 KV 复用、Qwen-Image 预热），描述的是"某模型在某卡上的某次优化"，不是可复用的通用 Ascend 机制。

**匮乏不等于现有内容有错。** 那 14 篇 skill 多数经 campaign 验证，质量可用；问题纯粹是覆盖面——`aclnn` / AscendC API / CANN Runtime / 算子实现这四类基础层次在本仓几乎是空白，导致 Agent 做 Ascend 任务时只能依赖 campaign 记忆与现场搜索，无法像 CUDA 路径那样先查知识再动手。

**这也解释了为什么不能只靠"蒸馏"：** 上游的知识生产侧（`knowledge-ingest`、两个 Operator producer、trace ingest）已经是一个持续产出系统，本仓若只做消费端的手工蒸馏，永远落后一个数量级的产能。本 RFC 讨论的正是"以什么形态消费这套外部产能"，而不是"要不要再造一套"。

## 2. 上游形态与许可（实测）

写作时对上游 `master` 的一次浅克隆观测（commit 观测值 `92dc260756e91e72e6dcd60f3996a4d54f43c8f5`，2026-11-16）：

| 项 | 值 |
| --- | --- |
| 知识正文根 | `knowledge/`，OKF v0.2 唯一 Bundle，Concept ID = Bundle 相对路径去 `.md` |
| 概念卡 / 导航 | 10,550 张 / 818 个 `index.md`（不参与检索） |
| 正文字节 | 约 118 MiB（不含导航）；目录占用约 143 MB |
| 领域分布 | `ops` 7,440 · `model` 1,890 · `contrib` 653 · `runtime` 530 · `common` 21 · `tools` 16 · `graph` 0（保留结构入口） |
| 状态分布 | `stable` 6,588 · `draft` 3,698 · `deprecated` 41 |
| 类型分布 | `API` 3,875 · `Runbook` 2,362 · `Guide` 1,788 · `Optimization` 1,087 · `Operator` 903 · `Concept` 287 · `Example` 23 · `Glossary` 2 |
| 平台受控值 | `a2` 1,765 · `a3` 1,610 · `310p` 395 · `agnostic` 228 · `kirin_x90` 198 · `kirin_9030` 172 |
| 写作语言 | 标题、描述与正文说明以中文写作；API 名、签名与代码为英文 |

**上游不是一个资料包，是一个知识系统：**

- `governance/` 有机器可读的 schema、路径 Profile、受控值规则与 20 余个 check 实现（来源、链接、索引同步、生命周期、信任层级）。
- 检索索引版本化（`cannbot-knowledge-index.v1`），带 `content_fingerprint` 与 `built_repository_state.commit`；索引相对当前提交过期时**拒绝服务**。
- `mcp-server/` 提供只读 `discover` / `search` / `read_card`，stdio 与 HTTP 双传输。
- 卡的来源资源**不在 Git 内**：`sources[].resource` 常指向 `cann-docs-raw/...` 或 `cann-recipes-raw/<repo>/<commit>/...`，由 `get_resources.sh` 恢复，默认不提交。**单张卡本身不自包含证据闭包。**

**许可。** 上游 LICENSE 为 CANN Open Software License Agreement v2.0，不是 OSI 许可：授予 limited、royalty-free、**non-transferable、non-sublicensable、revocable** 的许可，用途限于华为 AI 处理器系统。本仓为 Apache-2.0。把该内容打包进 `src/inferrsi/knowledge/data/` 并随 sdist/wheel 分发，或写入 `evidence/`，都会形成不可撤销的分发承诺。（本条为 LICENSE 文本的读法，**不是法律意见**，需要组织确认。）

**关于本仓内的 12 个 skill：** cannbot-knowledge 的 `.agents/skills/` 有 12 个 skill，但它们是知识仓自己的工具链——三个消费流程（`knowledge-query` 等，就是 MCP 背后的 CLI）、五个生产流程（`*-ingest`、operator producer）、两个治理（`knowledge-lint`、`knowledge-issue-handler`）、两个带 `VENDORED.md` 的裁剪副本。**CANN 领域知识全在 `knowledge/`，MCP 三工具已完整覆盖，不存在"skill 覆盖不到"的缺口。**

## 3. 形态选择记录

五种候选的比较与结论（保留作为决策依据，不再并行生效）：

| 形态 | 许可可分发 | 离线复现 | 漂移检测 | 结论 |
| --- | --- | --- | --- | --- |
| A 外链锁 + 包外缓存 | ✅ 不进包 | ✅ digest | ✅ | 未选：仍需同步与自建索引，收益低于 MCP |
| A′ 索引先行 | ✅ | ✅ | ✅ | 未选：同 A |
| B git submodule（KDA 式） | ⚠️ 需仓库层处理许可 | ✅ | ⚠️ 仅指针 | 未选：把许可义务交给集成方，且 143 MB 随克隆 |
| **C 全量转换进本仓** | ❌ 冲突 | ✅ | ❌ 副本即漂移 | **判死**：许可阻断 + 15 倍体积 + 每次上游前进需全量重转 |
| **D 只读 MCP** | ✅ 不落地 | ⚠️ 依赖上游 checkout | ✅ 由上游索引保证 | **选定**：唯一同时满足许可与规模，且上游已自带治理与索引 |
| E 混合 | — | — | — | 收敛为 D；C 仅以 [#91](https://github.com/InferMatrixLab/InferRSI/issues/91) 蒸馏精选子集的形式保留 |

KDA 的可借之处仍是纪律：README 锁表、`third_party_licenses/` 逐件许可、以及"submodule 指向做过去敏的发布点而非上游任意 commit"。本方案把这三条落在 §7 的 receipt 与 §5.3 的 `revision` 字段上，而不引入 submodule 这一形式。

## 4. 本仓检索侧事实

| 项 | 值 |
| --- | --- |
| `find` 实现 | `src/inferrsi/knowledge/knowledge_find.py`，commit `61303fa8`（#466 统一检索） |
| 检索模型 | 纯词法：`idf × 字段权重 × sqrt(出现次数)`，`FIELD_WEIGHTS` 见 `knowledge_find.py:42` |
| 来源 | `kinds=("case","skill","record")`，`load_corpus` 见 `:620` |
| 语料规模 | 143 篇 `SKILL.md` + 128 条记录 + cases，同进程内构建 |
| 确定性 | 完全离线、可复现、无 I/O 依赖 |
| 中文处理 | `tokens()` 已内建 CJK 双字切分（`:87`）；`_BACKEND_NAME_ALIASES` 含 `昇腾 → ascend` |
| 权威源枚举 | `AUTHORITIES = ("package", "checkout", "store")`（`knowledge_operations.py:25`） |

上游 MCP 侧实测：索引构建 73.9 秒（7,921,396 postings）；查询**冷启 3.67 秒 / 热 1.46 秒**；结果字段 `rank` / `score` / `match_basis` / `path` / `local_path` / `card_lines` / `card_sha256`；响应 schema `knowledge-search.v5`。

## 5. 接入设计

### 5.1 通道抽象

新增 `src/inferrsi/knowledge/channels.py`，把外部源收敛到同一协议，使 `find` 不认识具体是 cannbot 还是 MindIE：

```python
class Channel(Protocol):
    name: str                  # "cannbot-knowledge" | "mindie-agent"
    backend: str | None        # "ascend" | None（None = 平台无关）
    def describe(self) -> ChannelStatus: ...          # 探活，可缓存
    def search(self, query: str, *, platform: str | None,
               limit: int) -> ChannelResult: ...      # 返回定位符，不返回正文
    def read(self, locator: str) -> str: ...          # 单独调用，不在 find 热路径
```

```python
@dataclass
class ChannelStatus:
    state: str          # ok | not_enabled | unreachable | index_stale | timeout
                        # | version_mismatch | rejected | unknown | backend_unknown
    revision: str | None      # 上游 commit / catalog generation
    detail: str = ""
    fix: str = ""             # 修复命令，例如索引重建
    checked_at: float = 0.0

@dataclass
class ChannelResult:
    status: ChannelStatus
    items: list[ChannelHit]   # 失败时为空，但 state 必须说明原因
    elapsed_ms: int
```

`ChannelHit` 字段固定：`locator` / `title` / `summary` / `score` / `score_scale` / `status` / `platforms` / `card_sha256`。

`score_scale` 是关键：标明分数来自哪套评分（`"cannbot/knowledge-search.v5"` 或 `"mindie/graded-0.13.13"`），从结构上阻止调用方跨通道比较。

### 5.2 平台门控（决定"要不要查"）

```text
find(query, backend=?)
   │
   ├─ backend 未声明 ──► 不查外部；external[] 每项 state="backend_unknown"
   │                      且 fix 给出 "inferrsi find --backend ascend"
   │
   ├─ backend == ascend ──► 查询所有 backend ∈ {ascend, None} 的已授权通道
   │                         （cannbot-knowledge + mindie-agent）
   │
   └─ backend == cuda/mlx/... ──► 不查外部；external[] 为空
```

`backend` 来源优先级：`--backend` 显式参数 > grant 文件声明 > `backend_unknown`（**不猜**）。

`--backend` **只接受单值**。多平台任务由调用方分两次查询并各自保留结果。理由：多值会让输出无法回答"这条外部结果是为哪个平台召回的"，而上游平台纪律本身 fail-closed（`--platform` 必填、不混合各平台结果），本仓不应在门控层放宽这一语义。

这里刻意**不使用** `named_backends()`（`knowledge_find.py:739`）那种从查询词推断的方式：从"query 里出现了 asc"推断"这是 Ascend 任务"不可靠，且失败形态是静默查错平台。门控必须是显式事实。

### 5.3 分栏呈现（决定"怎么放"）

**不做混合排序。** 本仓 `idf` 建立在 143+128 条语料上，上游建立在 10,550 张卡上；同一个词在两套体系里的权重完全不同。任何跨通道合并都要发明归一化函数——那正是 RSI 明令禁止的"编造分数"。

```json
{
  "query": "AscendC tiling 参数",
  "backend": "ascend",
  "items": [ /* 只放本仓结果，沿用现有 ranked list */ ],
  "matched": 3,
  "external": [
    {
      "channel": "cannbot-knowledge",
      "state": "ok",
      "revision": "92dc260756e91e72e6dcd60f3996a4d54f43c8f5",
      "elapsed_ms": 1520,
      "score_scale": "cannbot/knowledge-search.v5",
      "items": [{
        "locator": "ops/ascendc/apis/simd_api/adv_api/cube_compute/matmul_tiling",
        "title": "Matmul Tiling类使用说明",
        "score": 18.4,
        "status": "stable",
        "platforms": ["a2", "a3"],
        "card_sha256": "049b4824...",
        "open": "inferrsi cannbot read ops/ascendc/apis/simd_api/adv_api/cube_compute/matmul_tiling"
      }]
    },
    {
      "channel": "mindie-agent",
      "state": "not_enabled",
      "detail": "no project grant for this checkout",
      "fix": "inferrsi mindie enable --domain <d>"
    }
  ],
  "notes": [
    "External results are not locally verified; scores are not comparable across channels.",
    "Pin external revisions from this output when citing them."
  ]
}
```

三条不可退让的规则：

1. **`items` 只放本仓结果。** 外部命中不进 `items`，避免下游按 `items` 处理时静默把未验证内容当成已验证。
2. **每个通道独立 `state`。** 一个通道失败不影响另一个；失败必须可见并附 `fix`。
3. **不合并 `score`。** 每个通道内部排序，跨通道并列。需要合并时由调用方决定。

### 5.4 执行模型：并行、预算、缓存

```text
find()
  ├─ 本地 Corpus 打分            （毫秒级，主线程）
  └─ 并行启动 N 个外部通道
        ├─ cannbot-knowledge   （子进程 / MCP stdio）
        └─ mindie-agent        （子进程，现有 call()）
```

用 `ThreadPoolExecutor`，通道间无共享状态；总耗时 ≈ max(各通道) 而非 sum。

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--external-timeout` | 8 秒 | 单通道上限 |
| `--no-external` | 关闭 | 只用本仓结果（CI 与离线场景） |
| `--external-limit` | 通道默认 | 覆盖单通道返回条数 |

| 通道 | 默认条数 | 理由 |
| --- | --- | --- |
| `cannbot-knowledge` | **10** | 定位符精度高（`path` 即 Concept ID），平台过滤已生效，多给几条有助于一次选中正确粒度 |
| `mindie-agent` | **5** | 返回 `navigation_only` 的 ref 定位符，粒度更粗；过多会淹没本地结果 |

**`find` 默认即带外部查询**（不带 `--no-external`），Ascend 任务开箱即双查。CI 与单测必须显式传 `--no-external`，以隔离外部通道可用性对基线的影响。

超时必须映射成 `state:"timeout"` 并附 `elapsed_ms`，**绝不能表现为空结果**。"查了但超时"与"查了没命中"是两种事实，混同会让 Agent 误判为"上游没有这个知识"。

| 缓存对象 | TTL | 理由 |
| --- | --- | --- |
| `describe()` / `discover` | 300 秒 | 探活成本高（冷启 3.7s），revision 不会秒级变化 |
| 通道授权状态与 checkout identity | 进程生命周期 | 文件系统事实 |
| search 结果 | 不缓存 | query 空间无限，缓存会让"上游更新"不可见 |

缓存只在内存，不落盘。

### 5.5 cannbot-knowledge 接法

新增 `src/inferrsi/apps/cannbot/`，结构镜像 `apps/mindie/`：

| 文件 | 职责 |
| --- | --- |
| `project.py` | 逐 checkout 授权；`~/.config/inferrsi/cannbot-projects/<sha256(repo)>.json` |
| `context.py` | 解析上游 JSON；2 MiB 上限、重复键拒绝、非有限数拒绝（复用 MindIE 的 `_object` / `_invalid_constant`） |
| `worker.py` | 用 grant 里的 python 起子进程，调上游 `knowledge_query.py search/read` 或 MCP |
| `mcp.py` | stdio MCP 代理三工具 |
| `receipt.py` | 落 receipt（§7） |

授权文件：

```json
{
  "schema": "inferrsi-cannbot-project/1",
  "checkout": "<abs-path>",
  "checkout_identity": {"device": 0, "inode": 0, "created": 0},
  "python": "<venv>/bin/python",
  "backend": "ascend",
  "default_platforms": ["a2"],
  "enabled_at": "<iso8601>"
}
```

`checkout_identity` 抄 MindIE 的做法（`.git` 的 device + inode + birthtime），防止 grant 被复制到另一个 clone 误用。`default_platforms` 让常用平台不必每次传；未声明时 `search` 直接报错（与上游 fail-closed 一致）。

### 5.6 MindIE Agent 接法

不重写，加一层 adapter 让现有 `call()` 满足 `Channel` 协议：

| 现状 | 改造 |
| --- | --- |
| `call("query", args)` 返回 `repository.query(navigation_only=True)` | adapter 映射为 `ChannelResult` |
| ref 形如 `mindie://<domain>/units/<id>@<gen>` | 作为 `locator` |
| grant 无 backend | 增可选 `backend` 字段 |
| `ReadFailure` 区分失败 | 映射到 `not_enabled` / `version_mismatch` / `rejected` |

`mindie-agent` 的 `describe` 已有：`repository.available()` + `component_version`（版本钉 `0.13.13`，`read_worker.py:24`）。

## 6. 为什么不采用其余形态（要点）

- **C 全量转换**：许可阻断分发；7.8 MiB → 约 126 MiB；上游每次前进需全量重转；与 #388 的单一权威来源规则冲突；10,550 条无法诚实标 `locally_verified=true`。**判死。**
- **B submodule**：把 CANN OSL 的许可义务交给每个集成方；143 MB 随克隆；`gitcode` 可达性成为所有开发者的硬依赖。KDA 能这么做是因为它不 pip 分发且 submodule 是 MIT/过过过洗的发布点。
- **A/A′ 外链锁缓存**：机制正确但与 MCP 重叠——两者都在解决"如何引用外部内容"，而 MCP 让上游承担索引与治理。保留为未来若需要"完全离线复现"时的备选，当前不实现。

## 7. 证据与许可

### 7.1 receipt 只存定位符

```json
{
  "schema": "inferrsi-external-receipt/1",
  "channel": "cannbot-knowledge",
  "revision": "92dc260756e91e72e6dcd60f3996a4d54f43c8f5",
  "index": {"schema": "cannbot-knowledge-index.v1", "version": 3,
            "content_fingerprint": "0047983f..."},
  "query": "CeilDivision 向上取整",
  "platforms": ["a2"],
  "decision": "确认 a3 上的取整语义",
  "hits": [{
    "locator": "ops/ascendc/apis/utils_api/cpp_stdlib/math_functions/ceil_division",
    "card_sha256": "b97cbe82492d25cc0363d1852eddcf87d991c9d75a57891a9aed3e75188ffc86",
    "status": "stable", "platforms": ["a2", "a3"]
  }],
  "delivered": "locators_only",
  "locally_verified": false
}
```

**不含卡片正文、不含 frontmatter 全文、不含 `local_path`。** 前两者会把 CANN OSL 内容带进 `evidence/`（把许可问题从 `data/` 原样搬到 `evidence/`）；后者是个人绝对路径，违反隐私规则。

`card_sha256` 保证"我引用的确实是这一版这张卡"，且摘要不构成再分发。

### 7.2 引用话术与验证状态

引用外部结论必须写成 `cannbot-knowledge @ <commit>` 或 `mindie-knowledge 0.13.13 / <domain>@<gen>`，并显式标注 `locally_verified=false`。外部命中**不参与** `PASS` 判定（沿用 `AGENTS.md` 的证据纪律）。

## 8. 代码改动清单

| # | 文件 | 改动 | 风险 |
| --- | --- | --- | --- |
| 1 | `knowledge/channels.py` | 新增 `Channel` / `ChannelStatus` / `ChannelHit` / `ChannelResult` / `ChannelRegistry` | 无 |
| 2 | `knowledge/knowledge_find.py:732` `find()` | 增 `channels` / `backend` / `external_limit` / `external_timeout`；并行调度；输出 `external[]` | 需保证 `channels=None` 时行为**逐字节一致** |
| 3 | `knowledge/knowledge_find.py:620` `load_corpus` | 不改 | — |
| 4 | `knowledge/knowledge_operations.py:25` `AUTHORITIES` | **不改**（外部内容不作为 bundle 读取） | — |
| 5 | `apps/cannbot/*` | 新增五个文件 | 新代码 |
| 6 | `apps/mindie/` | 增 `channel.py` adapter；grant 增 `backend` | 小 |
| 7 | `apps/cli/arguments.py` | `find` 增 `--backend` / `--no-external` / `--external-limit` / `--external-timeout`；新增 `cannbot` 子命令组 | 小 |
| 8 | `apps/cli/__init__.py` | 分发 `cannbot`；`campaign import-cannbot` / `import-mindie` 统一 | 中 |
| 9 | `tests/` | fake channel（本地 stdio 假进程 + 固定 JSON），覆盖全部 `state` | 必需 |

**第 2 条的不变量：** `channels` 为空或 `--no-external` 时，`find` 的输出必须与 #466 之后的行为完全一致。必须写成测试，否则外部通道会悄悄改变现有 143 篇 skill 的排序基线。

**第 4 条的理由：** 不把 `external` 加进 `AUTHORITIES`，意味着 `find` 的 `read_args` / `open_argv` 不会指向外部卡（避免生成一个执行即错的命令），外部读走独立的 `cannbot read`。

## 9. 使用方式

### 9.1 首次配置（每台机器、每个 checkout 一次）

```bash
inferrsi cannbot enable \
  --checkout ~/src/cannbot-knowledge \
  --python ~/venvs/cannbot/bin/python \
  --backend ascend \
  --platform a2

inferrsi mindie enable --domain <domain> --backend ascend
```

前置条件由用户负责：上游要求 Python 3.10+、`uv`、**完整 checkout**、**索引已构建**。

自查与自修复：

```bash
inferrsi cannbot describe
# {"state":"ok","revision":"92dc2607...","cards":10550,
#  "index":{"version":3,"content_fingerprint":"0047983f..."}}
```

```text
state: index_stale
detail: index built at <old> differs from checkout <new>
fix:    cd ~/src/cannbot-knowledge && python3 .agents/skills/knowledge-query/scripts/knowledge_index.py build
```

### 9.2 日常检索（Ascend 任务，常驻双查）

```bash
$ inferrsi find "AscendC tiling 参数怎么算" --backend ascend
```

```text
本仓 (backend=ascend)
  1. ascendc-tiling-design                       score 42.1
  2. ascend-performance-analysis                 score 31.7

外部通道
  cannbot-knowledge @ 92dc2607  ok  1.5s  3 hits
    1. Matmul Tiling类使用说明          18.4  ops/ascendc/apis/.../cube_compute/matmul_tiling
    2. 使用高阶API时配套的Tiling实现     17.9  ops/ascendc/guides/.../tiling
    3. Matmul tiling 形状与核数推导链    17.2  ops/ascendc/guides/.../derivation_chain
    → inferrsi cannbot read <locator>

  mindie-agent                  not_enabled  (fix: inferrsi mindie enable --domain <d>)
```

本仓有命中时**照样**查外部；两个通道各自一段；分数不跨栏比较。

### 9.3 非 Ascend 任务 / 未声明 backend

```bash
$ inferrsi find "CUDA graph capture" --backend cuda
# 只查本仓；external: []
```

```text
external: [{"channel":"cannbot-knowledge","state":"backend_unknown",
            "fix":"inferrsi find --backend ascend"}]
```

### 9.4 读外部卡正文

```bash
inferrsi cannbot read ops/ascendc/apis/utils_api/cpp_stdlib/math_functions/ceil_division
inferrsi cannbot read <locator> --page 2        # 分页续读，默认 200 行
inferrsi mindie read <ref>
```

正文只在终端呈现，不落盘、不进 receipt。

### 9.5 Agent 挂载（Claude Code / Codex）

```bash
inferrsi cannbot serve     # stdio MCP：discover / search / read_card
```

**透传，不收窄。** 三工具的名称、参数与语义与上游一致，只多一层授权检查、receipt 与错误归一化。理由：自造收窄契约会在上游演进（新增过滤参数、`search` schema 从 v5 升级）时变成必须同步维护的负债，而透传可依靠 `schema_version` 直接暴露差异。授权检查、receipt、错误归一化都在这一层完成。

### 9.6 进 campaign evidence

```bash
inferrsi cannbot search "CeilDivision 向上取整" --platform a2 \
  --decision "确认 a3 上的取整语义" \
  --receipt .inferrsi/receipts/ceil.json

inferrsi campaign import-cannbot .inferrsi/receipts/ceil.json
```

## 10. 切片

| 片 | 内容 | 依赖 | 可独立合入 |
| --- | --- | --- | --- |
| C0 | `channels.py` 协议 + fake channel + 全部 state 的测试 | — | ✅ |
| C1 | `find()` 融合 + `--backend` 门控（只接 fake channel） | C0 | ✅ |
| C2 | `apps/cannbot/` 的 `enable/disable/describe` | C0 | ✅ |
| C3 | cannbot `search` / `read`（worker + 子进程） | C2 | ✅ |
| C4 | MindIE channel adapter + grant `backend` | C0 | ✅ |
| C5 | `cannbot serve`（stdio MCP 代理） | C3 | ✅ |
| C6 | `receipt.py` + `campaign import-cannbot` 统一 | C3、C4 | ✅ |

C1 先行的理由：它把"平台门控 + 分栏 + 超时语义"这套契约钉死，之后两个真源接入都只是实现 `Channel`，不会反过来改 `find` 的输出结构。

**C4 建议紧跟 C0**，因为 MindIE 已有 `call()` 与 `describe()`，adapter 成本低，能最早验证协议抽象是否成立。

## 11. 风险

| # | 风险 | 现状 | 缓解 |
| --- | --- | --- | --- |
| R1 | 热路径增加 1.5–3.7s | 实测 | 并行 + `describe` 缓存 300s + `--no-external` |
| R2 | 破坏 `find` 的确定性与离线可测 | 真实风险 | 不传 `--backend` 时不查外部；`--no-external` 关闭全部通道；fake channel 覆盖全部 state；两种路径输出逐字节固定 |
| R3 | 上游索引过期导致"昨天能查今天不能查" | 上游 fail-closed | `state: index_stale` + `fix`；不做静默重试 |
| R4 | 平台枚举不可映射（`a2/a3/950/310p` vs `ascend`） | 未决 | grant 声明 `backend` + `platform` 两级；未知值拒绝，不猜 |
| R5 | 许可内容意外落盘 | 已设计 | receipt 只存 locator + sha256；剔除 `local_path` |
| R6 | 两套评分被下游误混 | 已设计 | `score_scale` 字段 + 分栏结构 + `notes` |
| R7 | `uv` / 完整 checkout 在 CI 不可用 | 未验证 | 单测只用 fake channel；真上游走人工验收 |
| R8 | MindIE 0.13.13 版本钉导致升级即断 | 现有行为 | `state: version_mismatch` + `fix` |

## 12. 关闭条件

本文作为 RFC 关闭时应当满足：

- [ ] 评审接受 §5 的通道契约（`Channel` 协议、`state` 枚举、`external[]` 结构、`score_scale`）。
- [ ] 评审接受 §5.2 的平台门控语义：显式声明、单值、不推断。
- [ ] 评审接受 §7 的 receipt 形状与"不含正文"的许可边界；Q1（CANN OSL 立场）有组织层面的答复或明确接受为"实施前再定"。
- [ ] 评审接受 §5.4 的默认值：`find` 默认查外部、每通道 10/5、超时 8 秒。
- [ ] 确认 §8 第 2 条与第 4 条不变量写入测试。
- [ ] 明确与 [#388](https://github.com/InferMatrixLab/InferRSI/issues/388) / [#387](https://github.com/InferMatrixLab/InferRSI/issues/387) 的关系：本文不关闭 #388，`external[]` 需在 #387 的 schema 中登记。
- [ ] 实施切片（C0–C6）另开 issue，本 Issue 不承接代码合入。

## 13. 相关

- [#388](https://github.com/InferMatrixLab/InferRSI/issues/388) 外部技能内容的依赖、版本锁定与可复现导入（治理 RFC，仍 Open）
- [#387](https://github.com/InferMatrixLab/InferRSI/issues/387) K/H/B 与 Apps 公开接口详细设计（`read` / `collect`，仍 Proposed）
- [#362](https://github.com/InferMatrixLab/InferRSI/issues/362) 三模块目标架构（已接受方向）
- [#91](https://github.com/InferMatrixLab/InferRSI/issues/91) SearchSpace 蒸馏覆盖跟踪（本仓内唯一权威来源路径）
- [#43](https://github.com/InferMatrixLab/InferRSI/issues/43) 历史 `license: UNKNOWN` 与许可链遗留约束
- [#466](https://github.com/InferMatrixLab/InferRSI/pull/466) 统一 `find` 检索（本文接入的宿主接口）
- [#114](https://github.com/InferMatrixLab/InferRSI/pull/114) cann/cannbot 固定阶段证据蒸馏入库（既有蒸馏先例，不是外部依赖机制）

## 14. 参考实现（外部）

- [cann/cannbot-knowledge](https://gitcode.com/cann/cannbot-knowledge)：OKF v0.2 + CANNBot Profile，自带 governance / Query / Lint / MCP。
- [NVlabs/kda](https://github.com/NVlabs/kda)：submodule 钉版本 + README 锁表 + `third_party_licenses/` 逐件许可 + 明确"submodule 不受本仓一方许可覆盖"。**可借的是纪律，不是形式。**
