const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

async function main() {
  const events = new Map();
  const effects = [];
  const closed = [];
  let route;
  let tool;
  const manager = {
    test: async (options, { sessionId }) => {
      assert.equal(options.password, 'fake-test-password');
      assert.equal(sessionId, 'session-test');
      return { status: 'connected', connectionId: 'test-id' };
    },
    close: (sessionId, id) => {
      if (closed.length) throw new Error('connection_unavailable');
      closed.push({ sessionId, id });
    },
    closeSession: () => {}, dispose: () => {},
    run: async sessionId => ({ status: 'ok', owner: sessionId }),
  };
  const module = { exports: {} };
  vm.runInNewContext(fs.readFileSync(process.argv[2], 'utf8'), {
    module, require: name => {
      assert.equal(name, './remote.cjs');
      return { createRemoteManager: () => manager };
    },
    AbortController, AbortSignal, Response, Buffer,
  });
  module.exports.installRemote({
    effect: factory => effects.push(factory()),
    on: (event, callback) => events.set(event, callback),
    connection: { fetch: { register: value => { route = value; } } },
    tools: { register: value => { tool = value; } },
  }, 'unused-runtime');
  assert.equal(route.path, '/api/inferrsi/connection');
  assert.equal(route.requestBody, 'buffered');
  const controller = new AbortController();
  const response = await route.fetch(new Request('http://localhost/api/inferrsi/connection', {
    method: 'POST', body: JSON.stringify({ action: 'test', sessionId: 'session-test',
      options: { password: 'fake-test-password' } }), signal: controller.signal,
  }));
  const result = await response.json();
  assert.equal(result.connectionId, 'test-id');
  assert.ok(!JSON.stringify(result).includes('fake-test-password'));
  await tool.execute({ operation: 'close', connectionId: 'test-id' }, { agent: { id: 'session-test' } });
  controller.abort();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(closed.length, 1);
  await assert.rejects(tool.execute({ operation: 'read', connectionId: 'test-id' }, {}));
  const value = await tool.execute({ operation: 'read', connectionId: 'test-id' }, {
    agent: { id: 'session-test' }, signal: new AbortController().signal,
  });
  assert.equal(value.owner, 'session-test');
  events.get('agent/disposed')({ agent: { id: 'session-test' } });
  await Promise.all(effects.map(dispose => dispose()));
  console.log('Owner connection response, scoped tool and idempotent abort cleanup verified.');
}

main().catch(error => { console.error(error); process.exitCode = 1; });
