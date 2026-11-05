const { createRemoteManager } = require('./remote.cjs');

async function readBody(request) {
  const reader = request.body?.getReader();
  if (!reader) throw new Error('invalid_request');
  const parts = [];
  let size = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 192 * 1024) throw new Error('request_too_large');
      parts.push(Buffer.from(value));
    }
    return JSON.parse(Buffer.concat(parts).toString('utf8'));
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

function installRemote(ctx, runtimeDir) {
  const manager = createRemoteManager({ runtimeDir });
  const lifetime = new AbortController();
  const pending = new Set();
  function track(promise) {
    pending.add(promise);
    promise.finally(() => pending.delete(promise)).catch(() => {});
    return promise;
  }
  ctx.effect(() => async () => {
    lifetime.abort();
    await manager.dispose();
    await Promise.allSettled([...pending]);
  });
  ctx.on('agent/disposed', ({ agent }) => {
    track(Promise.resolve().then(() => manager.closeSession(agent.id))).catch(() => {});
  });
  ctx.on('session/disposed', session => {
    track(Promise.resolve().then(() => manager.closeSession(session.id))).catch(() => {});
  });
  ctx.connection.fetch.register({
    path: '/api/inferrsi/connection', methods: ['POST'], requestBody: 'buffered',
    fetch: request => track((async () => {
      try {
        const body = await readBody(request);
        // DSH admits only authenticated owner Peers to exact Fetch routes.
        // This is the owner's selected session, not a caller identity credential.
        if (typeof body.sessionId !== 'string' || body.sessionId.length > 256) {
          throw new Error('invalid_session');
        }
        const signal = AbortSignal.any([request.signal, lifetime.signal]);
        if (body.action === 'close') {
          const result = await manager.close(body.sessionId, body.connectionId);
          return Response.json(result, { headers: { 'Cache-Control': 'no-store' } });
        }
        if (body.action !== 'test') throw new Error('invalid_action');
        const result = await manager.test(body.options, { sessionId: body.sessionId, signal });
        if (result.connectionId && signal.aborted) {
          await manager.close(body.sessionId, result.connectionId);
          throw new Error('cancelled');
        }
        // A completed test transfers the connection to the session/plugin lifetime.
        // Later HTTP cancellation must not close that established connection.
        return Response.json(result, { headers: { 'Cache-Control': 'no-store' } });
      } catch (error) {
        return Response.json({ status: 'error', code: error.code || 'connection_failed',
          message: '连接未完成，请核对主机、认证和服务器指纹后重试。' },
        { status: 400, headers: { 'Cache-Control': 'no-store' } });
      }
    })()),
  });
  ctx.tools.register({
    name: 'inferrsi_remote',
    description: 'Operate on the SSH repository explicitly selected and tested in the InferRSI form. Credentials stay in the Host. Use cli for canonical InferRSI operations, dashboard for a local live-dashboard tunnel, list/read/write for scoped repository files, and run_script for the user-designated benchmark or quality script. run_script requires maxMinutes from the remaining task budget; cli accepts it optionally and cli run uses the smaller of it and --max-minutes. Fixed operations, not an execution sandbox: edited repository code and designated scripts run with the SSH user\'s permissions.',
    parameters: {
      type: 'object', additionalProperties: false,
      properties: {
        connectionId: { type: 'string' },
        operation: { type: 'string', enum: ['list', 'read', 'write', 'run_script', 'cli', 'dashboard', 'close'] },
        path: { type: 'string' }, content: { type: 'string' },
        args: { type: 'array', items: { type: 'string' } },
        script: { type: 'string', enum: ['benchmark', 'quality'] },
        maxMinutes: { type: 'number', exclusiveMinimum: 0, maximum: 10080 },
      },
      required: ['connectionId', 'operation'],
    },
    output: {
      schema: { type: 'object', additionalProperties: true },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value) }],
    },
    execute: (args, exec) => track((async () => {
      if (!exec.agent?.id) throw new Error('This connection requires its owning Agent session.');
      if (!args || typeof args.connectionId !== 'string' || typeof args.operation !== 'string') {
        throw new Error('Invalid remote operation.');
      }
      if (args.operation === 'close') {
        return manager.close(exec.agent.id, args.connectionId);
      }
      const signal = AbortSignal.any([exec.signal, lifetime.signal]);
      return manager.run(exec.agent.id, args.connectionId, args, signal);
    })()),
  });
}

module.exports = { installRemote };
