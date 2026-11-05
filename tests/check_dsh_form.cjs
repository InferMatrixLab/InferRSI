const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { buildPrompt, taskFromForm } = require(process.argv[2]);

// Render the bundled component's actual hooks and handlers without a browser.
let rendering;
const React = {
  Fragment: 'fragment',
  createElement(type, props, ...children) {
    if (props?.ref && !props.ref.current) {
      props.ref.current = { open: false, value: '',
        showModal() { this.open = true; }, close() { this.open = false; } };
    }
    return { type, props: props || {}, children };
  },
  useState(initial) {
    const instance = rendering;
    const index = instance.cursor++;
    if (!(index in instance.hooks)) instance.hooks[index] = initial;
    return [instance.hooks[index], value => {
      instance.hooks[index] = typeof value === 'function' ? value(instance.hooks[index]) : value;
    }];
  },
  useRef(initial) {
    const instance = rendering;
    const index = instance.cursor++;
    if (!(index in instance.hooks)) instance.hooks[index] = { current: initial };
    return instance.hooks[index];
  },
  useEffect(effect, dependencies) {
    const instance = rendering;
    const index = instance.cursor++;
    const previous = instance.hooks[index];
    if (!previous || dependencies.some((value, i) => !Object.is(value, previous.dependencies[i]))) {
      instance.effects.push(() => {
        previous?.cleanup?.();
        instance.hooks[index] = { dependencies, cleanup: effect() };
      });
    }
  },
};

function mount(Action, props) {
  const component = Action(props);
  const instance = { hooks: [], cursor: 0, effects: [], tree: null };
  instance.render = () => {
    instance.cursor = 0;
    rendering = instance;
    try { instance.tree = component.type(component.props); } finally { rendering = null; }
    for (const effect of instance.effects.splice(0)) effect();
    return instance.tree;
  };
  instance.unmount = () => {
    for (const hook of instance.hooks) hook?.cleanup?.();
  };
  instance.find = (predicate, root = instance.tree) => {
    function visit(node) {
      if (!node || typeof node !== 'object') return undefined;
      if (predicate(node)) return node;
      for (const child of node.children.flat(Infinity)) {
        const found = visit(child);
        if (found) return found;
      }
    }
    const result = visit(root);
    assert.ok(result, 'expected rendered element');
    return result;
  };
  instance.render();
  return instance;
}

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

async function main() {
  const form = {
    repository: 'workspace with spaces', model: 'Example model', objective: '降低推理延迟',
    framework: 'auto', backend: 'gpu', plane: 'harness', execution: 'local', maxRounds: '3', maxMinutes: '20',
    constraints: '保留质量门槛\n带引号的 "要求" 和 ``` 字符',
  };
  const prompt = buildPrompt(form);
  const task = JSON.parse(prompt.match(/```json\n([\s\S]+?)\n```/u)[1]);
  assert.equal(task.repository, form.repository);
  assert.equal(task.constraints, form.constraints);
  assert.equal(task.maxRounds, 3);
  assert.equal(task.maxMinutes, 20);
  assert.equal(task.acceptance, null);
  assert.equal(task.execution, 'local');
  const remote = { ...form, backend: 'npu', execution: 'remote', host: '192.0.2.1',
    password: 'fake-test-password', privateKey: 'fake-test-key' };
  assert.throws(() => buildPrompt(remote));
  const remotePrompt = buildPrompt(remote, { connectionId: 'test-connection' });
  assert.match(remotePrompt, /test-connection/u);
  assert.ok(!remotePrompt.includes('fake-test-password') && !remotePrompt.includes('fake-test-key'));
  assert.ok(!remotePrompt.includes('192.0.2.1'));
  assert.match(prompt, /dashboard --live --port 0/u);
  assert.match(prompt, /冻结/u);
  for (const values of [
    { objective: '' }, { repository: ' ' }, { plane: 'unknown' }, { backend: 'unknown' },
    { maxRounds: '' }, { maxRounds: '1.5' }, { maxRounds: 'Infinity' },
    { maxMinutes: 0 }, { maxMinutes: false }, { model: {} },
  ]) {
    assert.throws(() => taskFromForm({ ...form, ...values }));
  }

  let plugin;
  let nativeError;
  let nativeReply = { status: 'error', code: 'unknown_receipt' };
  let nativeStatus = 400;
  vm.runInNewContext(fs.readFileSync(process.argv[3], 'utf8'), {
    AbortController,
    URL,
    document: { baseURI: 'https://example.invalid/' },
    fetch: async () => {
      if (nativeError) throw nativeError;
      return { ok: nativeStatus >= 200 && nativeStatus < 300, status: nativeStatus, json: async () => nativeReply };
    },
    window: { __ModuleLoader__: { load: ({ id, factory }) => {
      assert.equal(id, 'inferrsi-dsh');
      plugin = factory(name => {
        assert.equal(name, 'react');
        return React;
      });
    } } },
  });
  let registration;
  let Action;
  const deliveries = [];
  let running = false;
  let conversationAvailable = true;
  let send = async () => {};
  const scope = { get: name => {
    assert.equal(name, 'conversation');
    return conversationAvailable ? { send: text => { deliveries.push(text); return send(text); } } : undefined;
  } };
  plugin.apply({
    slots: {
      inject: (key, callback) => {
        assert.equal(key, 'conversation.input.right');
        callback();
      },
      register: (definition, component) => { registration = definition; Action = component; },
    },
    sessions: {
      scope: id => id === 'target-session' ? scope : undefined,
      sessionOf: value => {
        assert.equal(value, scope);
        return { getSnapshot: () => ({ running }) };
      },
    },
  });
  const submit = registration.inject().submitPrompt;
  await submit('target-session', prompt);
  assert.equal(deliveries.length, 1);
  assert.equal(deliveries[0], prompt);
  await assert.rejects(submit('different-session', prompt), error => error.submissionState === 'rejected');
  running = true;
  await assert.rejects(submit('target-session', prompt), error => error.submissionState === 'rejected');
  assert.equal(deliveries.length, 1);
  running = false;
  conversationAvailable = false;
  await assert.rejects(submit('target-session', prompt), error => error.submissionState === 'rejected');
  conversationAvailable = true;
  send = async () => { throw Object.assign(new Error('unconfirmed admission'), { submissionState: 'rejected' }); };
  await assert.rejects(submit('target-session', prompt), error => error.submissionState === 'ambiguous');
  const nativeRequest = registration.inject().remoteRequest;
  for (const code of ['unknown_receipt', 'connection_unavailable', 'permission_denied']) {
    nativeReply = { status: 'error', code };
    await assert.rejects(nativeRequest({ action: 'close', sessionId: 'target-session', connectionId: 'test-receipt' }),
      error => error.code === code, 'the HTTP wrapper preserves structured close codes');
  }
  nativeReply = { status: 'error', code: 'unknown_receipt' };
  for (const status of [200, 401, 403, 500]) {
    nativeStatus = status;
    await assert.rejects(nativeRequest({ action: 'close' }), error => error.code === undefined,
      'only a Host business error response can authorize unknown-receipt recovery');
  }
  nativeStatus = 400;
  nativeReply = { code: 'unknown_receipt' };
  await assert.rejects(nativeRequest({ action: 'close' }), error => error.code === undefined);
  nativeError = new Error('synthetic network failure mentioning unknown_receipt');
  await assert.rejects(nativeRequest({ action: 'close' }), error => error.code === undefined);
  nativeError = null;

  async function remoteForm({ connect = true, sessionId = 'target-session' } = {}) {
    // Let confirmed cleanup from a previous unmount settle before a new fixture.
    if (connect) await new Promise(resolve => setImmediate(resolve));
    const requests = [];
    let closeFails = false;
    let close = async () => {
      if (closeFails) throw new Error('synthetic close failure');
      return { status: 'closed' };
    };
    let test = async () => ({ status: 'connected', connectionId: 'synthetic-connection', fingerprint: 'SHA256:synthetic' });
    const instance = mount(Action, {
      sessionId, submitPrompt: submit,
      useSession: selector => selector({ running: false, removed: false, openState: 'open', pendingSubmissions: [] }),
      useSessions: selector => selector({ byId: { [sessionId]: { cwd: '/workspace/example' } } }),
      useAccess: () => true,
      remoteRequest: async request => {
        requests.push(request);
        if (request.action === 'close') {
          return close();
        }
        return test();
      },
    });
    function field(name, value) {
      instance.find(node => node.props.name === name).props.onChange({ target: { value } });
      instance.render();
    }
    if (connect) {
      field('execution', 'remote');
      for (const [name, value] of Object.entries({ ...form, execution: 'remote', repository: '/workspace/example' })) {
        if (!['constraints', 'execution'].includes(name)) field(name, value);
      }
      await instance.find(node => node.type === 'button' && node.children.includes('测试连接')).props.onClick();
      instance.render();
    }
    instance.submit = () => instance.find(node => node.type === 'form').props.onSubmit({ preventDefault() {} });
    instance.closes = () => requests.filter(request => request.action === 'close');
    instance.tests = () => requests.filter(request => request.action === 'test');
    instance.failClose = value => { closeFails = value; };
    instance.closeWith = handler => { close = handler; };
    instance.testWith = handler => { test = handler; };
    instance.field = field;
    return instance;
  }

  // A definite wrapper preflight refusal leaves the form responsible for cleanup.
  let instance = await remoteForm();
  running = true;
  await instance.submit();
  instance.render();
  instance.unmount();
  assert.equal(instance.closes().length, 1);
  running = false;

  // Unmount can occur while awaiting the wrapper; settle the submitted receipt later.
  for (const outcome of ['rejected', 'success', 'ambiguous']) {
    const pending = deferred();
    send = () => pending.promise;
    instance = await remoteForm();
    const pendingTest = instance.find(node => node.type === 'button' && node.children.includes('连接已验证')).props.onClick;
    if (outcome === 'rejected') running = true;
    const attempt = instance.submit();
    const retest = pendingTest();
    assert.equal(instance.tests().length, 1, 'pending admission cannot replace its connection through a stale handler');
    instance.unmount();
    assert.equal(instance.closes().length, 0);
    await retest;
    if (outcome === 'success') pending.resolve();
    else if (outcome === 'ambiguous') pending.reject(new Error('synthetic transport failure'));
    await attempt;
    running = false;
    assert.equal(instance.closes().length, outcome === 'rejected' ? 1 : 0);
  }

  send = async () => {};
  instance = await remoteForm();
  const earlySubmit = instance.find(node => node.type === 'form').props.onSubmit;
  const earlyTest = instance.find(node => node.type === 'button' && node.children.includes('连接已验证')).props.onClick;
  await instance.submit();
  instance.render();
  const admitted = deliveries.length;
  for (const [name, value] of [['repository', '/other'], ['objective', 'another task']]) {
    const field = instance.find(node => node.props.name === name);
    assert.equal(field.props.disabled, true);
    field.props.onChange({ target: { value } });
  }
  await earlyTest();
  await earlySubmit({ preventDefault() {} });
  instance.render();
  assert.equal(instance.closes().length, 0, 'field changes cannot revoke a confirmed handoff');
  assert.equal(instance.tests().length, 1, 'confirmed handoff cannot be retested');
  assert.equal(deliveries.length, admitted, 'confirmed handoff cannot be resubmitted before running refreshes');
  instance.unmount();
  assert.equal(instance.closes().length, 0, 'confirmed admission transfers the connection');

  instance = await remoteForm();
  await instance.submit();
  instance.render();
  await instance.find(node => node.type === 'button' && node.children.includes('断开远程连接（可能中止任务）')).props.onClick();
  instance.render();
  assert.equal(instance.closes().length, 1);
  assert.equal(instance.find(node => node.props.name === 'repository').props.disabled, false);
  await instance.find(node => node.type === 'button' && node.children.includes('测试连接')).props.onClick();
  instance.render();
  const beforeResubmit = deliveries.length;
  await instance.submit();
  assert.equal(deliveries.length, beforeResubmit + 1, 'explicit disconnect and retest permits a new task');
  instance.unmount();
  assert.equal(instance.closes().length, 1);

  send = async () => { throw new Error('synthetic transport failure'); };
  instance = await remoteForm();
  await instance.submit();
  instance.render();
  assert.equal(instance.closes().length, 0);
  assert.equal(instance.find(node => node.props.name === 'repository').props.disabled, true);
  instance.find(node => node.props.name === 'repository').props.onChange({ target: { value: '/other' } });
  const uncertainDeliveries = deliveries.length;
  await instance.submit();
  await instance.find(node => node.type === 'button' && node.children.includes('连接已验证')).props.onClick();
  assert.equal(deliveries.length, uncertainDeliveries);
  assert.equal(instance.tests().length, 1);
  assert.equal(instance.closes().length, 0, 'uncertain admission cannot implicitly close the connection');
  instance.find(node => node.type === 'button' && node.children.includes('保留连接，查看会话')).props.onClick();
  instance.render();
  assert.equal(instance.closes().length, 0);
  instance.failClose(true);
  await instance.find(node => node.type === 'button' && node.children.includes('断开远程连接（可能中止任务）')).props.onClick();
  instance.render();
  assert.equal(instance.find(node => node.props.name === 'repository').props.disabled, true,
    'failed explicit disconnect must retain the uncertain connection');
  instance.failClose(false);
  await instance.find(node => node.type === 'button' && node.children.includes('断开远程连接（可能中止任务）')).props.onClick();
  instance.render();
  assert.equal(instance.find(node => node.props.name === 'repository').props.disabled, false);
  assert.equal(instance.closes().length, 2, 'explicit disconnect supports retry after a failure');
  instance.unmount();
  assert.equal(instance.closes().length, 2, 'successful disconnect is not repeated on unmount');

  // Editing a tested connection closes it before applying any new inputs.
  for (const [name, value] of [['repository', '/other'], ['host', '192.0.2.2'], ['execution', 'local']]) {
    instance = await remoteForm();
    const oldValue = instance.find(node => node.props.name === name).props.value;
    const earlySubmit = instance.find(node => node.type === 'form').props.onSubmit;
    const earlyTest = instance.find(node => node.type === 'button' && node.children.includes('连接已验证')).props.onClick;
    const earlyEdit = instance.find(node => node.props.name === 'objective').props.onChange;
    const pending = deferred();
    instance.closeWith(() => pending.promise);
    const edit = instance.find(node => node.props.name === name).props.onChange({ target: { value } });
    instance.render();
    assert.equal(instance.find(node => node.props.name === name).props.value, oldValue);
    assert.equal(instance.find(node => node.props.name === name).props.disabled, true);
    const before = deliveries.length;
    await earlySubmit({ preventDefault() {} });
    await earlyTest();
    await earlyEdit({ target: { value: 'must remain unchanged' } });
    assert.equal(deliveries.length, before);
    assert.equal(instance.tests().length, 1);
    assert.equal(instance.closes().length, 1);
    pending.reject(Object.assign(new Error('synthetic close refusal'), {
      code: name === 'host' ? 'permission_denied' : 'connection_unavailable',
    }));
    await edit;
    instance.render();
    assert.equal(instance.find(node => node.props.name === name).props.value, oldValue,
      'an unconfirmed close keeps the old inputs and connection receipt');
    assert.equal(instance.find(node => node.props.name === 'repository').props.disabled, true);
    await earlySubmit({ preventDefault() {} });
    await earlyTest();
    assert.equal(deliveries.length, before);
    assert.equal(instance.tests().length, 1);
    instance.closeWith(async () => ({ status: 'closed' }));
    await instance.find(node => node.type === 'button' && node.children.includes('重试断开远程连接')).props.onClick();
    instance.render();
    assert.equal(instance.closes().length, 2);
    assert.ok(instance.closes().every(request => request.connectionId === 'synthetic-connection'));
    assert.equal(instance.find(node => node.props.name === name).props.disabled, false);
    await instance.find(node => node.props.name === name).props.onChange({ target: { value } });
    instance.render();
    assert.equal(instance.find(node => node.props.name === name).props.value, value);
    instance.unmount();
    assert.equal(instance.closes().length, 2);
  }

  for (const status of ['closed', 'already_closed']) {
    instance = await remoteForm();
    instance.closeWith(async () => ({ status }));
    await instance.find(node => node.props.name === 'repository').props.onChange({ target: { value: '/new' } });
    instance.render();
    assert.equal(instance.find(node => node.props.name === 'repository').props.value, '/new');
    assert.equal(instance.find(node => node.props.name === 'repository').props.disabled, false);
    instance.unmount();
    assert.equal(instance.closes().length, 1, 'confirmed closure releases the old receipt exactly once');
  }

  instance = await remoteForm();
  instance.closeWith(async () => ({ status: 'error', code: 'connection_unavailable' }));
  await instance.find(node => node.props.name === 'execution').props.onChange({ target: { value: 'local' } });
  instance.render();
  assert.equal(instance.find(node => node.props.name === 'execution').props.value, 'remote',
    'generic unavailable or permission errors do not establish already-closed ownership');
  instance.closeWith(async () => ({ status: 'already_closed' }));
  instance.unmount();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(instance.closes().length, 2, 'unmount retries an unconfirmed owned receipt');
  instance.unmount();
  assert.equal(instance.closes().length, 2);

  instance = await remoteForm();
  const pendingClose = deferred();
  instance.closeWith(() => pendingClose.promise);
  const abandonedEdit = instance.find(node => node.props.name === 'repository').props.onChange({ target: { value: '/abandoned' } });
  instance.unmount();
  assert.equal(instance.closes().length, 1, 'unmount joins the pending close');
  instance.closeWith(async () => ({ status: 'closed' }));
  pendingClose.reject(new Error('synthetic transport failure'));
  await abandonedEdit;
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(instance.closes().length, 2, 'a pending close that fails after unmount gets one cleanup retry');
  instance.unmount();
  assert.equal(instance.closes().length, 2);

  // A failed edit close and failed unmount retry retain only the opaque receipt.
  instance = await remoteForm();
  instance.failClose(true);
  await instance.find(node => node.props.name === 'execution').props.onChange({ target: { value: 'local' } });
  instance.unmount();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(instance.closes().length, 2);
  const unrelated = await remoteForm({ connect: false, sessionId: 'unrelated-session' });
  assert.equal(unrelated.find(node => node.props.name === 'repository').props.disabled, false,
    'pending cleanup belongs only to its owning session');
  unrelated.unmount();
  instance = await remoteForm({ connect: false });
  assert.equal(instance.find(node => node.props.name === 'repository').props.disabled, true);
  assert.equal(instance.find(node => node.props.type === 'submit').props.disabled, true);
  instance.field('execution', 'remote');
  assert.equal(instance.find(node => node.props.name === 'execution').props.value, 'local');
  instance.closeWith(async () => ({ status: 'already_closed' }));
  await instance.find(node => node.type === 'button' && node.children.includes('重试断开远程连接')).props.onClick();
  instance.render();
  assert.equal(instance.closes().length, 1);
  assert.equal(instance.closes()[0].connectionId, 'synthetic-connection');
  assert.deepEqual(Object.keys(instance.closes()[0]).sort(), ['action', 'connectionId', 'sessionId']);
  assert.equal(instance.find(node => node.props.name === 'repository').props.disabled, false);
  instance.unmount();

  function prepareRemote(instance) {
    instance.field('execution', 'remote');
    for (const [name, value] of Object.entries({ ...form, execution: 'remote', repository: '/workspace/example' })) {
      if (!['constraints', 'execution'].includes(name)) instance.field(name, value);
    }
  }

  // A test result returned after abandonment also retains a failed cleanup receipt.
  instance = await remoteForm({ connect: false });
  prepareRemote(instance);
  const lateTest = deferred();
  instance.testWith(() => lateTest.promise);
  instance.failClose(true);
  const abandonedTest = instance.find(node => node.type === 'button' && node.children.includes('测试连接')).props.onClick();
  instance.unmount();
  lateTest.resolve({ status: 'connected', connectionId: 'late-test-connection' });
  await abandonedTest;
  assert.equal(instance.closes()[0].connectionId, 'late-test-connection');
  instance = await remoteForm({ connect: false });
  assert.equal(instance.find(node => node.props.name === 'repository').props.disabled, true);
  await instance.find(node => node.type === 'button' && node.children.includes('重试断开远程连接')).props.onClick();
  instance.render();
  assert.equal(instance.closes()[0].connectionId, 'late-test-connection');
  assert.equal(instance.find(node => node.props.name === 'repository').props.disabled, false);
  instance.unmount();

  // Distinct late receipts must each be queued even while the first close is pending.
  instance = await remoteForm({ connect: false });
  prepareRemote(instance);
  const tests = [deferred(), deferred()];
  let nextTest = 0;
  instance.testWith(() => tests[nextTest++].promise);
  const firstClose = deferred();
  let nextClose = 0;
  instance.closeWith(() => nextClose++ === 0 ? firstClose.promise : Promise.resolve({ status: 'closed' }));
  const testHandler = instance.find(node => node.type === 'button' && node.children.includes('测试连接')).props.onClick;
  const attempts = [testHandler(), testHandler()];
  instance.unmount();
  tests[0].resolve({ status: 'connected', connectionId: 'late-connection-a' });
  tests[1].resolve({ status: 'connected', connectionId: 'late-connection-b' });
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(instance.closes().map(request => request.connectionId), ['late-connection-a']);
  firstClose.resolve({ status: 'closed' });
  await Promise.all(attempts);
  assert.deepEqual(instance.closes().map(request => request.connectionId), ['late-connection-a', 'late-connection-b']);
  instance = await remoteForm({ connect: false });
  assert.equal(instance.find(node => node.props.name === 'repository').props.disabled, false);
  instance.unmount();

  function button(instance, label, root) {
    return instance.find(node => node.type === 'button' && node.children.includes(label), root);
  }
  function chooseForget(instance, connectionId) {
    const row = instance.find(node => node.props['data-connection-id'] === connectionId);
    button(instance, '放弃此本地连接记录', row).props.onClick();
    instance.render();
  }
  function confirmForget(instance) {
    button(instance, '确认放弃本地记录').props.onClick();
    instance.render();
  }
  function noForget(instance) {
    assert.throws(() => button(instance, '放弃此本地连接记录'), /expected rendered element/);
  }
  async function unknownQueue() {
    const owner = await remoteForm();
    owner.closeWith(async () => ({ status: 'error', code: 'unknown_receipt' }));
    await owner.find(node => node.props.name === 'repository').props.onChange({ target: { value: '/other' } });
    owner.unmount();
    await new Promise(resolve => setImmediate(resolve));
    return owner;
  }

  // Unknown Host state permits only an explicit, two-step local-only recovery.
  instance = await remoteForm();
  instance.closeWith(async () => ({ status: 'error', code: 'unknown_receipt' }));
  await instance.find(node => node.props.name === 'repository').props.onChange({ target: { value: '/other' } });
  instance.render();
  chooseForget(instance, 'synthetic-connection');
  assert.equal(instance.closes().length, 1);
  assert.equal(instance.find(node => node.props.name === 'repository').props.disabled, true);
  const cancelledConfirm = button(instance, '确认放弃本地记录').props.onClick;
  button(instance, '取消').props.onClick();
  cancelledConfirm();
  instance.render();
  assert.equal(instance.find(node => node.props.name === 'repository').props.disabled, true);
  chooseForget(instance, 'synthetic-connection');
  confirmForget(instance);
  assert.equal(instance.closes().length, 1, 'forgetting local state does not claim or perform a close');
  assert.equal(instance.find(node => node.props.name === 'repository').props.disabled, false);
  assert.match(instance.find(node => node.props.role === 'alert').children.join(''), /未确认远程连接或任务停止/u);
  instance.testWith(async () => ({ status: 'connected', connectionId: 'new-connection', fingerprint: 'SHA256:synthetic' }));
  prepareRemote(instance);
  await button(instance, '测试连接').props.onClick();
  instance.render();
  send = async () => {};
  await instance.submit();
  assert.match(deliveries.at(-1), /new-connection/u);
  instance.unmount();
  assert.equal(instance.closes().length, 1, 'only the matching stale receipt was forgotten');

  // Neither error text nor unavailable/permission codes authorize local forgetting.
  for (const code of [undefined, 'connection_unavailable', 'permission_denied']) {
    instance = await remoteForm();
    instance.closeWith(async () => { throw Object.assign(new Error('unknown_receipt in untrusted error text'), { code }); });
    await instance.find(node => node.props.name === 'repository').props.onChange({ target: { value: '/other' } });
    instance.render();
    noForget(instance);
    instance.closeWith(async () => ({ status: 'closed' }));
    await button(instance, '重试断开远程连接').props.onClick();
    instance.unmount();
  }

  await unknownQueue();
  instance = await remoteForm({ connect: false });
  chooseForget(instance, 'synthetic-connection');
  confirmForget(instance);
  assert.equal(instance.find(node => node.props.name === 'repository').props.disabled, false,
    'an unknown receipt and its explicit recovery remain available after remount');
  instance.unmount();

  // Across remounts, stale unknown results cannot authorize a newer failed retry.
  await unknownQueue();
  const a = await remoteForm({ connect: false });
  const aClose = deferred();
  a.closeWith(() => aClose.promise);
  const aRetry = button(a, '重试断开远程连接').props.onClick();
  a.unmount();
  const b = await remoteForm({ connect: false });
  const bClose = deferred();
  b.closeWith(() => bClose.promise);
  const bRetry = button(b, '重试断开远程连接').props.onClick();
  b.unmount();
  const c = await remoteForm({ connect: false });
  aClose.resolve({ status: 'error', code: 'unknown_receipt' });
  await aRetry;
  c.render();
  noForget(c);
  bClose.reject(new Error('synthetic network error'));
  await bRetry;
  c.render();
  noForget(c);
  c.closeWith(async () => ({ status: 'error', code: 'unknown_receipt' }));
  await button(c, '重试断开远程连接').props.onClick();
  c.render();
  chooseForget(c, 'synthetic-connection');
  const staleConfirm = button(c, '确认放弃本地记录').props.onClick;
  const d = await remoteForm({ connect: false });
  d.closeWith(async () => ({ status: 'error', code: 'unknown_receipt' }));
  await button(d, '重试断开远程连接').props.onClick();
  staleConfirm();
  c.render();
  assert.equal(c.find(node => node.props.name === 'repository').props.disabled, true,
    'a fresh unknown response requires a fresh first confirmation step');
  chooseForget(c, 'synthetic-connection');
  confirmForget(c);
  c.unmount();
  d.unmount();

  // Even the latest unknown result cannot be forgotten while an older close is pending.
  await unknownQueue();
  const older = await remoteForm({ connect: false });
  const olderClose = deferred();
  older.closeWith(() => olderClose.promise);
  const olderRetry = button(older, '重试断开远程连接').props.onClick();
  older.unmount();
  const latest = await remoteForm({ connect: false });
  latest.closeWith(async () => ({ status: 'error', code: 'unknown_receipt' }));
  await button(latest, '重试断开远程连接').props.onClick();
  latest.render();
  noForget(latest);
  olderClose.resolve({ status: 'error', code: 'unknown_receipt' });
  await olderRetry;
  latest.render();
  chooseForget(latest, 'synthetic-connection');
  confirmForget(latest);
  latest.unmount();

  // Selecting one unknown ID never drops another ID or another session's cleanup.
  const other = await remoteForm({ sessionId: 'other-cleanup-session' });
  other.closeWith(async () => ({ status: 'error', code: 'unknown_receipt' }));
  await other.find(node => node.props.name === 'repository').props.onChange({ target: { value: '/other' } });
  other.unmount();
  await new Promise(resolve => setImmediate(resolve));
  instance = await remoteForm({ connect: false });
  prepareRemote(instance);
  const pair = [deferred(), deferred()];
  let pairIndex = 0;
  instance.testWith(() => pair[pairIndex++].promise);
  let closeIndex = 0;
  instance.closeWith(async () => ({ status: 'error', code: closeIndex++ === 0 ? 'unknown_receipt' : 'permission_denied' }));
  const pairHandler = button(instance, '测试连接').props.onClick;
  const pairAttempts = [pairHandler(), pairHandler()];
  instance.unmount();
  pair[0].resolve({ status: 'connected', connectionId: 'forget-only-this-id' });
  pair[1].resolve({ status: 'connected', connectionId: 'keep-this-id' });
  await Promise.all(pairAttempts);
  instance = await remoteForm({ connect: false });
  chooseForget(instance, 'forget-only-this-id');
  confirmForget(instance);
  assert.equal(instance.find(node => node.props.name === 'repository').props.disabled, true);
  noForget(instance);
  await button(instance, '重试断开远程连接').props.onClick();
  assert.deepEqual(instance.closes().map(request => request.connectionId), ['keep-this-id']);
  instance.unmount();
  const otherRecovery = await remoteForm({ connect: false, sessionId: 'other-cleanup-session' });
  assert.equal(otherRecovery.find(node => node.props.name === 'repository').props.disabled, true);
  await button(otherRecovery, '重试断开远程连接').props.onClick();
  assert.equal(otherRecovery.closes()[0].connectionId, 'synthetic-connection');
  otherRecovery.unmount();
  console.log('Form validation, prompt payload, native module and scoped Agent delivery verified.');
  console.log('Confirmed, rejected and ambiguous remote handoff, abandonment races and explicit disconnect verified.');
  console.log('Connection edits preserve receipts until confirmed close; retry, already-closed and unmount cleanup verified.');
  console.log('Session-scoped opaque cleanup receipts survive remounts and serialize distinct abandoned test connections.');
  console.log('Typed unknown receipts require fresh two-step local-only recovery; other failures, attempts, IDs and sessions remain isolated.');
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
