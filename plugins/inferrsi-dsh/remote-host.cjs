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
        if (typeof body.sessionId !== 'string' || body.sessionId.length > 256) {
          throw new Error('invalid_session');
        }
        const signal = AbortSignal.any([request.signal, lifetime.signal]);
        if (body.action === 'close') {
          await manager.close(body.sessionId, body.connectionId);
          return Response.json({ status: 'closed' }, { headers: { 'Cache-Control': 'no-store' } });
        }
        if (body.action !== 'test') throw new Error('invalid_action');
        const result = await manager.test(body.options, { sessionId: body.sessionId, signal });
        if (result.connectionId) {
          const sessionId = body.sessionId;
          const connectionId = result.connectionId;
          const close = () => {
            Promise.resolve().then(() => manager.close(sessionId, connectionId)).catch(() => {});
          };
          if (signal.aborted) {
            close();
            throw new Error('cancelled');
          }
          signal.addEventListener('abort', close, { once: true });
        }
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
    description: 'Operate on the SSH repository explicitly selected and tested in the InferRSI form. Credentials stay in the Host. Use cli for canonical InferRSI operations, dashboard for a local live-dashboard tunnel, list/read/write for scoped repository files, and run_script for the user-designated benchmark or quality script. No general shell commands.',
    parameters: {
      type: 'object', additionalProperties: false,
      properties: {
        connectionId: { type: 'string' },
        operation: { type: 'string', enum: ['list', 'read', 'write', 'run_script', 'cli', 'dashboard', 'close'] },
        path: { type: 'string' }, content: { type: 'string' },
        args: { type: 'array', items: { type: 'string' } },
        script: { type: 'string', enum: ['benchmark', 'quality'] },
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
        await manager.close(exec.agent.id, args.connectionId);
        return { status: 'closed' };
      }
      const signal = AbortSignal.any([exec.signal, lifetime.signal]);
      return manager.run(exec.agent.id, args.connectionId, args, signal);
    })()),
  });
}

module.exports = { installRemote };
