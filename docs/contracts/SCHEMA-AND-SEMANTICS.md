# D017 — 新信封v1完整规格、规范编码和语义校验（含 D023 勘误对齐）

效力：用户t103/t108委派下的作者设计决定；待Fable复核此精确版本及仓库正式review。状态 **Proposed**。JSON Schema是本地设计产物，不是已合入的运行代码。机器字段全集以`schemas/contract-v1.schema.json`为准：Draft 2020-12，106个命名定义；所有新固定对象字段全部required，未知字段拒绝；可空用null表达，不靠缺字段制造第二种解释。`Parameters`是有意的任务/配置扩展槽，不是偷偷允许对象任意字段。

D023 勘误（见 `D023.md`）对本文件的改动是有界的：`CommandStep` 增加 required 可空 `expected_code_sha256`；prepare 闭包在进程内交付；`DeliveredContext` 语义收紧为已提交记录且草稿是进程内值；assess 主 claim 校验顺序固定；CLI attempt 保存与断连重放固定。V01–V30 全部保留，新增 V31–V35 承接 D023，不重写历史归档输出。

## 1. 生效范围及旧格式不变

- 新PreparedEvaluation、ExecutionSpec、持久ExecutionRecordPayload、EvidenceInput、EvaluationResult使用整数`schema_version:1`。v0.3的`schema_version:str`是未实施草图，本次明确选整数；没有声称生产旧v1数据已经是整数或转换历史数据。
- PreparedRef/AssessmentRef同样version=1；RecordRef版本是record_version（1起），payload自身另有schema_version。三种Ref互不替代。
- 旧Knowledge逻辑记录、Bundle manifest/revision、旧RunSpec/evaluate/native Python返回值/旧CLI仍走现有协议和编码；不强行把旧浮点/任意键记录塞入新canonical编码。Knowledge DTO里`logical_record`/`bundle`明确是`LegacyJSON`原样透传，其校验由现有K Bundle/Reader/Store承担，**不属于inferrsi-json-v1摘要域**。不能用这个透传槽携带新Execution/Prepared/Result未知字段。DeliveredContext只归档真正交付字节的ArtifactRef，不把旧逻辑记录JSON重新编码来重算Bundle hash。
- 新首期TargetRequest.executor_kind只支持local_cpu；未知executor/schema/task/rule明确UnsupportedOperation/UnsupportedSchema/UnsupportedRuleVersion，不猜测相近能力。遥测/真实Agent/远端/视频新政策不是K01/H01的前置。

## 2. 公开端口与owner（类型实现各模块自有，schema共词汇不共享Python业务类）

| owner | 端口 | 输入/输出定义 | 禁止副作用/不变量 |
|---|---|---|---|
| K | read(reference,revision=None) | KnowledgeReadRequest→KnowledgeReadResult | 返回实际pin，旧逻辑记录不改；read不写store/执行 |
| K | collect(query/ids/pins/filters/selection) | KnowledgeCollectRequest→KnowledgeCollection | 无命中/遗漏/冲突可解释，动态选择不冒称永久重放 |
| K | resource(reference,path,revision) | KnowledgeResourceRequest→KnowledgeResourceResult及只读字节 | revision必填，不能再次resolve current；路径授权/hash校验 |
| K | create/update/history | 对应Knowledge*Request→现有固定revision/历史结果 | update CAS冲突不当成功；不新增写请求去重日志 |
| B | prepare(PrepareRequest) | PreparedEvaluation，**且在对象之外进程内交付：该次冻结协议的规范字节 + 按role读取资源闭包的只读入口（字节或流）** | 无执行/预算准入/隐式存档，冻结合法规则与闭包；不依赖Apps存储路由，不自行存盘 |
| B | encode/decode/validate_prepared | PreparedEvaluation↔规范字节（可接受已分配的最终location） | 纯计算，未知版本不猜；encode不自行存盘 |
| B | assess(prepared,evidence,*,artifacts) | EvidenceInput→EvaluationResult | 仅读留存字节，不启动worker/候选、不联网/设备/补测 |
| B | claim_keys(protocol)/validate_request_key | 冻结协议→只读claim key集合／明确的无业务投影判定请求键是否合法 | 只读核对，不做业务判定、不写assessment；供Apps在调用assessor前使用（V34） |
| B | encode/decode/validate_assessment | EvaluationResult↔规范字节 | 只有B决定claim/metric/eligibility/comparison |
| H | allocate_attempt(run_id,owner,target_request,deadline,resources,budget,retry*) | AttemptContext | 分配身份，不占预算/资源、不启动；request_id=attempt_id |
| H | execute(spec,*,cancellation=None) | ExecutionSpec→平铺ExecutionRecord或PublicError类稳定错误 | 原子登记、H准入/绑定/运行/记录；启动前核对实际入口代码摘要（V32）；不是B评分 |
| H | read(attempt_id,record_version=None) | 平铺ExecutionRecord | latest只查最新已提交；指定版本固定；无已提交记录→NoCommittedRecord，不编造快照；不接管/重启 |
| H内注入端口 | CandidateProvider.plan_generation/collect_candidate | CandidateContext+AttemptContext→GenerationPlan；Record→CandidateProposal | 两端不做外部执行；H中间execute |
| H内注入端口 | EvaluationPort.execution_for/assess | PreparedRef+CandidateProposal+AttemptContext+scope→ExecutionSpec；Record→AssessmentSummary | Apps实现适配；身份/期限/预算不重建，结果保存后才给AssessmentRef |
| H内注入端口 | ContextProvider.collect | ContextRequest→**DeliveredContextDraft（进程内值，非JSON DTO）** | K选择/Apps适配；草稿不得带未提交的有效ArtifactRef；H用自有捕获/提交封存DeliveredContext（V33） |
| Apps | archive_prepared/archive_assessment/bind_execution/to_evidence/to_summary | 固定字节→对应Ref；字段显式转换 | 归档成功才发布Ref；不写H RunStore、不造预算/判定/scope语义 |
| 各模块自有reader端口 | ArtifactReader.open(ArtifactRef) | 只读字节流 | 授权根、大小/hash、安全路径；不回退网络/current/重新execute |

D023-1 的进程内闭包交付不是新 DTO，也不扩 `PreparedEvaluation` 字段：最终 location 只落在既有 `ArtifactRef.location`。D023-3 的 `DeliveredContextDraft` 同样是进程内值类型（items/selection/omissions/limitations、字节或流、拟用逻辑位置与摘要），故意不进 `$defs`，也不编造可序列化流形状。

JSON Schema的引用复用是文档结构，不授权K/H/B互import DTO实现或共同业务包。

## 3. canonical编码/身份的精确规则

沿用D002，并明确：ASCII键字典序；UTF-8无BOM/末尾换行/空格；数组不随意排序；中文不转义、不Unicode normalize。拒绝重复键、孤立surrogate、浮点token/NaN/Infinity；整数范围[-9007199254740991,9007199254740991]，计数非负。JSON Schema数学上的integer可能接受1.0，因此**严格字节解析器必须先拒绝任何浮点token**，不能仅靠jsonschema判断。非整数值是Decimal定义规范十进制字符串，负零/指数/多余零拒绝，不读入后悄悄修复固定字节。

字符串规范转义不依赖语言库默认值：双引号唯一写`\"`、反斜杠唯一写`\\`；U+0008/U+0009/U+000A/U+000C/U+000D分别唯一写`\b/\t/\n/\f/\r`，其余U+0000–U+001F唯一写小写四位`\u00xx`。其他合法Unicode标量一律原始UTF-8（包括solidus `/`、U+007F、U+2028/U+2029、非BMP字符），不写`\/`或额外`\u`转义；无效UTF-8/孤立surrogate拒绝，不补U+FFFD。键和值用同一转义规则；键仍仅ASCII且按未转义字符串ASCII码序排序。字节解析先检重复键/合法Unicode/禁浮点token，再与本规范重编码逐字节比较；别名转义可作一般JSON请求输入，但不可冒充已固定canonical payload。编码不依赖locale，true/false/null小写、整数十进制无前导零，固定字节里的-0不canonical。

sha256字段=64小写hex；语义id=`sha256:<64hex>`。ArtifactRef四字段location/sha256/size_bytes/media_type；location相对授权存储命名空间，拒绝绝对/驱动器/反斜杠/NUL或控制字符/./../重复规范路径/未支持链接。cwd可为`.`，其他path不可。SourceSpec中的controller/target原始来源路径可以是授权配置下的来源，不将上述ArtifactRef路径限制错误套到已有输入来源；不得从source解析任意网络位置。

定义投影P：按本机器schema的命名定义/字段路径递归遍历；只有被该字段schema明确声明为ArtifactRef时才删除location，保留sha256/size_bytes/media_type。Parameters/JsonValue里的任意对象即使恰好同四字段也必须原样全量保留，不能凭形状猜Ref；其他对象原字段全部保留。角色在父Resource内仍保留。除下表明确排除项外，字段不能另行忽略；JsonValue任务参数全量进入其所属语义域。

| 身份 | 精确输入/排除 | 哈希 |
|---|---|---|
| protocol_digest | P(ProtocolV1删display_notes) | sha256(canonical字节)，加`sha256:`前缀 |
| prepared_id | P(PreparedEvaluation删prepared_id/created_at/display_notes) | 同上；protocol_digest已先算好；protocol字节摘要仍保留 |
| request_digest | 完整ExecutionSpec，不含任何外层receipt（spec本身没有request_digest字段） | canonical全量字节hash加前缀，含真实location以固定本次请求来源；**含每个CommandStep.expected_code_sha256（D023-2）** |
| RecordRef.artifact.sha256 | 完整ExecutionRecordPayload字节 | 原始规范字节hash，无前缀；record_version/recorded_at参加 |
| assessment_id | P(EvaluationResult删assessment_id/assessed_at) | 语义hash；claims/metrics/eligibility/comparison/理由与固定依据均参加 |
| PreparedRef/AssessmentRef.artifact.sha256 | 完整各自payload，含它自己的语义id | 完整规范字节hash；不含外层Ref |
| 原始证据/目录文件 | 原始实际字节 | 不canonical重写；目录manifest自身按新v1规范 |

ProtocolV1.worker_recipe含测量语义版本/代码身份/参数模板，作为冻结规则进入protocol_digest；PreparedEvaluation.recipe是其精确复制，不成为独立可变规则来源。recipe里不得固化具体候选id/hash/本次attempt/绝对安装路径；以固定role占位符绑定输入输出。具体CandidateExpectation对象只在prepared而不在protocol；ExecutionSpec.InputSpec保留本次绑定预期并受V28约束，不是可替代冻结预期的独立权威。所以T21同协议不同候选的protocol_digest相同、prepared_id不同。

**D023-1 投影边界**：P只剥外层已声明`ArtifactRef`的`location`。完整提交后新进程仅凭固定Ref与同一配置可读；已提交字节不可改写。但**不得**据此宣称任意搬迁都不改变`prepared_id`：若协议对象或资源描述自身的规范字节因**内部字段**变化而改变，相应sha与`prepared_id`按原规则重算。

集合规范：Resource按role唯一排序；输入集合按role唯一排序；DirectoryManifest.entries按path唯一排序。steps/samples/args、claims、metrics和有语义顺序的结果数组按协议定义顺序保存，不通用排序。claim_definitions顺序就是结果claims顺序（每个key唯一）；required_evidence的(check_id,checker_revision,subject,phase)唯一，按协议声明顺序冻结，协议与准备副本完全一致。fixture的P1要求顺序是明确冻结的顺序，不在读取时自动排序已有固定字节。

## 4. 必须与机器schema一起实现的跨字段语义校验（不是留待PR选择）

| ID | 必须校验/唯一失败结果 |
|---|---|
| V01 | 全对象通过对应schema；新固定字节必须canonical；未知主版本/字段拒绝，不丢弃后继续 |
| V02 | request_id=attempt_id；retry_of/retry_reason同时null或同时提供；父id/digest同样成对 |
| V03 | inputs role、step_id、每步output role/path唯一；candidate.input_role恰好对应一InputSpec；本次candidate来源/绑定预期以该InputSpec承载，且必须满足V28的prepared约束，不在CandidateSubmission重复维护 |
| V04 | source_namespace=artifact时source_ref非null、source=source_ref.location、expected_sha256=source_ref.sha256；其他namespace的source_ref=null，来源受H目标/控制端授权根配置约束 |
| V05 | 评测模式prepared_ref/protocol_digest/operation/validation_scope/candidate必须同时非null；普通命令模式这五项均null（且此时每步`expected_code_sha256`=null）；generation_record_ref与输入来源完整留存，不以null绕开已声明评测 |
| V06 | 从ArtifactReader验原prepared字节/hash/size，核对PreparedRef.id/version；protocol原字节/hash/size和独立语义digest均正确；不把protocol.sha256当protocol_digest |
| V07 | prepared task/grader/operation/scope/candidate_contract/required_evidence/recipe逐项等于固定ProtocolV1对应字段；prepared.protocol和prepared.resources共同固定完整闭包；resources按role身份列齐protocol.resources及非null baseline/reference/quality_reference，不把protocol文件自身Ref写入它自己；受支持外部worker代码按固定安装版本/代码身份核对，不要求整个解释器归档；task registry支持对应冻结版本 |
| V08 | 每个claim.required_checks都在required_evidence中有匹配要求；for_claims只引用已定义claim；每项claim有已注册decision_rule，任务参数通过其固定任务版本schema；没有合法判据prepare即拒绝 |
| V09 | required_evidence冻结producer种类/控制域和check_id/checker_revision/subject/phase/attempt/operation/scope/artifact schema匹配规则。worker自报producer.kind不升级可信度；实际capture_route/控制域由留存路径和采集适配器核验 |
| V10 | recipe.args仅允许字面量和整个token形式`{input:role}`/`{output:role}`；role必须已声明，不能字符串内插/执行表达式。Apps确定性替换为InputSpec.materialized_path/OutputSpec.path；不变更字面常量、采样、顺序或重试；golden Spec已用实际相对路径 |
| V11 | deadline不延长attempt/campaign期限；step timeout为正Decimal且不能延长期限；currency金额按币种/单位、tokens按整数字符串，不跨维度加总；CPU/memory请求若给定必须>0 |
| V12 | 免费CPU policy_ref=null仅在H确认无付费/任务不要求政策时可准入；其他缺政策拒绝。BudgetAdmission由H产生，不采信请求者自报已预留/已扣款 |
| V13 | 实际字节绑定/核对在候选启动前；执行留存快照或已验证物化副本，不能捕获后继续从原可变source运行。未做的检查not_performed，identity_status也not_performed，未知实际sha/ref/path为null |
| V14 | 同请求重入按状态/owner规则在任何新绑定/启动前短路；输入身份拒绝只能在实际绑定后、启动前成立，必须提交not_started（真正提交失败例外） |
| V15 | RecordRef.attempt/version与payload相同、原字节hash/size正确；payload没有record_ref/observed_at/controller_observation。API平铺返回只把这三项加在外层，to_evidence必须剥离它们而非将外层observed状态混进payload |
| V16 | EvidenceInput.record是对应v1固定payload的字段完整复制，不是可丢字段摘要；B可canonical编码这个内层payload核对RecordRef摘要，**不能把整份EvidenceInput字节声称等于RecordRef摘要**。record_digest=RecordRef.artifact.sha256；task来源是固定prepared，不是假称H捕获task |
| V17 | 顶层prepared/record/attempt/operation/scope错配拒绝且无本次EvaluationResult/AssessmentRef；单项产物外来/坏hash/缺失不当作拿错整份记录。ArtifactReader安全越界拒绝打开，记录该项不可用原因，由B解释正确组合内证据缺口 |
| V18 | phase/process_outcome/cleanup/started/side_effect_unknown独立：finished要求生命周期已收束且无未知外部进程/租约；finished可以not_started/非零退出；running/未知结局不能伪造exited；step可能unknown，外部未知不填not_started |
| V19 | cleanup=confirmed须process_exit_confirmed=true且所有已取得租约release_confirmed=true；not_needed只限从未取得需清理资源；release_confirmed=true须有确认时刻/证据，false/null不当成功 |
| V20 | not_started不能有实际进程exit_code；started=false的普通准入拒绝步骤not_started，elapsed未知就null（有可观测前置用量可保留）。记录elapsed_seconds为成功登记claim至本payload封存测量点的以monotonic时钟测得的已观测时长，不含其后的编码/落盘/commit；每步elapsed为进程启动到确认结束，未启动为null；前置时间未观测的not_started记录elapsed为null。usage unknown不填零；无租约用applicability=not_applicable，未知租约明确unknown |
| V21 | claims按(claim_id,validation_scope)、metrics按(name,validation_scope)、eligibility按validation_scope、comparison按(validation_scope,against.assessment_id)唯一且来自固定协议；对同一key的冲突证据须B聚合成一个结果（claim默认INCONCLUSIVE、metric invalid/null、eligibility ineligible、comparison incomparable，附conflict原因），不得输出重复键由Apps择首/择末；缺证据无特例→INCONCLUSIVE；冲突无特例同样；允许的独立错误证明可FAIL，不以其他scope或cleanup未知覆盖。无冻结汇总则无总verdict字段 |
| V22 | Metric.validity=valid时value非null且证据/聚合条件满足；invalid/unavailable时value=null，说明reason；assessor与grader版本分列，不支持冻结规则拒绝，不偷偷重测/换门槛 |
| V23 | result固定prepared/record/protocol/candidate/attempt与依据相同；assessment_id按表重算；AssessmentSummary.assessment_ref仅归档成功后存在，不从未保存内存结果造Ref |
| V24 | GenerationManifest先保存，seal_generation将role=generation_plan的固定InputSpec加进最终spec后再算request_digest；manifest不含自身Ref/完整spec/本次未产生record，角色冲突拒绝；collect_candidate只读本次留存manifest和产物，不读可变source |
| V25 | provider generation/evaluation/retry各自attempt，budget scope/总deadline不重置；候选父依赖/允许反馈由H冻结策略控制，B给比较资格，Apps不添加搜索/多分支产品能力 |
| V26 | LegacyJSON字段不通过新canonical重编码来重算旧revision；K读/写遵守现有authority/source/CAS/hash规则。package importlib、checkout Path、插件物理根分别解析，不把三者等同 |
| V27 | 实际启动step必须绑定实际runtime/entrypoint/code身份/argv与控制域；未启动可null，崩溃导致未知如实null并记录未知原因，不把声明路径当实际捕获；所有时间必须合法Gregorian/RFC3339 UTC值，不能只通过正则就采信无效日期 |
| V28 | 评测模式下：prepared.expected_candidate非null时，candidate.candidate_id=expected_candidate.candidate_id、其input_role的InputSpec.expected_sha256=expected_candidate.sha256，且expected_candidate.format_schema=prepared.candidate_contract.format_schema（CandidateSubmission并无format_schema字段）；任一声明冲突在登记前InvalidExecutionSpec。prepared期望为null时不修改原prepared；按冻结identity_rule支持capture-only（captured-sha256@1）或强制expected（expected-sha256@1）；前者可无caller预期但H必须捕获/hash/只运行固定快照，后者缺expected的组合静态可判定，登记前InvalidExecutionSpec，不启动/不造record。artifact来源仍须V04。无法支持的identity_rule拒绝，不自行降级。实际字节与一致声明的expected不同是绑定后事实，必须留not_started或真实提交失败，不退回伪装成预登记非法请求。 |
| V29 | Reader路由/命名空间和错误唯一编码按D021；新固定记录/Ref、结果内error code均须保持大小写及稳定映射，不接受别名。 |
| V30 | 新Apps请求/结果按D022；reason_code若无PublicError为null，有则等于error.code；多个相同scope的claim不由Apps汇总，CLI显式选择(primary_scope,primary_claim_id)。 |

### D023 新增校验（V31–V35）

| ID | 必须校验/唯一失败结果 |
|---|---|
| V31 | **prepare 进程内闭包（D023-1）**：B 的 `prepare` 返回必须在 `PreparedEvaluation` 之外同时提供（a）该次冻结协议的规范字节，与 `prepared.protocol` 的 sha/size 一致；（b）按 role 读取资源闭包的只读入口（字节或流），覆盖 `prepared.resources` 全部 role。已有且可校验的既有资源可复用既有 reader；**新生成协议不得只给尚未可解析的 `ArtifactRef`**。Apps 在可信显式 `StorageConfig` 下分配最终 location，再经 B 纯 `encode/validate_prepared`（可接受已分配 location）核对最终 prepared 规范字节后归档；Apps 不重写 B 规则，B 不依赖 Apps 存储路由也不自行存盘。缺任一必需资源、校验或归档失败→无有效 `PreparedRef`。完整提交后新进程仅凭固定 Ref 与同一配置可读。身份只按 P 投影剥 location；内部字段变化须按原规则重算 sha/`prepared_id`。 |
| V32 | **冻结代码摘要（D023-2）**：`OperationRecipe.code_sha256` 是冻结预期，作用域是受支持入口/包，不归档整个解释器。每个 `CommandStep.expected_code_sha256` 字段必须存在。评测模式（`prepared_ref` 非空）下其值**必须等于** prepared.recipe.code_sha256。`OperationRecipe.code_sha256` 已是 required 非空 `Sha256`，不存在「recipe 未声明代码摘要」分支。Apps 从固定 prepared.recipe 原样映射、不得改写或推断；普通命令模式（V05 五项均 null）下必须为 null。规格期违规（普通命令模式出现非 null，或评测模式 expected 为 null / 不等于冻结 `recipe.code_sha256`）在登记前按 `InvalidExecutionSpec` 拒绝，不启动、不造 record，也不得当作 T37。缺 required key 则先由 schema 层拒绝，不得把 schema validator 失败等同 `InvalidExecutionSpec` 或其他运行时 PublicError。T37 只适用于评测模式且 expected 已等于冻结 recipe 之后、启动前核对实际入口字节：实际摘要不同则零启动并提交 `not_started`（提交失败走既有 `ExecutionPersistenceError`）；无法解析实际入口则记 `not_performed`/unknown，不伪造 mismatch。普通命令 null 模式不覆盖 T37。H 在候选进程启动前计算实际入口字节摘要并核对，不 import B。`expected_code_sha256` 参与 `ExecutionSpec` canonical 字节与 `request_digest`；本字段的引入须同步 schema、V 校验与 `ExecutionSpec`/`request_digest` golden，**不重写历史归档输出**。等价投影（如 H 有版本的只读绑定投影从固定 prepared 读取同一预期）须在同一契约修订中写明等价性，且不得只记录实际观测、不核预期。 |
| V33 | **交付上下文（D023-3）**：`ContextProvider.collect` 返回的 `DeliveredContextDraft` 是进程内值，**不得携带尚未提交的有效 `ArtifactRef`**；其字节/流、拟用逻辑位置与摘要只是草稿事实。H 用自有捕获/提交完成留存后封存最终 `DeliveredContext`（其 `artifact` 指向已留存字节），再写入 generation manifest；写入者始终是 H，Apps 不直接写 H RunStore。留存失败时不得发布有效交付 Ref；成功提交后换进程用同一配置能读到与草稿完全相同的实际交付字节，不得只留引用后报 `ArtifactUnavailable`。`DeliveredContextDraft` 不是 JSON DTO，不得为其编造可序列化流形状或伪造一次 JSON 流。 |
| V34 | **主 claim 校验顺序（D023-4）**：`AppsResultV1` 必含 `primary_claim_id`、`primary_scope`、`exit_code`、`error`，并保持内外层 Ref/`admission` 一致；assess 必传精确 `(primary_claim_id, primary_scope)`。读到合法固定 protocol 后，**先**用 B 公开的只读 claim-key 能力或明确的无业务投影核对请求键，顺序唯一：(a) 键不在冻结协议或未提供合法主键→`InvalidRequest`/exit 2，不调用 assessor、不写 assessment；(b) 键在协议中但 B 结果遗漏该键→`AssessorError` 类结果契约错误，Apps 不补判、不误报为用户参数错误；(c) 合法完整结果时归档失败优先（exit 6，可保留内存结果但 `assessment_ref` 必须 null），成功后按所选 claim 返回 0/8/9，其他 claim/scope 原样保留。Apps 不对多 claim 聚合，不自动选第一项。 |
| V35 | **attempt 保存与断连重放（D023-5）**：`AppsExecuteRequest.attempt` 必填，为预分配 `AttemptContext`；`execute` 不再自行 `allocate_attempt`。`StorageConfig` 由可信宿主或显式 `--storage-config` 注入，不进入任何 `Apps*Request`。首期受支持路径：宿主先调用 H `allocate_attempt`，**执行前保存完整 `AppsExecuteRequest`**，再把该文件交给 CLI。断连重放：同一 RunStore、同一已保存请求，首次提交后响应丢失，重发放回原 `RecordRef`（已完成）或 `RecoveryRequired`（状态未知）；不新分配 attempt、不延长期限/预算。**必须重用原 attempt/原请求**；禁止把不同请求或超期重跑说成同一次重放。 |

JSON Schema无法单独保证以上跨引用、授权、信任来源和生命周期不变量；“schema通过”不等于本表通过，合成验收须两者皆满足。

## 5. 固定fixture与当前验证证据

`fixtures/`有Protocol、Prepared（两候选）、ExecutionSpec、Record payload、平铺返回、EvidenceInput、EvaluationResult和三种固定Ref的完整canonical字节；MANIFEST记录每份精确size/hash及语义id。P1 fixture包含中文、Decimal字符串、null、数组顺序、未启动/缺证据三个claim独立INCONCLUSIVE（本fixture它们同属p1范围；跨scope另外由T08核验）。生成器只是文档构造器，**未运行实际worker、生产execute/assess或仓库测试**。

本地使用独立box venv的jsonschema 4.25.1验证schema自身、13份完整正例和7个schema负例及4个合法JSON但非canonical字节负例（schema负例：未知字段/自引用/临时观测/不完整Ref/越界路径/非规范Decimal/非法错误码；字节负例：换行长转义、solidus转义、中文转义、整数负零）。另有V28等跨字段状态向量及构造断言，未声称生产语义校验器已实现。两候选protocol_digest相同、prepared_id不同；仅移动外层已声明 ArtifactRef 的 protocol.location 不改变 prepared_id，内部字段变化须按原规则重算 prepared_id；同形参数反例证明Parameters里的location属于语义，不能被投影抹掉。schemas是$defs库，必须选择具体命名定义；直接验证空库根不算通过。这些是文档构造证据，不是仓库execute/assess或跨语言互操作实测。

D023 增加的 `fixtures/d023-conformance-cases.json` 是**文档向量**：为 T36–T40 各给具体正/负例的显式输入事实与期望结果。同一文件另含 V32-N1–N3（规格期 `InvalidExecutionSpec`，不启动、不造 record）与 SCHEMA-N1（缺 key 的 schema 层拒绝；不得把 schema validator 等同运行时 PublicError）。这些向量不是 T36–T40 验收，也不计入 T37。其中出现的 64hex 摘要是**语法有效的固定示例值**，不是计算所得摘要；coordinator 后续再作 hash 校验。该文件不声称任何运行时测试已通过。

还须实际测试的语义反例：顶层身份错配；单项坏证据；实际候选不匹配not_started；重入/冲突/finished重放；pending cleanup与独立FAIL；预算unknown/单位；registration/commit崩溃点；unsafe symlink；离线禁网络/subprocess；旧Bundle hash/CAS及旧evaluate缺项优先；以及 D023 的 T36–T40。这些验收已定，不再把预期结果留给实施者选择。

## 6. P1 fixture协议的task-owned具体语法/规则（不强加给真实任务）

注册键：task=p1-fixture@1，grader=p1-rules@1，assessor=fixture-assessor@1，operation=evaluate，顶层scope=p1。参数按P1Parameters闭合校验（decimal_fixture和label只用于该编码测试协议的固定内容，不是性能收益门槛）；不借此宣称实现了真实任务库。协议要求的format-proof/grader-proof/samples-proof/cleanup-proof分别对应P1FormatProof/P1GraderProof/P1SamplesProof/P1CleanupProof；未知版本明确拒绝。

- F：匹配本candidate实际捕获sha/attempt/operation/scope、可信format检查及固定schema。可信failed→F FAIL；可信passed且其唯一必需条件满足→PASS；缺失/坏字节/外来/冲突/来源不达要求→INCONCLUSIVE。不能把候选自己填的“passed”当独立检查。
- C：同样使用匹配的可信grader proof；failed→C FAIL，完整可信passed→PASS，否则INCONCLUSIVE。不因M缺样本/cleanup未知覆盖其独立FAIL。
- M：本次确已执行、完整有效samples proof按固定顺序A1/B1/B2/A2（两轮AB、BA），round/role对应，所有值为正Decimal且unit=ms；record完成条件、cleanup和资源释放均已确认，可信cleanup proof与record一致，才M PASS。缺一项/冲突→INCONCLUSIVE。M是测量有效性，不是性能收益PASS；此fixture没有统一收益总分。
- 若同scope存在两份互相矛盾且无协议特例可裁定的proof，该claim INCONCLUSIVE/conflict；不是先看到fail就吞掉冲突。T05/T06只给一份充分可信独立错误证明而没有相反证据；其FAIL并不外推到所有任务。
- P1 schema中candidate_id/actual_sha256是checker输出待校验的声明，只有与固定record BoundInput和实际采集route核对后可用，不自证。record候选实际sha与预期不符但无格式/正确性错误证明的T25不制造数学FAIL。
