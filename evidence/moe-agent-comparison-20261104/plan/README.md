# 历史条件协议与原件身份

这是历史提示协议的脱敏提取，不是逐字复制私有会话提示。
原四组在搜索前冻结计划，后追加 Astra ON/OFF，沿用任务、门槛、测量、源包和
访问约束。两份原件分别由 `provenance.json` 中的 SHA256 标识；
`publication.json` 是另有身份的公开字段提取，不冒充原件。

每组新建 projectless 会话，不 fork、不 resume、不复制父会话优化上下文。
实际模型及 xhigh 从会话 turn context 核验；每条件仅运行一个 Agent，不调
子 Agent、不换模型。按 6.1 ON、6.1 OFF、5.6 ON、5.6 OFF、Astra ON、Astra OFF
串行执行；前一组 8 轮、独立 final、资源清理全部结束后才开始下一组。

共同指令协议：读取冻结任务及必要执行接口，交付 `compute` 实现；每轮提交
不可变源码并调用共同评测器，根据正确性、逐 case 延迟和证据选择下一轮。
不正确、抛异常或更慢的候选仍消耗一轮；不得因收集失败重跑已完成设备实验。
恰好消耗 8 轮后，从本组已测有效候选或 baseline 中预选最终实现，再独立测
一次 4 对 AB/BA final。final 不参与事后重选、不回填探索最优值。
**8 轮是本次历史协议，不是 InferRSI 的全局默认值。**

ON 允许查询冻结 InferRSI revision 中的 skill_library、knowledge_packs、
repo_packs，通过 collect/resource 获取材料，记录返回 identity/revision、
实际可见正文和采纳理由。OFF 不读取这些优化知识库正文。两边均可读冻结任务、
执行器必要接口、共同 NPU 执行规则和公开技术文档；不得读其他会话/候选/结果、
协调分析、私有预实验、全局优化技能/插件或外部记忆记录。实际访问记录另行审计；
这是指令和访问审计约束，不是硬文件系统隔离，也不能证明模型没有训练先验。

原四组及追加组实际使用相同冻结 `source_revision`、task/grader 与 79 个源文件
hash。这些 campaign pins 只存在本证据及验收 issue 中，不进入通用默认值。
历史执行入口是 `inferrsi.harness.scenarios.external.execute_trial`；
host-specific 启动配置和其余执行源字节未随此 bundle 公布，清单身份保留。

计时：完整 forward、host 调度和全部通信在区间内，返回后设备同步；每次
两个 rank 取最大值。探索各 case 每实现 16 样本，final 32 样本，交替 AB/BA；
每个样本换输入，并使用数值不同但专家矩阵形状相同的预热输入。
case 分数为 baseline 中位延迟 / candidate 中位延迟，总分是三 case 几何平均。
错误样本不构造虚假速度，失败 round 保留之前 best。

冻结容差为逐元素 atol/rtol 0.03、NRMSE 0.01；检查双 rank、只读输入/参数、
有限性、独立 CPU FP32 oracle，以及 top-k=1/2、不等 token、空专家、零输入
rank、原位参数变化。参数更新用例不穷举所有缓存失效分支；最终六实现均没有
权重布局缓存。完整准确门槛与输入生成方式见 `../validator/task/`。
