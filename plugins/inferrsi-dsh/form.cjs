const frameworks = ['auto', 'vllm', 'vllm-omni', 'sglang', 'pytorch', 'other'];
const backends = ['gpu', 'npu'];
const planes = ['harness', 'model', 'infra'];

function taskFromForm(form, connection) {
  const task = {};
  const labels = {
    repository: '目标仓库', model: '模型', objective: '优化目标',
    framework: '推理框架', backend: '计算后端', plane: '本轮改动范围',
    maxRounds: '最多迭代轮数', maxMinutes: '总时间预算',
  };
  for (const name of [
    'repository', 'model', 'objective', 'framework', 'backend', 'plane', 'execution',
    'device', 'acceptance', 'baseline', 'benchmark', 'quality', 'campaign', 'constraints',
  ]) {
    const value = form[name];
    if (value !== undefined && typeof value !== 'string') {
      throw new Error(`${labels[name] || name} 的格式无效。`);
    }
    task[name] = value?.trim() || null;
  }
  for (const name of ['repository', 'model', 'objective', 'plane']) {
    if (!task[name]) throw new Error(`请填写${labels[name]}。`);
  }
  for (const [name, options] of Object.entries({ framework: frameworks, backend: backends, plane: planes })) {
    if (!options.includes(task[name])) throw new Error(`请选择${labels[name]}。`);
  }
  if (!['local', 'remote'].includes(task.execution)) throw new Error('请选择本机或远程机器。');
  if (task.execution === 'remote') {
    if (!connection?.connectionId) throw new Error('请先测试并验证远程连接。');
    task.remote = { connectionId: connection.connectionId };
  }
  for (const name of ['maxRounds', 'maxMinutes']) {
    const value = form[name];
    if (typeof value !== 'string' && typeof value !== 'number') {
      throw new Error(`请填写${labels[name]}。`);
    }
    const number = Number(value);
    if (!Number.isSafeInteger(number) || number <= 0) {
      throw new Error(`${labels[name]}必须是正整数。`);
    }
    task[name] = number;
  }
  return task;
}

function buildPrompt(form, connection) {
  const task = taskFromForm(form, connection);
  return [
    '请使用已安装的 InferRSI 技能，在本会话中执行下面的迭代优化任务。',
    '这份请求由用户填写表单并点击“启动迭代”提交。按填写的仓库、改动范围和预算开展工作。',
    '',
    '任务参数',
    '```json',
    JSON.stringify({ schema_version: 1, ...task }, null, 2),
    '```',
    '',
    '执行要求',
    '1. 校验目标仓库和运行环境，读取仓库的 AGENTS.md，加载 InferRSI 技能并检查随包运行时。',
    '   backend 表示 GPU 或 NPU 硬件类别。检查设备后再选择受支持的实际运行时后端。execution=remote 时，使用 inferrsi_remote 工具和 remote.connectionId，在已经测试的远程仓库内开展工作；通过 cli 操作运行随包 InferRSI，通过 dashboard 操作打开转发后的实时页面。',
    '2. 从 acceptance 引用读取已有验收条件。字段为空时先检查仓库内相关计划和脚本，准备缺失项。冻结 baseline、工作负载、验证器和数值门槛后再开始候选实验。关键验收输入无法确定时说明缺口。',
    '3. 在用户选择的 plane 范围内逐轮提出假设、修改、比较和决策。使用 maxRounds 限制优化迭代轮数，使用 maxMinutes 限制总时间。每轮中的 A/B 重复测量次数由冻结计划确定。到达预算后停止新实验并汇报当前证据。',
    '4. 使用现有 InferRSI CLI 和目标仓库的基准、质量脚本。保留现有用户改动，遵守已有资源和执行授权。复用已准备好的目标环境。',
    '5. 使用明确的 campaign 记录目标、知识检索上下文、搜索空间、每轮假设、决策和 run_id 关联，保留失败、跳过和回滚记录。使用 campaign capture-context、campaign record 和 campaign log。',
    '6. 通过随包启动器打开该 campaign 的 dashboard --live --port 0，返回实际启动 URL 并保留服务进程标识。实时监控和历史轮次由现有 dashboard 展示。',
    '7. 结论依据冻结验证器与运行证据，保留 PASS、FAIL、INCONCLUSIVE。服务性能结论需要相应 L4 或 campaign 定义的端到端证据。',
    '8. 汇报完成的轮数、候选决策、证据目录、dashboard 链接、剩余缺口和下一步。',
  ].join('\n');
}

module.exports = { taskFromForm, buildPrompt };
