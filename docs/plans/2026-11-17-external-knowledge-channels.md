# 外部知识通道设计：cannbot-knowledge 与 MindIE Agent 的常驻查询接入

> Status: Proposed（设计草案）。本文只定义接入设计与使用方式，不构成实施授权。
> 上位依赖：[#476](https://github.com/InferMatrixLab/InferRSI/issues/476)（候选形态与许可边界）、[#388](https://github.com/InferMatrixLab/InferRSI/issues/388)（外部依赖治理）、[#387](https://github.com/InferMatrixLab/InferRSI/issues/387)（Knowledge 公开接口）。
> 文中所有上游 revision 与统计值都是写作时的实测观测值，不是本仓 pin。

## 0. 相对前一版的关键变更

前一版设计把外部通道当作**补漏**：本地 `find` 零命中时才提示外部存在。本文改为**常驻并行查询**：

| 维度 | 前一版（补漏） | 本版（常驻） |
| --- | --- | --- |
| 触发条件 | `no_match == true` | 平台门控命中即查，无论本地是否命中 |
| 语义 | 外部源是兜底 | 外部源是**第二知识源**，与本地并列 |
| 输出 | `external_channels` 提示条目 | `external[]` 实际检索结果 |
| 平台门控 | 无 | 必须显式声明；`ascend` 任务常驻查询，其他平台不触发 |

理由：Ascend 任务的真实知识分布是"本仓有 14 篇流程型 skill，上游有 10,550 张 API/算子卡"。只在零命中时查，等于假设"本地一旦有命中，外部就没有增量"——这个假设在粒度互补的场景下明显不成立（本仓命中"如何设计 tiling 流程"，上游同时有"`Matmul Tiling` 类的具体参数"）。

## 1. 现状与约束（实测）

### 1.1 本仓知识侧

| 项 | 值 |
| --- | --- |
| `find` 实现 | `src/inferrsi/knowledge/knowledge_find.py`，commit `61303fa8`（#466 统一检索） |
| 检索模型 | 纯词法：`idf × 字段权重 × sqrt(出现次数)`，`FIELD_WEIGHTS` 见 `knowledge_find.py:42` |
| 来源 | `kinds=("case","skill","record")`，`load_corpus` 见 `:620` |
| 语料规模 | 143 篇 `SKILL.md` + 128 条记录 + cases，同进程内构建 |
| 确定性 | 完全离线、可复现、无 I/O 依赖 |
| Ascend 内容卡 | 6 张（详见 #476「现状」节） |

### 1.2 cannbot-knowledge MCP 侧

| 项 | 实测值 |
| --- | --- |
| 索引构建 | 73.9 秒（10,550 卡，7,921,396 postings） |
| 查询延迟 | 冷启 3.67 秒 / 热 1.46 秒 |
| 检索结果字段 | `rank` / `score` / `match_basis` / `path` / `local_path` / `card_lines` / `card_sha256` |
| 响应 schema | `knowledge-search.v5`，含 `request_sha256` 与 `index.repository_state.commit` |
| 平台纪律 | `--platform` 必填，缺失即报错（fail-closed，不混合各平台） |
| 索引过期 | 拒绝服务并给出 `index_stale`，不自动重建 |
| 工具面 | `discover` / `search` / `read_card`，全部 `read_only` |
| 许可 | CANN OSL v2.0（内容不得进包、进 evidence） |

### 1.3 MindIE Agent 侧

| 项 | 现有实现 |
| --- | --- |
| 适配代码 | `src/inferrsi/apps/mindie/`（639 行） |
| 工具体 | `knowledge_query` / `knowledge_explain` |
| 运行时 | `subprocess.run([grant["python"], "-I", "-B", worker, ...])`，`project.py:103` |
| 版本钉 | `mindie-knowledge == 0.13.13` 硬校验，`read_worker.py:24` |
| 授权 | 逐 checkout，`~/.config/inferrsi/mindie-projects/<sha256>.json` |
| 检索 | `repository.query(navigation_only=True)`，返回 ref 定位符 |

### 1.4 由此产生的设计约束

1. **两套评分不可比。** 本仓的 `idf` 建立在 143+128 条语料上，上游建立在 10,550 张卡上；同一个词在两边的 idf 与权重体系完全不同。任何"混合排序"都需要我们自己发明一个归一化函数——那是本轮 RSI 明令禁止的"编造分数"。
2. **外部检索是 I/O，不是计算。** 1.5–3.7 秒相对本仓 `find` 的毫秒级是数量级差异，且失败模式有七种（未授权 / 不可达 / 索引过期 / 平台未知 / 超时 / 协议错 / 上游拒绝）。
3. **外部结果不确定。** 上游 checkout 更新后同一 query 结果会变，因此**每次输出必须携带 revision**，否则 `find` 的结果无法被任何人复现。
4. **许可边界不因常驻而放松。** 正文永不落盘；进 receipt 的只有 `path` + `card_sha256` + `revision`。

## 2. 核心设计：通道抽象 + 平台门控 + 分栏呈现

### 2.1 通道抽象

新增 `src/inferrsi/knowledge/channels.py`，把两个外部源收敛到同一协议，使 `find` 不认识具体是 cannbot 还是 MindIE：

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
    state: str          # ok | not_enabled | unreachable | index_stale
                        # | version_mismatch | rejected | unknown
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

`score_scale` 是关键：标明这个分数来自哪套评分（`"cannbot/knowledge-search.v5"` 或 `"mindie/graded-0.13.13"`），从结构上阻止调用方跨通道比较。

### 2.2 平台门控（决定"要不要查"）

数据流：

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

`backend` 来源优先级：

1. `inferrsi find --backend ascend`（显式参数，最高）
2. grant 文件里声明的 backend（`cannbot enable --backend ascend`）
3. 都没有 → `backend_unknown`，**不猜**

`--backend` **只接受单值**。一次调用只能声明一个 backend；同时涉及 Ascend 与 CPU host 侧等多平台任务，由调用方分两次查询并各自保留结果。理由：多值会让输出无法回答"这条外部结果是为哪个平台召回的"，而外部源的平台纪律本身是 fail-closed 的（上游 `--platform` 要求明确目标平台，不混合各平台结果），本仓不应在门控层放宽这一语义。

这里刻意不使用 `named_backends()`（`knowledge_find.py:739`）那种从查询词推断的方式：从"这个 query 里出现了 asc"推断"这个任务是 Ascend 任务"是不可靠的，且失败形态是静默查错平台。门控必须是显式事实。

### 2.3 分栏呈现（决定"怎么放"）

**不做混合排序。** 输出结构：

```json
{
  "query": "AscendC tiling 参数",
  "backend": "ascend",
  "items": [ /* 本仓结果，沿用现有 ranked list */ ],
  "matched": 3,
  "external": [
    {
      "channel": "cannbot-knowledge",
      "state": "ok",
      "revision": "92dc260756e91e72e6dcd60f3996a4d54f43c8f5",
      "elapsed_ms": 1520,
      "score_scale": "cannbot/knowledge-search.v5",
      "items": [
        {
          "locator": "ops/ascendc/apis/simd_api/adv_api/cube_compute/matmul_tiling",
          "title": "Matmul Tiling类使用说明",
          "score": 18.4,
          "status": "stable",
          "platforms": ["a2", "a3"],
          "card_sha256": "049b4824...",
          "open": "inferrsi cannbot read ops/ascendc/apis/simd_api/adv_api/cube_compute/matmul_tiling"
        }
      ]
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

1. **`items` 只放本仓结果。** 外部命中不进 `items`，避免任何下游按 `items` 处理时会静默把未验证内容当成已验证。
2. **每个通道独立 `state`。** 一个通道失败不影响另一个；失败必须可见并附 `fix`。
3. **不合并 `score`。** 每个通道内部排序，跨通道并列。需要合并时由调用方决定，不由 `find` 代劳。

## 3. 执行模型：并行、预算、降级

### 3.1 并行

```text
find()
  ├─ 本地 Corpus 打分            （毫秒级，主线程）
  └─ 并行启动 N 个外部通道
        ├─ cannbot-knowledge   （子进程 / MCP stdio）
        └─ mindie-agent        （子进程，现有 call()）
```

用 `concurrent.futures.ThreadPoolExecutor`，通道之间无共享状态。总耗时 ≈ max(各通道)，而不是 sum。

### 3.2 预算与降级

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--external-timeout` | 8 秒 | 单通道上限 |
| `--no-external` | — | 只用本仓结果（CI 与离线场景） |
| `--external-limit` | 通道默认（见下） | 覆盖单通道返回条数 |

**每通道条数默认值：**

| 通道 | 默认条数 | 理由 |
| --- | --- | --- |
| `cannbot-knowledge` | **10** | 10,550 张卡、2,993 张 Ascend C API 卡，定位符精度高（`path` 即 Concept ID），多给几条能让调用方一次选中正确粒度 |
| `mindie-agent` | **5** | 返回的是 `navigation_only` 的 ref 定位符，粒度更粗；过多会淹没本地结果 |

`find` **默认即带外部查询**（不带 `--no-external`），因此 Ascend 任务开箱就是双查。CI 与单测必须显式传 `--no-external`，以保证基线不受外部通道可用性影响。

超时必须映射成 `state: "timeout"` 并附 `elapsed_ms`，**绝不能表现为空结果**。"查了但超时"与"查了没命中"是两种事实，混同会让 Agent 误判为"上游没有这个知识"。

### 3.3 缓存

| 对象 | TTL | 理由 |
| --- | --- | --- |
| `describe()` / `discover` | 300 秒 | 探活成本高（冷启 3.7s），且 revision 不会秒级变化 |
| 通道授权状态与 checkout identity | 进程生命周期 | 文件系统事实 |
| search 结果 | 不缓存 | query 空间无限，且缓存会让"上游更新"不可见 |

缓存落在内存，不落盘；落盘缓存会引入"缓存里的 revision 与当前不一致"的经典问题。

## 4. 两个通道的具体接法

### 4.1 cannbot-knowledge

新增 `src/inferrsi/apps/cannbot/`，结构镜像 `apps/mindie/`：

| 文件 | 职责 |
| --- | --- |
| `project.py` | 逐 checkout 授权；`~/.config/inferrsi/cannbot-projects/<sha256(repo)>.json` |
| `context.py` | 解析上游 JSON；2 MiB 上限、重复键拒绝、非有限数拒绝（复用 MindIE 的 `_object` / `_invalid_constant`） |
| `worker.py` | 用 grant 里的 python 起子进程，调 `knowledge_query.py search/read` 或 MCP `search`/`read_card` |
| `mcp.py` | stdio MCP 代理三工具，供 agent 直接挂载 |
| `receipt.py` | 落 receipt（§5） |

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

`default_platforms` 让常用平台不必每次传；未声明时 `search` 直接报错（与上游 fail-closed 一致）。

### 4.2 MindIE Agent

不重写，增加一层 adapter 让现有的 `call()` 满足 `Channel` 协议：

| 现状 | 改造 |
| --- | --- |
| `call("query", args)` 返回 `repository.query(navigation_only=True)` | adapter 中映射为 `ChannelResult` |
| ref 形如 `mindie://<domain>/units/<id>@<gen>` | 作为 `locator` |
| backend 未声明 | grant 增可选的 `backend` 字段，默认 `ascend` |
| `state` 由 `ReadFailure` 区分 | 映射到 `not_enabled` / `version_mismatch` / `rejected` |

`mindie-agent` 的 `describe` 已有：`repository.available()` + `component_version`。

## 5. 证据与许可

### 5.1 receipt 只存定位符

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

**不含卡片正文、不含 frontmatter 全文、不含 local_path。** 原因：前两者会把 CANN OSL 内容带进 `evidence/`，把许可问题从 `data/` 原样搬到 `evidence/`；`local_path` 是个人绝对路径，违反隐私规则。

`card_sha256` 的作用是"我引用的确实是这一版这张卡"，且摘要不构成再分发。

### 5.2 引用话术

引用外部结论时必须写成：`cannbot-knowledge @ <commit>` 或 `mindie-knowledge 0.13.13 / <domain>@<gen>`，并显式标注 `locally_verified=false`。外部命中**不参与** `PASS` 判定（沿用 `AGENTS.md` 的证据纪律）。

## 6. 代码改动清单

| # | 文件 | 改动 | 风险 |
| --- | --- | --- | --- |
| 1 | `knowledge/channels.py` | 新增 `Channel` / `ChannelStatus` / `ChannelHit` / `ChannelResult` / `ChannelRegistry` | 无 |
| 2 | `knowledge/knowledge_find.py:732` `find()` | 增 `channels`、`backend`、`external_limit`、`external_timeout` 参数；并行调度；输出 `external[]` | 需保证 `channels=None` 时行为与现在**逐字节一致** |
| 3 | `knowledge/knowledge_find.py:620` `load_corpus` | 不改 | — |
| 4 | `knowledge/knowledge_operations.py:25` `AUTHORITIES` | **不改**（外部内容不作为 bundle 读取） | — |
| 5 | `apps/cannbot/*` | 新增 five files | 新代码 |
| 6 | `apps/mindie/` | 增 `channel.py` adapter；grant 增 `backend` | 小 |
| 7 | `apps/cli/arguments.py` | `find` 增 `--backend` / `--no-external` / `--external-limit` / `--external-timeout`；新增 `cannbot` 子命令组 | 小 |
| 8 | `apps/cli/__init__.py` | 分发 `cannbot`；`campaign import-cannbot` / `import-mindie` 统一 | 中 |
| 9 | `tests/` | fake channel（本地 stdio 假进程 + 固定 JSON），覆盖七种 `state` | 必需 |

第 2 条的不变量：**`channels` 为空或 `--no-external` 时，`find` 的输出必须与 #466 之后的行为完全一致。** 这条要写成测试，否则外部通道会悄悄改变现有 143 篇 skill 的排序基线。

## 7. 使用方式

### 7.1 首次配置（每台机器、每个 checkout 一次）

```bash
# cannbot-knowledge
inferrsi cannbot enable \
  --checkout ~/src/cannbot-knowledge \
  --python ~/venvs/cannbot/bin/python \
  --backend ascend \
  --platform a2

# MindIE（沿用现有命令，仅补 backend）
inferrsi mindie enable --domain <domain> --backend ascend
```

自查：

```bash
inferrsi cannbot describe
# {"state":"ok","revision":"92dc2607...","cards":10550,
#  "index":{"version":3,"content_fingerprint":"0047983f..."}}

inferrsi mindie describe
# {"available":true,"component_version":"0.13.13","domain":"<d>"}
```

失败时直接给修复命令：

```text
state: index_stale
detail: index built at <old> differs from checkout <new>
fix:    cd ~/src/cannbot-knowledge && python3 .agents/skills/knowledge-query/scripts/knowledge_index.py build
```

### 7.2 日常检索（Ascend 任务，常驻双查）

```bash
$ inferrsi find "AscendC tiling 参数怎么算" --backend ascend
```

输出（示意）：

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

要点：本地有命中时**照样**查外部；两个通道各自一段；分数不跨栏比较。

### 7.3 非 Ascend 任务

```bash
$ inferrsi find "CUDA graph capture" --backend cuda
# 只查本仓；external: []
```

不传 `--backend` 且 grant 未声明时：

```text
external: [{"channel":"cannbot-knowledge","state":"backend_unknown",
            "fix":"inferrsi find --backend ascend"}]
```

### 7.4 读外部卡正文

```bash
inferrsi cannbot read ops/ascendc/apis/utils_api/cpp_stdlib/math_functions/ceil_division
inferrsi cannbot read <locator> --page 2        # 分页续读，默认 200 行
inferrsi mindie read <ref>                      # MindIE 侧沿用现有 read 动作
```

正文只在终端呈现，不落盘、不进 receipt。

### 7.5 Agent 挂载（Claude Code / Codex）

```bash
inferrsi cannbot serve     # stdio MCP：discover / search / read_card
```

**透传，不收窄。** 三个工具的名称、参数与语义与上游保持一致，只是多一层授权检查、receipt 与错误归一化。理由：自造一层收窄契约会在上游演进（例如新增过滤参数、`search` schema 从 v5 升级）时变成必须同步维护的负债，而透传可以靠 `schema_version` 字段直接暴露差异。在 agent 配置中注册一条命令即可。

### 7.6 进 campaign evidence

```bash
inferrsi cannbot search "CeilDivision 向上取整" --platform a2 \
  --decision "确认 a3 上的取整语义" \
  --receipt .inferrsi/receipts/ceil.json

inferrsi campaign import-cannbot .inferrsi/receipts/ceil.json
```

## 8. 切片

| 片 | 内容 | 依赖 | 可独立合入 |
| --- | --- | --- | --- |
| C0 | `channels.py` 协议 + fake channel + 七种 state 的测试 | — | ✅ |
| C1 | `find()` 融合 + `--backend` 门控（只接 fake channel，不接真源） | C0 | ✅ |
| C2 | `apps/cannbot/` 的 `enable/disable/describe` | C0 | ✅ |
| C3 | cannbot `search` / `read`（worker + 子进程） | C2 | ✅ |
| C4 | MindIE channel adapter + grant `backend` | C0 | ✅ |
| C5 | `cannbot serve`（stdio MCP 代理） | C3 | ✅ |
| C6 | `receipt.py` + `campaign import-cannbot` 统一 | C3、C4 | ✅ |

C1 先行的理由：它把"平台门控 + 分栏 + 超时语义"这套契约固定下来，之后两个真源接入都只是实现 `Channel`，不会反过来改 `find` 的输出结构。

## 9. 风险与未决

| # | 风险 | 现状 | 缓解 |
| --- | --- | --- | --- |
| R1 | 热路径增加 1.5–3.7s | 实测 | 并行 + `describe` 缓存 300s + `--no-external` |
| R2 | 破坏 `find` 的确定性与离线可测 | 真实风险 | 不传 `--backend` 时不查外部；`--no-external` 关闭全部通道；fake channel 覆盖全部 state；两种路径下的输出都逐字节固定 |
| R3 | 上游索引过期导致"昨天能查今天不能查" | 上游 fail-closed | `state: index_stale` + `fix`；不做静默重试 |
| R4 | 平台枚举不可映射（`a2/a3/950/310p` vs `ascend`） | 未决 | grant 声明 `backend` + `platform` 两级；未知值拒绝，不猜 |
| R5 | 许可内容意外落盘 | 已设计 | receipt 只存 locator + sha256；模板里剔除 `local_path` |
| R6 | 两套评分被下游误混 | 已设计 | `score_scale` 字段 + 分栏结构 + `notes` |
| R7 | `uv` / 完整 checkout 在 CI 不可用 | 未验证 | 单测只用 fake channel；真上游走人工验收 |
| R8 | MindIE 0.13.13 版本钉导致升级即断 | 现有行为 | `state: version_mismatch` + `fix`，与现状一致 |

### 已定决策

以下四项已确认，不再是待决项；实现按此执行，若需变更须另行评审。

| # | 问题 | 决定 | 落实位置 |
| --- | --- | --- | --- |
| D1 | `--backend` 是否允许一次声明多个 | **只允许一个。** 多平台任务由调用方分两次查询，各自保留结果；不接受多值，避免输出无法回答"这条外部结果是为哪个平台召回的" | §2.2 平台门控、§6 改动 7 |
| D2 | `find` 默认是否带 `--no-external` | **不带。** Ascend 任务开箱即双查；CI 与单测必须显式传 `--no-external`，以隔离外部通道可用性对基线的影响 | §3.2 预算与降级、§6 改动 9 |
| D3 | `external[]` 每通道默认条数 | **`cannbot-knowledge` 10 条 / `mindie-agent` 5 条。** 上游定位符精确到 `path` 且平台过滤已生效，多给几条有助于一次选中正确粒度；MindIE 返回粗粒度 ref，过多会淹没本地结果 | §3.2 每通道条数默认值 |
| D4 | `cannbot serve` 的 MCP 面 | **透传上游 `discover` / `search` / `read_card` 三工具**，名称、参数、语义保持一致；只增加授权检查、receipt 与错误归一化。不收窄，以免在上游 `search` schema 升级时产生必须同步维护的自造契约 | §7.5 Agent 挂载 |

## 10. 与既有文档的关系

| 文档 | 关系 |
| --- | --- |
| #476 | 本文把方案 D（MCP 旁路）升格为主接法，并补充"常驻查询"语义；#476 §4 的方案 D 需据此修订 |
| #388 | 本文的 receipt 设计、六类拒绝状态、许可门禁是 #388 契约的具体落地 |
| #387 | `find` 新增的 `external[]` 属于 Knowledge 公开接口的一部分，需在 #387 的 schema 中登记 |
| `AGENTS.md` | 外部命中不参与 `PASS`；引用须带 revision 与 `locally_verified=false` |
