const frameworks = ['auto', 'vllm', 'vllm-omni', 'sglang', 'pytorch', 'other'];
const backends = ['gpu', 'npu'];
const planes = ['harness', 'model', 'infra'];
const executions = ['local', 'remote'];
const { isMap, isScalar, parseDocument } = require('./vendor/yaml.cjs');
const yamlSizeLimit = 64 * 1024;

const taskYamlTemplate = `# Fill the task fields. Omit unknown optional inputs or leave them null.
# Do not include SSH connection settings or credentials.
schema_version: 1
optimization:
  repository: null  # Local workspace by default; absolute path for remote.
  model: null
  framework: auto   # auto | vllm | vllm-omni | sglang | pytorch | other
  plane: null       # harness | model | infra
  objective: null   # Use | for a multiline goal.
environment:
  backend: null     # gpu | npu
  execution: local  # local | remote
  device: null
  benchmark: null
  quality: null
  campaign: null
  maxRounds: null   # Positive integer.
  maxMinutes: null  # Positive integer.
acceptance:
  reference: null   # Acceptance issue URL or plan path.
  baseline: null    # Quote a revision if it looks like a number.
  constraints: null # Use | for multiline metrics and thresholds.
`;

function taskDefaults(repository) {
  return {
    repository, model: '', objective: '', framework: 'auto', backend: '', execution: 'local',
    plane: '', maxRounds: '', maxMinutes: '', device: '', acceptance: '', baseline: '',
    benchmark: '', quality: '', campaign: '', constraints: '',
  };
}

const yamlSections = {
  optimization: { repository: 1024, model: 256, objective: 4096, framework: frameworks, plane: planes },
  environment: {
    backend: backends, execution: executions, device: 1024, benchmark: 1024, quality: 1024,
    campaign: 1024, maxRounds: 'budget', maxMinutes: 'budget',
  },
  acceptance: { reference: 2048, baseline: 256, constraints: 4096 },
};

function plainNode(node) {
  return !node?.tag && !node?.anchor;
}

function yamlMapping(node, allowed, label) {
  if (!isMap(node) || !plainNode(node)) throw new Error(`${label} 必须是普通键值表。`);
  const entries = {};
  for (const { key, value } of node.items) {
    if (!isScalar(key) || !plainNode(key) || typeof key.value !== 'string' || !Object.hasOwn(allowed, key.value)) {
      throw new Error(`${label} 含有不支持的字段，请对照 YAML 模板。`);
    }
    entries[key.value] = value;
  }
  return entries;
}

function readTaskYaml(source, cwd) {
  if (source.length > yamlSizeLimit) throw new Error('YAML 文件不能超过 64 KiB。');
  let doc;
  try {
    doc = parseDocument(source, { version: '1.2', schema: 'core', merge: false, prettyErrors: false });
  } catch {
    throw new Error('无法解析 YAML，请检查文件格式。');
  }
  if (doc.errors.length || doc.warnings.length || doc.directives.yaml.version !== '1.2') {
    throw new Error('请提供一份有效的 YAML 1.2 文档，字段不能重复。');
  }
  const sections = yamlMapping(doc.contents, { schema_version: true, ...yamlSections }, 'YAML');
  const version = sections.schema_version;
  if (!isScalar(version) || !plainNode(version) || version.value !== 1) {
    throw new Error('YAML 必须包含 schema_version: 1。');
  }

  const task = {};
  let fieldCount = 0;
  for (const [section, fields] of Object.entries(yamlSections)) {
    if (!Object.hasOwn(sections, section)) continue;
    for (const [key, node] of Object.entries(yamlMapping(sections[section], fields, section))) {
      fieldCount += 1;
      if (node === null) continue;
      if (!isScalar(node) || !plainNode(node)) throw new Error(`${section}.${key} 必须是普通值。`);
      const value = node.value;
      if (value === null) continue;
      const rule = fields[key];
      const valid = rule === 'budget' ? Number.isSafeInteger(value) && value > 0
        : Array.isArray(rule) ? rule.includes(value)
          : typeof value === 'string' && value.length <= rule;
      if (!valid) throw new Error(`${section}.${key} 的值无效，请对照 YAML 模板。`);
      task[key === 'reference' ? 'acceptance' : key] = rule === 'budget' ? String(value) : value;
    }
  }
  if (!fieldCount) throw new Error('YAML 中至少需要一个任务字段。');
  return { ...taskDefaults(task.execution === 'remote' ? '' : cwd), ...task };
}

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
  if (!executions.includes(task.execution)) throw new Error('请选择本机或远程机器。');
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
    '2. 优先使用用户提供的验收标准，包括 constraints 和 acceptance 引用中的已有条件，不得用估计值替换或降低门槛。未提供验收标准时，使用仓库的 performance-ceiling-analysis 技能及其 acceptance-criteria.md 流程制定标准；部分提供时保留已有要求，只推导缺失项并标明来源。记录基线、校准依据、不确定性和已有冻结授权；理论上限不能直接当作可达目标或质量容差。条件冲突时先澄清，证据不足时列出缺口和补测计划。冻结 baseline、工作负载、验证器和数值门槛后再开始候选实验。',
    '3. 在用户选择的 plane 范围内逐轮提出假设、修改、比较和决策。使用 maxRounds 限制优化迭代轮数，使用 maxMinutes 限制总时间。每轮中的 A/B 重复测量次数由冻结计划确定。到达预算后停止新实验并汇报当前证据。',
    '4. 使用现有 InferRSI CLI 和目标仓库的基准、质量脚本。远程 run_script 必须传入 maxMinutes，远程长时间 cli 操作也传入该参数，按任务剩余总时间预算设置，不能为每次调用重新分配完整预算。保留现有用户改动，遵守已有资源和执行授权。复用已准备好的目标环境。',
    '5. 使用明确的 campaign 记录目标、知识检索上下文、搜索空间、每轮假设、决策和 run_id 关联，保留失败、跳过和回滚记录。使用 campaign capture-context、campaign record 和 campaign log。',
    '6. execution=remote 时通过 inferrsi_remote 的 dashboard 操作打开该 campaign 的实时页面，保留连接标识；本机模式通过随包启动器运行 dashboard --live --port 0 并保留服务进程标识。返回实际 URL，实时监控和历史轮次由现有 dashboard 展示。',
    '7. 结论依据冻结验证器与运行证据，保留 PASS、FAIL、INCONCLUSIVE。服务性能结论需要相应 L4 或 campaign 定义的端到端证据。',
    '8. 汇报完成的轮数、候选决策、证据目录、dashboard 链接、剩余缺口和下一步。',
  ].join('\n');
}

module.exports = { taskFromForm, buildPrompt, taskDefaults, taskYamlTemplate, readTaskYaml, yamlSizeLimit };
