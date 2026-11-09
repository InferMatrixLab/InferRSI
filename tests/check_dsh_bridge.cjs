const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

async function main() {
  const events = new Map();
  const effects = [];
  const connections = new Map();
  const closedReceipts = new Map();
  const closed = [];
  const disposedSessions = [];
  let nextId = 0;
  let route;
  let tool;
  let abortAtReady;
  let pendingStarted;
  let disposed = false;
  let closeFails = false;
  function owned(sessionId, id) {
    if (connections.get(id) !== sessionId) throw Object.assign(
      new Error('connection_unavailable'), { code: 'connection_unavailable' });
  }
  const manager = {
    test: async (options, { sessionId, signal }) => {
      assert.equal(options.password, 'fake-test-password');
      if (options.waitForAbort) {
        pendingStarted();
        await new Promise((resolve, reject) => {
          const cancel = () => reject(Object.assign(new Error('cancelled'), { code: 'cancelled' }));
          if (signal.aborted) cancel();
          else signal.addEventListener('abort', cancel, { once: true });
        });
      }
      const connectionId = 'test-id-' + ++nextId;
      connections.set(connectionId, sessionId);
      abortAtReady?.();
      return { status: 'connected', connectionId };
    },
    close: (sessionId, id) => {
      if (!connections.has(id) && !closedReceipts.has(id)) throw Object.assign(
        new Error('unknown_receipt'), { code: 'unknown_receipt' });
      if (closedReceipts.has(id) && closedReceipts.get(id) === sessionId) {
        return { status: 'already_closed' };
      }
      owned(sessionId, id);
      if (closeFails) throw new Error('synthetic teardown failure');
      connections.delete(id);
      closedReceipts.set(id, sessionId);
      closed.push({ sessionId, id });
      return { status: 'closed' };
    },
    closeSession: sessionId => {
      disposedSessions.push(sessionId);
      for (const [id, owner] of connections) if (owner === sessionId) connections.delete(id);
      for (const [id, owner] of closedReceipts) if (owner === sessionId) closedReceipts.delete(id);
    },
    dispose: () => { disposed = true; connections.clear(); closedReceipts.clear(); },
    run: async (sessionId, id, args) => {
      owned(sessionId, id);
      return { status: 'ok', owner: sessionId, maxMinutes: args.maxMinutes };
    },
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
  assert.equal(tool.parameters.properties.maxMinutes.type, 'number');
  assert.equal(tool.parameters.properties.maxMinutes.exclusiveMinimum, 0);
  assert.equal(tool.parameters.properties.maxMinutes.maximum, 10080);
  const request = (body, signal) => route.fetch(new Request('http://localhost/api/inferrsi/connection', {
    method: 'POST', body: JSON.stringify(body), signal,
  }));
  const test = (sessionId, signal, options = {}) => request({ action: 'test', sessionId,
    options: { password: 'fake-test-password', ...options } }, signal);
  const context = id => ({ agent: { id }, signal: new AbortController().signal });

  // HTTP request cancellation owns only a pending test, not its returned receipt.
  const controller = new AbortController();
  const response = await test('session-test', controller.signal);
  const result = await response.json();
  assert.equal(result.status, 'connected');
  assert.ok(!JSON.stringify(result).includes('fake-test-password'));
  controller.abort();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(closed.length, 0);
  const value = await tool.execute({ operation: 'read', connectionId: result.connectionId,
    maxMinutes: 2.5 }, context('session-test'));
  assert.equal(value.owner, 'session-test');
  assert.equal(value.maxMinutes, 2.5);

  // The owner selects a session on the route; tools use the actual executing Agent id.
  await assert.rejects(tool.execute({ operation: 'read', connectionId: result.connectionId }, {}));
  await assert.rejects(tool.execute({ operation: 'read', connectionId: result.connectionId,
    sessionId: 'session-test' }, context('another-session')), error => error.code === 'connection_unavailable');
  await assert.rejects(tool.execute({ operation: 'close', connectionId: result.connectionId },
    context('another-session')), error => error.code === 'connection_unavailable');
  const wrongClose = await request({ action: 'close', sessionId: 'another-session',
    connectionId: result.connectionId });
  assert.equal(wrongClose.status, 400);
  assert.equal((await wrongClose.json()).code, 'connection_unavailable');
  assert.equal(connections.get(result.connectionId), 'session-test');
  assert.equal((await tool.execute({ operation: 'close', connectionId: result.connectionId },
    context('session-test'))).status, 'closed');
  assert.equal(closed.length, 1);
  const repeatedClose = await request({ action: 'close', sessionId: 'session-test',
    connectionId: result.connectionId });
  assert.equal(repeatedClose.status, 200);
  assert.equal((await repeatedClose.json()).status, 'already_closed');
  assert.equal((await tool.execute({ operation: 'close', connectionId: result.connectionId },
    context('session-test'))).status, 'already_closed');
  for (const [sessionId, connectionId, code] of [
    ['another-session', result.connectionId, 'connection_unavailable'],
    ['session-test', 'unknown-receipt', 'unknown_receipt']]) {
    const rejected = await request({ action: 'close', sessionId, connectionId });
    assert.equal(rejected.status, 400);
    assert.equal((await rejected.json()).code, code);
    await assert.rejects(tool.execute({ operation: 'close', connectionId }, context(sessionId)),
      error => error.code === code);
  }

  const pendingController = new AbortController();
  const started = new Promise(resolve => { pendingStarted = resolve; });
  const pendingResponse = test('session-test', pendingController.signal, { waitForAbort: true });
  await started;
  pendingController.abort();
  const cancelled = await pendingResponse;
  assert.equal(cancelled.status, 400);
  assert.equal((await cancelled.json()).code, 'cancelled');
  assert.equal(connections.size, 0);

  // If cancellation wins at the result boundary, discard the unreturned receipt.
  const racingController = new AbortController();
  abortAtReady = () => racingController.abort();
  const racing = await test('session-test', racingController.signal);
  abortAtReady = undefined;
  assert.equal(racing.status, 400);
  assert.equal(connections.size, 0);
  assert.equal(closed.length, 2);

  // A real teardown failure stays an error; the same receipt can be retried.
  const retry = await (await test('session-retry')).json();
  closeFails = true;
  const failedClose = await request({ action: 'close', sessionId: 'session-retry',
    connectionId: retry.connectionId });
  assert.equal(failedClose.status, 400);
  assert.equal((await failedClose.json()).code, 'connection_failed');
  assert.equal(connections.get(retry.connectionId), 'session-retry');
  assert.ok(!closedReceipts.has(retry.connectionId));
  await assert.rejects(tool.execute({ operation: 'close', connectionId: retry.connectionId },
    context('session-retry')), /synthetic teardown failure/);
  closeFails = false;
  const retried = await request({ action: 'close', sessionId: 'session-retry',
    connectionId: retry.connectionId });
  assert.equal(retried.status, 200);
  assert.equal((await retried.json()).status, 'closed');

  // Agent/session disposal and plugin unload still own established connections.
  const agentConnection = await (await test('session-agent')).json();
  const sessionConnection = await (await test('session-log')).json();
  events.get('agent/disposed')({ agent: { id: 'session-agent' } });
  events.get('session/disposed')({ id: 'session-log' });
  await new Promise(resolve => setImmediate(resolve));
  assert.ok(disposedSessions.includes('session-agent'));
  assert.ok(disposedSessions.includes('session-log'));
  assert.ok(!connections.has(agentConnection.connectionId));
  assert.ok(!connections.has(sessionConnection.connectionId));
  await assert.rejects(tool.execute({ operation: 'close', connectionId: agentConnection.connectionId },
    context('session-agent')), error => error.code === 'unknown_receipt');
  const expiredClose = await request({ action: 'close', sessionId: 'session-agent',
    connectionId: agentConnection.connectionId });
  assert.equal(expiredClose.status, 400);
  assert.equal((await expiredClose.json()).code, 'unknown_receipt');
  await test('session-unload');
  await Promise.all(effects.map(dispose => dispose()));
  assert.equal(disposed, true);
  assert.equal(connections.size, 0);
  assert.equal(closedReceipts.size, 0);
  console.log('HTTP test lifetime, owner-scoped close confirmation, retry and disposal verified.');
}

main().catch(error => { console.error(error); process.exitCode = 1; });
