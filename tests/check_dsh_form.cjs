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
  instance.find = predicate => {
    function visit(node) {
      if (!node || typeof node !== 'object') return undefined;
      if (predicate(node)) return node;
      for (const child of node.children.flat(Infinity)) {
        const found = visit(child);
        if (found) return found;
      }
    }
    const result = visit(instance.tree);
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
  vm.runInNewContext(fs.readFileSync(process.argv[3], 'utf8'), {
    AbortController,
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

  async function remoteForm() {
    const requests = [];
    let closeFails = false;
    const instance = mount(Action, {
      sessionId: 'target-session', submitPrompt: submit,
      useSession: selector => selector({ running: false, removed: false, openState: 'open', pendingSubmissions: [] }),
      useSessions: selector => selector({ byId: { 'target-session': { cwd: '/workspace/example' } } }),
      useAccess: () => true,
      remoteRequest: async request => {
        requests.push(request);
        if (request.action === 'close') {
          if (closeFails) throw new Error('synthetic close failure');
          return { status: 'closed' };
        }
        return { status: 'connected', connectionId: 'synthetic-connection', fingerprint: 'SHA256:synthetic' };
      },
    });
    function field(name, value) {
      instance.find(node => node.props.name === name).props.onChange({ target: { value } });
      instance.render();
    }
    field('execution', 'remote');
    for (const [name, value] of Object.entries({ ...form, execution: 'remote', repository: '/workspace/example' })) {
      if (!['constraints', 'execution'].includes(name)) field(name, value);
    }
    await instance.find(node => node.type === 'button' && node.children.includes('测试连接')).props.onClick();
    instance.render();
    instance.submit = () => instance.find(node => node.type === 'form').props.onSubmit({ preventDefault() {} });
    instance.closes = () => requests.filter(request => request.action === 'close');
    instance.tests = () => requests.filter(request => request.action === 'test');
    instance.failClose = value => { closeFails = value; };
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
  console.log('Form validation, prompt payload, native module and scoped Agent delivery verified.');
  console.log('Confirmed, rejected and ambiguous remote handoff, abandonment races and explicit disconnect verified.');
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
