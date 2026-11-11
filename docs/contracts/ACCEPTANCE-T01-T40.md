# T01–T40唯一结果（设计预期，不是已执行测试）

状态 **Proposed**。T01–T35 保留原基线内容（措辞与唯一结果不变），T36–T40 为 D023 新增。全部条目是**规格说明**：除第 5 节明确标注的既有文档构造证据外，**没有任何一条已被当作运行时测试执行通过**。schema 通过不等于本表通过。

D003非终态政策已由作者选择，C3已按D018/D020精确门禁路线选择。P1只作fixture协议：F格式独立错误可FAIL；C正确性可信错误可FAIL；M必须完整测量/清理证据。未提供其他有效证据即无隐含替代；跨scope不覆盖。

## 1. 基线唯一结果 T01–T27

| ID | 固定输入/操作 | 本候选要求的结果 | 责任与反例 |
| --- | --- | --- | --- |
| T01 | RecordRef 请求 att-1/v3，载荷却 v4 或原字节摘要不符 | 拒绝交接，无本次 EvaluationResult/AssessmentRef | Apps 先核对；B 对漏过的顶层错配仍拒绝，不归类为证据不足。 |
| T02 | att-1 顶层正确，P1 必需单项 grader-output 来自 att-2 或单项字节损坏，且没有其他 C 有效证据或独立错误证明 | 该项无效，C=INCONCLUSIVE；F/M 按未给证据保留 INCONCLUSIVE；固定 att-1 仍是正确组合 | Reader 不读越界路径；Apps 保留失败原因，B 判证据，不升级为拿错整份记录。 |
| T03 | P1 正确记录，进程 exit 0 但缺必需 grader-output | C INCONCLUSIVE，不能从进程成功补 PASS | H 仅执行事实；B 决定 C。 |
| T04 | P1 not_started，仅资源不足，已提交固定记录，无 F/C 证据 | 可显式 assess；F/C/M 各 INCONCLUSIVE，非完成测量，执行 not_started 保留 | 自动同步流程停止不调用下一跳；独立显式 assess 不启动进程。 |
| T05 | P1 not_started，但固定记录已有可信的候选格式错误证明 | F FAIL，C/M INCONCLUSIVE；不伪造测量启动 | 不以 phase=finished/非终态一刀切抹掉 F。 |
| T06 | P1 recovery_required，C 的可信独立错误证明已提交，cleanup unknown | C FAIL 保留，M INCONCLUSIVE，cleanup unknown 单列 | 不自动恢复重跑；F 未给证据仍 INCONCLUSIVE。 |
| T07 | P1 已存在的历史 running 固定修订，无完整测量样本，也无 F/C 证据；只有返回信封当前观测声称已完成 | F/C/M 各 INCONCLUSIVE；不能用临时观测补固定证据 | 新观测若要判定，H 先提交新修订。 |
| T08 | 同 claim 多 scope：S-A 证据充分 FAIL；S-B 缺证据 | (claim,S-A)=FAIL 与 (claim,S-B)=INCONCLUSIVE 分列；无冻结汇总则不出总 verdict | CLI 只能概括请求声明的主范围，不覆盖另外结果。 |
| T09 | 同 claim/scope 的必需证据互相矛盾，P1 未定义特例 | 该 claim INCONCLUSIVE/conflict | 不最后一条覆盖，也不由 Apps 选更好结果。 |
| T10 | 固定 scope 编码不同但人认为语义包含 | 绑定/顶层检查拒绝；只有 B 公开协议提供确定映射后才按其映射重建合法请求 | Apps 不推导包含/等价，也不静默更换冻结范围。 |
| T11 | v4 已补清理，显式重判 v3 | 仍只用 v3 与其中 prepared；P1 M 若 v3 缺清理仍 INCONCLUSIVE | v4 不自动补入 v3，旧引用不证明当前状态。 |
| T12 | 启动前记录无法持久化 / 启动后提交失败 | 前者 ExecutionPersistenceError(started=false) 且不启动、无 RecordRef；后者 ExecutionPersistenceError(started=true, partial_record, retained_refs)，无有效新 Ref，保留已知身份/局部事实及仍有效旧引用 | 局部事实不能替代 committed payload，未知结果不重跑；沿原已接受但单人评审的 B 约束继续核对恢复细节，不新增恢复 API。 |
| T13 | B 已给结果而 assessment 归档失败 | 无有效新 AssessmentRef；内存结果与保存失败分列，原 RecordRef 可显式重判 | 不当作交接拒绝，也不伪造归档成功；不推进依赖持久结果的候选。 |
| T14 | 交接身份错误但需诊断 | 无本次 EvaluationResult/AssessmentRef；允许保存非判定诊断 | 日志不是 assessment 或捕获任务证据，历史有效 assessment 不删除。 |
| T15 | prepared 的协议/recipe/必需资源未能完整冻结归档 | 无有效 PreparedRef，不 execute | B 列语义必需闭包，Apps 校验归档，不用内存 id 顶替。 |
| T16 | prepared 归档成功，但执行目标缺受支持 worker/能力/固定资源 | H 明确准入拒绝并按可持久化条件留 not_started；不回退未授权执行 | B 固定 recipe，H 目标端解析，Apps 无第二套调度。 |
| T17 | 离线 assessor 不支持冻结 grader/rule 版本 | 明确不支持/拒绝，无本次正常 assessment | 不下载/执行归档任意代码，不用当前阈值代替。 |
| T18 | 新旧 id/ref 文档示例更正 | Bundle id 为纯 id，读取 ref 带 authority；历史 Bundle hash 不改 | 无证据不迁移历史数据，不声称历史绝无非法 id。 |
| T19 | PR-00b精确门禁policy未正式接受，却准备七K物理迁移 | 不执行越界搬家/造壳；先提交正常review的精确policy设计，不用动态import逃扫描 | 路线已选，流程未接受不冒称已获许可。 |
| T20 | 七K精确policy已正式接受并实施，K01七K主体/cat拆分/补丁测试联动迁入、旧根纯静态导出，尚有已登记H残余 | 旧K公共行为/类型对象/hash/pin不变；新K不反向import根壳；overall isolation_complete=false | 不授予H直接→K或evaluation→Apps的例外。 |
| T21 | 固定任务/规则/输入资产/候选契约不变，仅更换 expected_candidate 的具体 id/digest（均符合契约）并重新 prepare | protocol_digest 相同；prepared_id 不同；各准备信封分别保存自身预期身份并在执行时核对，不因候选不同而改变比较规则 | 本版prepared.json/prepared-candidate-2.json给出具体双候选golden及同protocol/different prepared断言；不重算历史产物。 |
| T22 | 同一已登记 request_id/request_digest 再次 execute，既有 owner lock 有效且仍在执行 | 在任何本次新候选绑定/启动前返回 AttemptInProgress(attempt_id, latest_record_ref若有)，不等待、不替换控制者、不新增执行 | 原v0.3唯一返回规则；第四次有效全文复核确认本条唯一，正文返回规则在本版补全。 |
| T23 | 本次执行已结束，清理未确认但已知记录/证据能够完整提交 | 返回对应固定 RecordRef 与 phase=recovery_required、cleanup=unknown 的实际事实；不伪装 finished/PASS，不自动重跑 | 本次可提交的待恢复记录不同于T22重入短路；后续对同请求的重新提交仍按既有RecoveryRequired规则处理。 |
| T24 | 首次合法请求已登记，预算/资源/能力/身份准入拒绝，且not_started记录提交成功 | 必须返回固定 RecordRef 与not_started/拒绝原因；不启动候选、不自动判定，不允许选择性丢弃本来可提交的拒绝记录 | 真正提交失败则走无有效新Ref分支，与本输入条件分开；不是给非法未登记请求造记录。 |
| T25 | 首次合法评测请求已登记，预算/能力通过，实际候选字节与预期digest不符；提交成功且无F/C独立错误证明 | 绑定后启动前必须not_started固定记录，保存actual/expected核对失败；不启动；显式assess正确固定组合时P1 F/C/M均INCONCLUSIVE | 实际候选异常不同于T01拿错顶层记录，不凭hash错配证明数学错误。 |
| T26 | 已登记相同request_id，提交不同ExecutionSpec（如仅output_root改变） | RequestConflict，保留原请求，不启动、不覆盖原记录 | request_digest覆盖完整spec，换位置不绕claim。 |
| T27 | 相同key/digest重入，旧记录finished/exited且已固定提交 | 返回原record_ref及payload，不新增执行/记录修订；可对原固定材料离线重判，不覆盖旧assessment | 同步重放not_started仍停止自动推进；非终态owner未知走RecoveryRequired不是本例。 |

## 2. 源码整合验收 T28–T35

| ID | 场景 | 唯一预期结果 | 范围/证据 |
|---|---|---|---|
| T28 | prepared冻结候选sha=A，而spec候选role写B；或id/format声明不同；或expected-sha256@1缺expected | 登记前InvalidExecutionSpec、不启动/不造record；若声明都A而实际B则T25绑定后not_started | V28；与实际身份错配分开 |
| T29 | 合法准入拒绝、未取得资源、前置时长未观测 | finished/not_started/started=false/cleanup=not_needed；record elapsed=null、usage amount=null/unknown，不填0 | V20/D021；v2 golden |
| T30 | 进程已有外部副作用后、commit前崩溃；重开OS锁空闲且无committed record | RecoveryRequired、latest_ref=null、不绑定/不重启；read latest=NoCommittedRecord，不能临时造快照 | D021/H01-4 |
| T31 | PublicError.code=invalid_spec之类未列别名 | schema拒绝；合法具体场景按D021有限code精确拼写，不由Apps猜测映射 | 106定义；PublicErrorCode |
| T32 | 同一assess配置有stores/demo和stores前缀同时命中，或Ref无匹配mount | 配置重叠先InvalidRequest/不读；合法配置但Ref无匹配则UnsafeArtifactPath；禁止尝试第二根/联网 | D021路由前置 |
| T33 | 同metric/scope或eligibility/scope、comparison/scope/against出现冲突证据 | B产一个唯一invalid/null、ineligible或incomparable并附conflict；若结果自身重复key则验证拒绝，不默选首末 | V21，claim冲突仍独立INCONCLUSIVE |
| T34 | K01只搬主体造壳，不迁D1–D5补丁目标或提前导入skill_catalog | PR验收失败；补丁必须同PR联动，私有_json显式导出；yaml缺失路径两个skill_catalog模块名均未加载 | Phase3 D1–D8/D020；不是已实测 |
| T35 | 同scope含F PASS/C FAIL/M INCONCLUSIVE，assess显式主key=C且归档成功 | exit8/fail，保留三claim原结论；选F为0只指F，未提供主key则InvalidRequest/2，不造总verdict | D022；不改旧run0/1/2 |

## 3. D023 验收 T36–T40（规格，不是已运行测试）

| ID | 场景 | 唯一预期结果 | 范围/证据 |
|---|---|---|---|
| T36 | 空归档根、非 fixture 的授权 prefix；其后缺一个必需资源；再补齐并完整提交；最后换进程读取 | 缺任一必需资源→**无有效 `PreparedRef`**、不 execute；补齐全并提交成功→新进程仅凭固定 Ref 与同一配置读到**相同字节与身份**（prepared 字节/hash/prepared_id 不变） | D023-1/V31；Apps 分配 location 后经 B 纯 encode/validate 核对再归档；B 不存盘、不依赖 Apps 路由；移动 location 不必然保持 prepared_id，内部字段变化须重算 |
| T37 | 入口名与 revision 相同、实际代码摘要与冻结值不同；另设无法解析实际入口的情形 | 摘要不同→候选进程**零启动**，提交 `not_started` 与核对失败事实；提交失败走既有 `ExecutionPersistenceError`。无法解析实际入口→记 `not_performed`/unknown，**不伪造 mismatch** | D023-2/V32；评测模式 `CommandStep.expected_code_sha256` 必须等于 prepared.recipe.code_sha256，普通命令模式为 null；H 启动前计算，不 import B；同步 schema/V/`ExecutionSpec`/`request_digest` golden，不重写历史输出 |
| T38 | Apps 生成交付上下文，H 留存失败一次；再成功留存并封存，然后换进程读取 | 留存失败→**不发布有效交付 Ref**；成功→换进程用同一配置读到与草稿**完全相同的实际交付字节**，不得只有引用却报 `ArtifactUnavailable` | D023-3/V33；`ContextProvider.collect` 不得返回未提交的有效 `ArtifactRef`；`DeliveredContextDraft` 是进程内值，不是 JSON 流 DTO；写入者始终是 H，Apps 不写 H RunStore |
| T39 | 在 T35 之上增加两行：(a) 请求键不在冻结协议 / 无合法主键；(b) 键在协议但 B 结果遗漏该键 | (a) `InvalidRequest`/exit 2，**不调用 assessor、不写 assessment**；(b) `AssessorError` 类结果契约错误，Apps 不补判、不误报为用户参数错误；两行各自唯一 | D023-4/V34；先核对 claim key 再调用 assessor；归档失败优先 exit 6 且 `assessment_ref` 必须 null；合法完整结果按所选 claim 返回 0/8/9，其他 claim/scope 原样保留 |
| T40 | 同一 RunStore、同一已保存 `AppsExecuteRequest`；首次提交后响应丢失，随后重放同一请求 | 重放**重用原 attempt/原请求**：已完成→返还原 `RecordRef`；状态未知→`RecoveryRequired`；**不新分配 attempt、不延长期限/预算** | D023-5/V35；`AppsExecuteRequest.attempt` 必填，execute 不自行 allocate；`StorageConfig` 由宿主/`--storage-config` 注入且不在 `Apps*Request`；禁止把不同请求或超期重跑说成同一次重放 |

## 4. 未纳入 T36–T40 的反向断言

以下不得由 T36–T40 推导为规范：

- 任意内部 location 变更都保持 `prepared_id`；
- 代码摘要只能通过一种 DTO 字段实现、禁止等价投影；
- 把首批 `prohibited_first_wave` 写成永久禁止，或未经单独 review 写成永久允许壳→Apps；
- 把断连重放解释成不得复用原 attempt；
- 把 `collect_candidate` 的定位/字节提取升级为已证实的 Apps 判分越界。

## 5. 验证状态说明

- 基线 P1 的 canonical 正例/负例与 schema 自身校验，属于**文档构造证据**（见 SCHEMA-AND-SEMANTICS 第 5 节），不是仓库 execute/assess 或跨语言互操作实测。
- T01–T40 全部为**规格说明**，等待实现 P0a 之后的运行验证。
- `fixtures/d023-conformance-cases.json` 是 T36–T40 的文档向量；其 64hex 摘要是语法有效的固定示例值，不是计算所得，coordinator 后续另行 hash 校验。
