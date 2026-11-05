const React = require('react');
const { buildPrompt } = require('./form.cjs');
const h = React.createElement;

const styles = `
.irsi-open { font: inherit; padding: 5px 10px; border: 1px solid color-mix(in srgb, currentColor 20%, transparent); border-radius: 7px; background: transparent; color: inherit; cursor: pointer; }
.irsi-dialog { width: min(720px, calc(100vw - 28px)); max-height: calc(100dvh - 40px); padding: 0; border: 1px solid color-mix(in srgb, CanvasText 20%, transparent); border-radius: 14px; background: Canvas; color: CanvasText; color-scheme: light dark; font: 14px/1.5 system-ui, sans-serif; }
.irsi-dialog::backdrop { background: #0008; }
.irsi-dialog * { box-sizing: border-box; }
.irsi-dialog header { display: flex; justify-content: space-between; align-items: start; gap: 16px; padding: 20px 22px 12px; }
.irsi-dialog h2 { margin: 0; font-size: 20px; }
.irsi-dialog p { margin: 5px 0 0; opacity: .75; }
.irsi-dialog button { font: inherit; cursor: pointer; border: 1px solid color-mix(in srgb, currentColor 24%, transparent); border-radius: 7px; background: transparent; color: inherit; padding: 7px 12px; }
.irsi-dialog button:disabled { cursor: default; opacity: .55; }
.irsi-dialog form { padding: 0 22px 20px; }
.irsi-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 16px; }
.irsi-field { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.irsi-wide { grid-column: 1 / -1; }
.irsi-field input, .irsi-field select, .irsi-field textarea { width: 100%; min-width: 0; font: inherit; color: inherit; background: Canvas; border: 1px solid color-mix(in srgb, currentColor 24%, transparent); border-radius: 7px; padding: 8px 10px; }
.irsi-field textarea { resize: vertical; min-height: 72px; }
.irsi-dialog details { margin-top: 16px; }
.irsi-dialog summary { cursor: pointer; padding: 5px 0; }
.irsi-dialog details .irsi-fields { margin-top: 9px; }
.irsi-preview { white-space: pre-wrap; overflow-wrap: anywhere; font: 12px/1.6 ui-monospace, monospace; padding: 12px; background: color-mix(in srgb, CanvasText 5%, Canvas); border-radius: 8px; }
.irsi-actions { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; margin-top: 18px; }
.irsi-actions span { opacity: .7; font-size: 12px; }
.irsi-dialog .irsi-start { background: #315ec7; border-color: #315ec7; color: white; padding: 9px 18px; }
.irsi-message { padding: 10px 0 0; }
.irsi-error { color: light-dark(#a22626, #ffb6b6); }
.irsi-remote { margin: 4px 0; padding: 12px; border: 1px solid color-mix(in srgb, currentColor 20%, transparent); border-radius: 8px; min-width: 0; }
.irsi-remote > button { margin-top: 10px; }
.irsi-fingerprint { display: block; overflow-wrap: anywhere; margin: 6px 0; }
@media(max-width: 520px) { .irsi-fields { grid-template-columns: 1fr; } .irsi-field { grid-column: 1; } .irsi-dialog header { padding: 15px; } .irsi-dialog form { padding: 0 15px 15px; } .irsi-field input, .irsi-field select, .irsi-field textarea { font-size: 16px; } }
`;

function IterationForm({ sessionId, useSession, useSessions, useAccess, submitPrompt, remoteRequest }) {
  const cwd = useSessions(state => state.byId[sessionId]?.cwd || '');
  const session = useSession(state => state);
  const canSend = useAccess('session/prompt');
  const [open, setOpen] = React.useState(false);
  const [form, setForm] = React.useState({
    repository: cwd, model: '', objective: '', framework: 'auto', backend: '', execution: 'local',
    plane: '', maxRounds: '', maxMinutes: '', device: '', acceptance: '', baseline: '',
    benchmark: '', quality: '', campaign: '', constraints: '',
    host: '', sshPort: '22', sshUser: '', authType: 'key', privateKey: '', password: '',
    passphrase: '', sshFingerprint: '',
  });
  const [error, setError] = React.useState('');
  const [sending, setSending] = React.useState(false);
  const [sent, setSent] = React.useState(false);
  const [connection, setConnection] = React.useState(null);
  const [connectionState, setConnectionState] = React.useState(null);
  const [testing, setTesting] = React.useState(false);
  const dialog = React.useRef(null);
  const inFlight = React.useRef(false);
  const sentOnce = React.useRef(false);
  const mounted = React.useRef(true);
  const testAbort = React.useRef(null);
  const keyInput = React.useRef(null);
  const connectionRef = React.useRef(null);
  const submittedConnection = React.useRef(false);

  React.useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      testAbort.current?.abort();
      if (connectionRef.current && !submittedConnection.current) {
        remoteRequest({ action: 'close', sessionId,
          connectionId: connectionRef.current.connectionId }).catch(() => {});
      }
    };
  }, []);
  React.useEffect(() => {
    setForm(value => value.repository || value.execution === 'remote' ? value : { ...value, repository: cwd });
  }, [cwd]);
  React.useEffect(() => {
    if (open && !dialog.current.open) dialog.current.showModal();
    if (!open && dialog.current.open) dialog.current.close();
  }, [open]);

  const blocked = sending || sent || testing || !canSend || session.running || session.removed
    || session.openState !== 'open' || session.pendingSubmissions.length > 0
    || (form.execution === 'remote' && !connection);

  function update(name, value) {
    setForm(current => ({ ...current, [name]: value,
      ...(name === 'execution' ? { repository: value === 'local' ? cwd : '' } : {}),
    }));
    if (['execution', 'repository', 'host', 'sshPort', 'sshUser', 'authType', 'privateKey',
      'password', 'passphrase', 'sshFingerprint', 'benchmark', 'quality'].includes(name)) {
      testAbort.current?.abort();
      if (connection) remoteRequest({ action: 'close', sessionId, connectionId: connection.connectionId }).catch(() => {});
      setConnection(null);
      connectionRef.current = null;
      submittedConnection.current = false;
      setConnectionState(null);
    }
    setError('');
    setSent(false);
    sentOnce.current = false;
  }

  async function start(event) {
    event.preventDefault();
    if (blocked || inFlight.current || sentOnce.current) return;
    let prompt;
    try {
      prompt = buildPrompt(form, connection);
    } catch (failure) {
      setError(failure.message);
      return;
    }
    inFlight.current = true;
    setSending(true);
    setError('');
    submittedConnection.current = form.execution === 'remote';
    try {
      await submitPrompt(sessionId, prompt);
      sentOnce.current = true;
      if (mounted.current) setSent(true);
    } catch (failure) {
      if (mounted.current) setError(`提交未完成。请先查看当前会话是否已收到任务，再决定重试。${failure.message || ''}`);
    } finally {
      inFlight.current = false;
      if (mounted.current) setSending(false);
    }
  }

  async function testConnection(fingerprint) {
    if (testing || sending || session.running) return;
    testAbort.current?.abort();
    const abort = new AbortController();
    testAbort.current = abort;
    setTesting(true);
    setConnection(null);
    setError('');
    try {
      const result = await remoteRequest({ action: 'test', sessionId, options: {
        host: form.host, port: form.sshPort, user: form.sshUser,
        authType: form.authType, privateKey: form.privateKey, password: form.password,
        passphrase: form.passphrase, fingerprint: fingerprint || form.sshFingerprint,
        repository: form.repository, benchmark: form.benchmark, quality: form.quality,
      } }, abort.signal);
      if (!mounted.current || abort.signal.aborted) {
        if (result.connectionId) remoteRequest({ action: 'close', sessionId,
          connectionId: result.connectionId }).catch(() => {});
        return;
      }
      setConnectionState(result);
      if (result.status === 'connected') {
        connectionRef.current = result;
        setConnection(result);
        setForm(value => ({ ...value, privateKey: '', password: '', passphrase: '',
          sshFingerprint: result.fingerprint }));
        if (keyInput.current) keyInput.current.value = '';
      }
    } catch (failure) {
      if (mounted.current && !abort.signal.aborted) setError(failure.message);
    } finally {
      if (mounted.current && testAbort.current === abort) setTesting(false);
    }
  }

  function field(name, label, { options, multiline = false, wide = false, ...attributes } = {}) {
    const props = {
      name, value: form[name], disabled: sending || testing || (form.execution === 'remote' && session.running),
      onChange: event => update(name, event.target.value), ...attributes,
    };
    let input;
    if (options) {
      input = h('select', props, options.map(([value, title]) => h('option', { key: value, value }, title)));
    } else {
      input = h(multiline ? 'textarea' : 'input', props);
    }
    return h('label', { className: `irsi-field${wide ? ' irsi-wide' : ''}` }, h('span', null, label), input);
  }

  let preview;
  try {
    preview = buildPrompt(form, connection);
  } catch {
    preview = '填写必填项后，这里显示即将发送到当前 Agent 的完整 prompt。';
  }

  return h(React.Fragment, null,
    h('style', null, styles),
    h('button', { type: 'button', className: 'irsi-open', onClick: () => setOpen(true) }, 'InferRSI'),
    h('dialog', {
      ref: dialog, className: 'irsi-dialog', 'aria-labelledby': `irsi-title-${sessionId}`,
      onCancel: () => { testAbort.current?.abort(); setOpen(false); },
      onClose: () => { testAbort.current?.abort(); setOpen(false); },
    },
    h('header', null,
      h('div', null, h('h2', { id: `irsi-title-${sessionId}` }, '启动迭代优化'),
        h('p', null, '填写任务参数，交给当前 Agent 执行。进度与历史在 dashboard 查看。')),
      h('button', { type: 'button', 'aria-label': '关闭 InferRSI 表单', onClick: () => setOpen(false) }, '关闭')),
    h('form', { onSubmit: start },
      h('div', { className: 'irsi-fields' },
        field('repository', '目标仓库 *', { required: true, wide: true, maxLength: 1024, placeholder: '运行环境中的仓库路径' }),
        field('model', '模型 *', { required: true, maxLength: 256, placeholder: '模型名称或已有权重路径' }),
        field('framework', '推理框架', { options: [['auto', '从仓库识别'], ['vllm', 'vLLM'], ['vllm-omni', 'vLLM-Omni'], ['sglang', 'SGLang'], ['pytorch', 'PyTorch'], ['other', '其他']] }),
        field('backend', '硬件后端 *', { required: true, options: [['', '请选择'], ['gpu', 'GPU'], ['npu', 'NPU']] }),
        field('execution', '运行位置', { options: [['local', '本机运行'], ['remote', '远程机器']] }),
        field('plane', '本轮改动范围 *', { required: true, options: [['', '请选择'], ['harness', 'Harness / 执行与评测'], ['model', 'Model / 模型与算子'], ['infra', 'Infra / 基础设施']] }),
        form.execution === 'remote' && h('fieldset', { className: 'irsi-wide irsi-remote' },
          h('legend', null, 'SSH 远程连接'),
          h('div', { className: 'irsi-fields' },
            field('host', '机器 IP *', { required: true, placeholder: '目标机器的 IPv4 或 IPv6', maxLength: 64 }),
            field('sshPort', 'SSH 端口 *', { required: true, type: 'number', min: 1, max: 65535, step: 1 }),
            field('sshUser', 'SSH 用户名 *', { required: true, maxLength: 128 }),
            field('authType', '认证方式', { options: [['key', 'SSH 私钥'], ['password', '用户密码']] }),
            form.authType === 'key' && h('label', { className: 'irsi-field irsi-wide' },
              h('span', null, form.privateKey ? 'SSH 私钥已载入' : '选择 SSH 私钥文件'),
              h('input', { ref: keyInput, type: 'file', disabled: testing || sending || session.running,
                onChange: async event => {
                  const file = event.target.files?.[0];
                  if (!file) return;
                  if (file.size > 64 * 1024) { setError('私钥文件超过大小限制。'); return; }
                  update('privateKey', await file.text());
                } })),
            form.authType === 'key'
              ? field('passphrase', '私钥口令（如有）', { type: 'password', autoComplete: 'new-password', maxLength: 4096 })
              : field('password', 'SSH 用户密码', { type: 'password', autoComplete: 'new-password', maxLength: 4096 }),
            field('sshFingerprint', '服务器指纹（首次连接可留空）', { wide: true, placeholder: 'SHA256:…', maxLength: 128 })),
          h('p', null, '连接到远程 Linux 主机。目标仓库需填写远程机器上的绝对路径。'),
          h('button', { type: 'button', disabled: testing || sending || session.running || Boolean(connection),
            onClick: () => testConnection() }, testing ? '正在测试…' : connection ? '连接已验证' : '测试连接'),
          connectionState?.status === 'verify_host' && h('div', { className: 'irsi-message' },
            h('p', null, '请核对服务器指纹'), h('code', { className: 'irsi-fingerprint' }, connectionState.fingerprint),
            h('button', { type: 'button', disabled: testing, onClick: () => testConnection(connectionState.fingerprint) }, '信任此指纹并测试')),
          connection && h('div', { className: 'irsi-message', role: 'status' }, 'SSH 认证与仓库访问成功。本会话可使用该远程连接。')),
        field('objective', '优化目标 *', { required: true, multiline: true, wide: true, maxLength: 4096, placeholder: '希望改善什么，面向什么模型和工作负载' }),
        field('maxRounds', '最多优化轮数 *', { type: 'number', required: true, min: 1, step: 1, placeholder: '填写轮数上限' }),
        field('maxMinutes', '总时间预算（分钟）*', { type: 'number', required: true, min: 1, step: 1, placeholder: '填写总时间上限' })),
      h('details', null, h('summary', null, '验收与执行条件（可选，Agent 会检查缺失项）'),
        h('div', { className: 'irsi-fields' },
          field('acceptance', '验收 Issue 或已有计划', { wide: true, maxLength: 2048, placeholder: '已有验收记录的链接或路径' }),
          field('baseline', '基线修订', { maxLength: 256, placeholder: '已接受的 baseline revision' }),
          field('device', '设备与运行环境', { maxLength: 1024, placeholder: '使用哪些已准备好的设备' }),
          field('benchmark', '已有基准脚本', { maxLength: 1024, placeholder: '仓库中的脚本路径' }),
          field('quality', '已有质量验证脚本', { maxLength: 1024, placeholder: '仓库中的验证脚本路径' }),
          field('campaign', 'Campaign 目录', { wide: true, maxLength: 1024, placeholder: '现有 campaign 路径，留空由 Agent 准备' }),
          field('constraints', '质量门槛与其他约束', { multiline: true, wide: true, maxLength: 4096, placeholder: '填写已有数值门槛、保持的能力和限制' }))),
      h('details', null, h('summary', null, '查看生成的 prompt'), h('pre', { className: 'irsi-preview' }, preview)),
      error && h('div', { className: 'irsi-message irsi-error', role: 'alert' }, error),
      sent && h('div', { className: 'irsi-message', role: 'status' }, '任务已发送到当前 Agent。关闭表单后可在会话中查看执行进展。'),
      h('div', { className: 'irsi-actions' },
        h('span', null, session.running ? '当前 Agent 正在工作，请待本次任务结束后启动。' : '提交到当前会话 · 受填写的轮数与时间预算约束'),
        h('button', { type: 'submit', className: 'irsi-start', disabled: blocked }, sending ? '正在发送…' : sent ? '已发送' : '启动迭代')))));
}

function FormAction(props) {
  return h(IterationForm, { ...props, key: props.sessionId });
}

function apply(ctx) {
  ctx.slots.inject('conversation.input.right', () => ctx.slots.register({
    name: 'conversation.input.right', id: 'inferrsi-form', order: 40,
    inject: () => ({
      remoteRequest: async (payload, signal) => {
        if (payload.action === 'test' && !globalThis.isSecureContext) {
          throw new Error('输入 SSH 凭据需要使用本机 DSH 页面或 HTTPS 连接。');
        }
        const response = await fetch(new URL('api/inferrsi/connection', document.baseURI), {
          method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload), signal,
        });
        const result = await response.json();
        if (!response.ok || result.status === 'error') {
          throw new Error(result.message || '连接请求未完成，请检查网络后重试。');
        }
        return result;
      },
      submitPrompt: async (sessionId, text) => {
        const scope = ctx.sessions.scope(sessionId);
        if (!scope) throw new Error('当前会话已关闭，请重新打开后提交。');
        const session = ctx.sessions.sessionOf(scope);
        if (!session || session.getSnapshot().running) throw new Error('当前 Agent 正忙，请稍后再试。');
        const conversation = scope.get('conversation');
        if (!conversation) throw new Error('当前会话的消息服务不可用。');
        await conversation.send(text);
      },
    }),
  }, FormAction));
}

module.exports = { inject: ['slots', 'sessions', 'conversation'], apply };
