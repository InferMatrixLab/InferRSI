# CodePredictor speculative depth：最小移植设计与正确性边界

状态 UNTESTED / INCONCLUSIVE；仅源码研究，未修改engine、未运行GPU。C1 profile中25200次predictor attention对应336帧×15深度×5层，stage1共636721个kernel，支持调查顺序深度的调度粒度，不证明移植能加速。

## 已核实的上游机制

固定 NVIDIA TensorRT-Edge-LLM commit `e649dadcbbf049fa4caf2f09f3a3275ca56751db`。其方案以当前残差hidden配合后续深度已有lm_head提出草稿，不需要新增训练或权重；每轮一次较宽目标验证，逐项拒绝采样，最后补一个纠正或bonus码。当前Qwen checkpoint的15个残差head具备结构条件，但草稿接受率尚未测量。

[官方说明](https://github.com/NVIDIA/TensorRT-Edge-LLM/blob/e649dadcbbf049fa4caf2f09f3a3275ca56751db/docs/source/user_guide/features/codepredictor-speculative-decoding.md)。文档称draft免费，实际仍需head GEMM、概率处理、抽样和验证组装；不能将它当零时延。

源码核实：
- [runtime3230–3388](https://github.com/NVIDIA/TensorRT-Edge-LLM/blob/e649dadcbbf049fa4caf2f09f3a3275ca56751db/cpp/runtime/qwen3OmniTTSRuntime.cpp#L3230)：prefill取得hidden及第一个残差码；按行维护已提交深度/base长度；后续head批量产生draft，一次多位置verify，按不同head读取验证hidden；accept后提交有效长度、覆盖无效KV后缀。3350附近每轮D2H接受长度/码及cudaStreamSynchronize。直接搬此host同步循环不适合假定能解决当前C1粒度问题。
- [概率kernel211起](https://github.com/NVIDIA/TensorRT-Edge-LLM/blob/e649dadcbbf049fa4caf2f09f3a3275ca56751db/cpp/kernels/speculative/cpSpecKernels.cu#L211)：temperature、radix top-k、top-p及FP32概率；不是当前vLLM sampler逐位等价实现。
- [accept kernel468起](https://github.com/NVIDIA/TensorRT-Edge-LLM/blob/e649dadcbbf049fa4caf2f09f3a3275ca56751db/cpp/kernels/speculative/cpSpecKernels.cu#L468)：min(1,p/q)，首拒绝处采正残差，全部接受则target bonus；q或残差和接近零时含1e−20数值保护。这些近似需要单独审查，不能把实现直接等同实数域定理。

## 当前vLLM目标分布不能换成上游默认

[campaign4645采样1464–1478](https://github.com/amy-why-3459/vllm-omni/blob/4645c450ba4ed036433a30dfcb9782f22b0c3bfd/vllm_omni/model_executor/models/common/qwen3_code_predictor.py#L1464)：stored模式top_k=50，然后top_p=.8，然后Gumbel-max；本分支不应用per-call temperature。top-k用阈值mask `< kth`，边界并列者全部保留，可能超过50个；top-p先对保留logits进行FP32softmax、降序累计，删除prior cumulative>=.8的位置，边界跨越项保留。

**具体不兼容点：** NVIDIA kernel373附近 `kept=min(effectiveTopK,sCandidateCount)` 只保留k个候选，与vLLM保留kth并列者不同；排序并列规则也可能改变top-p边界。不能原样移植概率kernel并宣称相同目标分布。必须复用或精确复现当前mask、排序、FP32归一化与异常行契约。

Gumbel在理想独立连续uniform下实现categorical softmax；有限精度、uniform clamp及tie打破会带细微差别。“同分布”应明确数学目标与有限精度实现误差，不承诺相同seed得到相同序列。现有真实权重BF16 parity已展示shape变化会改变logits；因此“精确speculative sampling”只保证相对于验证器产生的p，不能自动证明相对于原来串行算术完全同分布。

## 建议最小版本：不依赖尚未通过parity的增量KV

1. 首轮维持当前全长17 causal predictor及原head，获得首个残差码和hidden。之后先仅支持B1、小窗口2（一个draft加一个bonus），off-by-default。
2. 在当前已提交深度d的hidden上应用未来head，得到提议q。q可以是不依赖窗口中间草稿的较粗分布，只要确实从该q采样、保留完整q概率。无需训练新head，不承诺接受率。
3. 保留完整长度17输入buf，加入最后已提交码和草稿的对应码本embedding；一次full17 forward提取连续位置的hidden、用各深度原head得到target p与bonus。保持全长形状是减少与现路径算术差异的选择，仍需真实输入验证；不能把不同head GEMM布局当已证明无影响。
4. 依次接受草稿，首拒绝改抽样后终止此轮；accepted prefix+纠正/bonus写回原码本顺序。清零/覆盖未提交后缀；只向Talker/codec提交完整16码帧，首音频/结束语义不改。不引入跨帧预测。
5. 初版full re-prefill不复用KV，避免把已知KV数值差异与speculation混在一起。后续若需要KV，必须按行回滚到最后真实输入位置，并区分“产生的bonus码”和“已经forward进入KV的码”；绝不可将未输入的bonus当成有效KV。
6. B64各行接受长度不同。先做固定窗口和设备端行状态/有效mask；按原request slot维护深度、RNG，保留重排/结束处理。原source统一step的head/embedding选择需扩展为per-row索引，这不是仅改采样函数。若必须host取长度，明确新增同步并先测量，不声称图内解决。

## 分布正确性、残差与RNG

对相同已提交历史H，第j个草稿x来自实际q_j；目标p_j必须是原目标在H加此前已接受草稿上的条件概率。即使q忽略中间草稿，也可视为合法条件分布。以独立U接受：U<=min(1,p_j(x)/q_j(x))。拒绝时从 r(v)=max(p_j(v)−q_j(v),0)/sum_v max(p_j(v)−q_j(v),0) 采纠正码，并丢弃后续草稿。若全部接受，从已经验证的下一位置p抽bonus。尾部不足窗口时截断，不能读不存在的head，也不能生成第16个残差码。

残差必须用最终归一化且应用相同筛选的p/q；不是logit相减，不是再套top-k/top-p到残差，否则改变定理。抽样q中零概率项不应产生提议；非有限或残差数值退化应保留诊断并走明确安全fallback，不能静默声称严格精确。

若使用Gumbel，proposal用log(q)+独立Gumbel，residual用log(r)+独立Gumbel，bonus用log(p)+独立Gumbel；accept用额外独立标量uniform。可以采用inverse-CDF而保持数学categorical分布，但不是原Gumbel bitwise/RNG语义。不能复用相同随机数同时决定draft与accept。

当前接口sample_uniforms[B,15,2048]不足以表达proposal+accept+residual/bonus的独立随机流，不能偷偷重用。最小安全契约是在提供旧显式uniforms或要求原seed重现时fallback；新增request-stable子流以(request,frame,round,role,depth)分域，批次重排不改变对应请求随机性。上游runtime固定seed加global offset的uniform pool不是当前逐请求生成器契约，不直接照搬。

## 验证与收益边界

先CPU概率oracle验证：p=q全部接受、支持集不重叠全部拒绝、部分交集、top-k并列、top-p精确边界、尾部剩1码、非有限fallback、多行不同进度。枚举小词表精确分布及固定随机流测试；之后真实Talker输入的target teacher-forced logits对齐，比较原串行与宽验证的数值、分布和实际接受长度，再进行独立固定质量/性能矩阵。

统计平均提交码/验证轮、各深度接受率、draft/verify/filter/accept/同步耗时和kernel次数。上限只在忽略所有额外成本且全部接受时接近每轮窗口码数；不能用此计算实际收益。当前组件计时中B1 KV甚至更慢，进一步说明减少FLOP不能代替端到端测量。候选状态保持UNTESTED，无实测gain或WER根因结论。
