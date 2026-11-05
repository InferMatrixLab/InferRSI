const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { buildPrompt, taskFromForm } = require(process.argv[2]);

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
    window: { __ModuleLoader__: { load: ({ id, factory }) => {
      assert.equal(id, 'inferrsi-dsh');
      plugin = factory(name => {
        assert.equal(name, 'react');
        return {};
      });
    } } },
  });
  let registration;
  const deliveries = [];
  let running = false;
  const scope = { get: name => {
    assert.equal(name, 'conversation');
    return { send: async text => { deliveries.push(text); } };
  } };
  plugin.apply({
    slots: {
      inject: (key, callback) => {
        assert.equal(key, 'conversation.input.right');
        callback();
      },
      register: definition => { registration = definition; },
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
  await assert.rejects(submit('different-session', prompt));
  running = true;
  await assert.rejects(submit('target-session', prompt));
  assert.equal(deliveries.length, 1);
  console.log('Form validation, prompt payload, native module and scoped Agent delivery verified.');
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
