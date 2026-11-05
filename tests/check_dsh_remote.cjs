const assert = require('node:assert/strict');
const { createHash, generateKeyPairSync } = require('node:crypto');
const { mkdtemp, mkdir, writeFile, rm } = require('node:fs/promises');
const http = require('node:http');
const { spawnSync } = require('node:child_process');
const net = require('node:net');
const os = require('node:os');
const path = require('node:path');
const { createRemoteManager } = require('../plugins/inferrsi-dsh/remote.cjs');
const { Client, Server, utils } = require('../plugins/inferrsi-dsh/vendor/ssh2.cjs');

const fakePassword = 'fake-password-with-no-service-access';
const hostKey = generateKeyPairSync('rsa', { modulusLength: 2048 }).privateKey
  .export({ type: 'pkcs1', format: 'pem' });
const userKey = generateKeyPairSync('rsa', { modulusLength: 2048 }).privateKey
  .export({ type: 'pkcs1', format: 'pem' });
const fingerprint = 'SHA256:' + createHash('sha256').update(utils.parseKey(hostKey).getPublicSSH())
  .digest('base64').replace(/=+$/u, '');
const status = utils.sftp.STATUS_CODE;
const root = '/workspace/repository';
const files = new Map([
  [root, { directory: true }],
  [root + '/bench.py', { content: Buffer.from('print("benchmark")\n') }],
  [root + '/quality.sh', { content: Buffer.from('exit 0\n') }],
  [root + '/source.py', { content: Buffer.from('original\n'), mode: 0o100755 }],
  [root + '/outside', { symlink: '/private' }],
  [root + '/campaign', { directory: true }],
  ['/private', { directory: true }],
  ['/private/secret.txt', { content: Buffer.from('unrelated private fixture') }],
]);
let authentications = 0;
let delayPlatform = false;
let delayDashboard = false;
let waitingChannel;
const commands = [];
const payloads = [];
const peers = new Set();

function operationClock() {
  let now = 0;
  const pending = new Set();
  return {
    timers: {
      setTimeout(callback, delay) {
        const timer = { callback, deadline: now + delay };
        pending.add(timer);
        return timer;
      },
      clearTimeout(timer) { pending.delete(timer); },
    },
    advance(milliseconds) {
      now += milliseconds;
      for (const timer of [...pending]) {
        if (timer.deadline <= now) {
          pending.delete(timer);
          timer.callback();
        }
      }
    },
  };
}

function resolved(filename) {
  let value = path.posix.normalize(filename);
  for (const [name, file] of files) {
    if (file.symlink && (value === name || value.startsWith(name + '/'))) {
      value = file.symlink + value.slice(name.length);
    }
  }
  return value;
}

function attributes(file) {
  return { mode: file.mode || (file.directory ? 0o40755 : file.symlink ? 0o120777 : 0o100644),
    size: file.content?.length || 0, uid: 0, gid: 0, atime: 1, mtime: 1 };
}

function serveSftp(sftp) {
  let nextHandle = 1;
  const handles = new Map();
  function handle(id, value) {
    const token = Buffer.from(String(nextHandle++));
    handles.set(token.toString(), value);
    sftp.handle(id, token);
  }
  sftp.on('REALPATH', (id, filename) => {
    const real = resolved(filename);
    if (!files.has(real)) return sftp.status(id, status.NO_SUCH_FILE);
    sftp.name(id, [{ filename: real, attrs: attributes(files.get(real)) }]);
  });
  sftp.on('STAT', (id, filename) => {
    const file = files.get(resolved(filename));
    if (!file) return sftp.status(id, status.NO_SUCH_FILE);
    sftp.attrs(id, attributes(file));
  });
  sftp.on('OPENDIR', (id, filename) => handle(id, { directory: resolved(filename), done: false }));
  sftp.on('READDIR', (id, token) => {
    const value = handles.get(token.toString());
    if (value.done) return sftp.status(id, status.EOF);
    value.done = true;
    const entries = [...files].filter(([filename]) => path.posix.dirname(filename) === value.directory)
      .map(([filename, file]) => ({ filename: path.posix.basename(filename), attrs: attributes(file) }));
    sftp.name(id, entries);
  });
  sftp.on('OPEN', (id, filename, flags, attrs) => {
    const real = resolved(filename);
    if ((flags & utils.sftp.OPEN_MODE.CREAT) !== 0) {
      if (files.has(real)) return sftp.status(id, status.FAILURE);
      files.set(real, { content: Buffer.alloc(0), mode: 0o100000 | (attrs.mode & 0o700) });
    }
    if (!files.has(real)) return sftp.status(id, status.NO_SUCH_FILE);
    handle(id, { filename: real });
  });
  sftp.on('READ', (id, token, offset, length) => {
    const buffer = files.get(handles.get(token.toString()).filename).content;
    if (offset >= buffer.length) return sftp.status(id, status.EOF);
    sftp.data(id, buffer.subarray(offset, offset + length));
  });
  sftp.on('WRITE', (id, token, offset, data) => {
    const file = files.get(handles.get(token.toString()).filename);
    const replacement = Buffer.alloc(Math.max(file.content.length, offset + data.length));
    file.content.copy(replacement);
    data.copy(replacement, offset);
    file.content = replacement;
    sftp.status(id, status.OK);
  });
  sftp.on('FSETSTAT', (id, token, attrs) => {
    if (attrs.mode !== undefined) files.get(handles.get(token.toString()).filename).mode = 0o100000 | attrs.mode;
    sftp.status(id, status.OK);
  });
  sftp.on('CLOSE', (id, token) => {
    handles.delete(token.toString());
    sftp.status(id, status.OK);
  });
  sftp.on('RENAME', (id, oldPath, newPath) => {
    files.set(newPath, files.get(oldPath));
    files.delete(oldPath);
    sftp.status(id, status.OK);
  });
  sftp.on('REMOVE', (id, filename) => {
    files.delete(filename);
    sftp.status(id, status.OK);
  });
}

const dashboardServer = http.createServer((request, response) => {
  response.setHeader('Content-Type', 'application/json');
  response.end(JSON.stringify({ dashboard: true, path: request.url }));
});

async function main() {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'inferrsi-remote-check-'));
  const runtimeDir = path.join(directory, 'runtime');
  await mkdir(runtimeDir);
  await writeFile(path.join(directory, 'remote-runtime.zip'), Buffer.from('synthetic-runtime-archive'));
  await new Promise(resolve => dashboardServer.listen(0, '127.0.0.1', resolve));
  const server = new Server({ hostKeys: [hostKey] }, client => {
    peers.add(client);
    client.on('error', () => {});
    client.once('close', () => peers.delete(client));
    client.on('authentication', context => {
      authentications++;
      if (context.method === 'password' && context.password === fakePassword) context.accept();
      else if (context.method === 'publickey' &&
          context.key.data.equals(utils.parseKey(userKey).getPublicSSH())) context.accept();
      else context.reject();
    });
    client.on('ready', () => {
      client.on('session', accept => {
        const session = accept();
        session.on('sftp', acceptSftp => serveSftp(acceptSftp()));
        session.on('exec', (acceptExec, reject, info) => {
          commands.push(info.command);
          const channel = acceptExec();
          if (info.command === 'uname -s') {
            if (delayPlatform) return;
            channel.write('Linux\n');
            channel.exit(0);
            channel.end();
            return;
          }
          assert.ok(info.command.startsWith("python3 -I -u -c '"));
          let text = '';
          channel.on('data', chunk => { text += chunk.toString('utf8'); });
          channel.on('end', () => {
            const payload = JSON.parse(text);
            payloads.push(payload);
            if (payload.args?.[0] === 'dashboard') {
              if (delayDashboard) return;
              channel.write(JSON.stringify({ dashboard: `http://127.0.0.1:${dashboardServer.address().port}/` }) + '\n');
              return;
            }
            if (payload.args?.includes('wait-for-check')) {
              waitingChannel = channel;
              return;
            }
            channel.write(JSON.stringify({ mode: payload.mode, args: payload.args }) + '\n');
            channel.exit(0);
            channel.end();
          });
        });
      });
      client.on('tcpip', (accept, reject, info) => {
        assert.equal(info.destIP, '127.0.0.1');
        assert.equal(info.destPort, dashboardServer.address().port);
        const remote = accept();
        const local = net.connect(info.destPort, info.destIP);
        local.on('error', () => remote.close());
        remote.on('error', () => local.destroy());
        local.once('close', () => remote.close());
        remote.once('close', () => local.destroy());
        remote.pipe(local).pipe(remote);
      });
    });
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const clock = operationClock();
  let holdNextClose = false;
  let controlledChannel;
  let deferredClose;
  class ControlledClient extends Client {
    exec(command, callback) {
      return super.exec(command, (error, channel) => {
        if (channel && holdNextClose && command !== 'uname -s') {
          holdNextClose = false;
          controlledChannel = channel;
          const close = channel.close.bind(channel);
          channel.close = () => { deferredClose = close; return channel; };
        }
        callback(error, channel);
      });
    }
  }
  const manager = createRemoteManager({ runtimeDir, Client: ControlledClient, timers: clock.timers });
  const options = { host: '127.0.0.1', port: server.address().port, user: 'synthetic-user',
    authType: 'password', password: fakePassword, repository: root,
    benchmark: 'bench.py', quality: 'quality.sh' };
  const sessionId = 'synthetic-session';
  try {
    if (process.argv.includes('--serve')) {
      const keyFile = path.join(directory, 'synthetic-user-key.pem');
      await writeFile(keyFile, userKey, { mode: 0o600 });
      console.log(JSON.stringify({ host: options.host, port: options.port, user: options.user,
        password: fakePassword, repository: root, fingerprint, keyFile }));
      await new Promise(resolve => {
        process.once('SIGINT', resolve);
        process.once('SIGTERM', resolve);
      });
      return;
    }
    assert.deepEqual(await manager.test(options, { sessionId }), { status: 'verify_host', fingerprint });
    assert.equal(authentications, 0, 'an untrusted host received authentication');
    await assert.rejects(manager.test({ ...options, fingerprint: 'SHA256:' + 'A'.repeat(43) }, { sessionId }),
      error => error.code === 'host_key_mismatch' && !error.message.includes(fakePassword));
    assert.equal(authentications, 0, 'a mismatched host received authentication');
    const connected = await manager.test({ ...options, fingerprint }, { sessionId });
    assert.equal(connected.status, 'connected');
    const id = connected.connectionId;
    await assert.rejects(manager.run('another-session', id, { operation: 'list' }),
      error => error.code === 'connection_unavailable');
    const listing = await manager.run(sessionId, id, { operation: 'list' });
    assert.ok(listing.entries.some(item => item.name === 'source.py'));
    assert.equal((await manager.run(sessionId, id, { operation: 'read', path: 'source.py' })).content, 'original\n');
    await manager.run(sessionId, id, { operation: 'write', path: 'source.py', content: 'replacement\n' });
    assert.equal(files.get(root + '/source.py').mode & 0o777, 0o755);
    assert.equal((await manager.run(sessionId, id, { operation: 'read', path: 'source.py' })).content, 'replacement\n');
    for (const escaped of ['../private/secret.txt', '/private/secret.txt', 'outside/secret.txt']) {
      for (const operation of ['read', 'write']) {
        await assert.rejects(manager.run(sessionId, id, { operation, path: escaped, content: 'blocked' }),
          error => error.code === 'path_outside_repository');
      }
    }
    assert.equal(files.get('/private/secret.txt').content.toString(), 'unrelated private fixture');
    await assert.rejects(manager.run(sessionId, id, { operation: 'run_script', script: 'arbitrary.py', maxMinutes: 1 }),
      error => error.code === 'script_unconfigured');
    await assert.rejects(manager.run(sessionId, id, { operation: 'run_script', script: 'benchmark' }),
      error => error.code === 'missing_budget');
    for (const maxMinutes of [null, 0, -1, Infinity, NaN, '3', true, 10081]) {
      await assert.rejects(manager.run(sessionId, id, { operation: 'run_script', script: 'benchmark', maxMinutes }),
        error => error.code === 'invalid_budget');
    }
    const injection = "literal'; exit 9; #";
    const script = await manager.run(sessionId, id, { operation: 'run_script', script: 'benchmark', maxMinutes: 1, args: [injection] });
    assert.equal(script.exitCode, 0);
    assert.equal(payloads.at(-1).script, root + '/bench.py');
    assert.deepEqual(payloads.at(-1).args, [injection]);
    const bootstrap = commands.at(-1).slice("python3 -I -u -c '".length, -1).replaceAll("'\\''", "'");
    const compilation = spawnSync('python', ['-I', '-c',
      'import sys; compile(sys.stdin.read(), "remote-bootstrap", "exec")'], { input: bootstrap, encoding: 'utf8' });
    assert.equal(compilation.status, 0, 'Remote Python bootstrap did not compile');
    await manager.run(sessionId, id, { operation: 'cli', args: ['collect', 'synthetic', '--limit', '1'] });
    assert.equal(Buffer.from(payloads.at(-1).archive, 'base64').toString(), 'synthetic-runtime-archive');
    assert.ok(commands.every(command => command === 'uname -s' || command === commands.find(item => item !== 'uname -s')),
      'user data changed the SSH shell command');
    assert.ok(!JSON.stringify(payloads).includes(fakePassword));
    assert.ok(!JSON.stringify(commands).includes(fakePassword));
    await manager.run(sessionId, id, { operation: 'cli', args: ['--help'] });
    await manager.run(sessionId, id, { operation: 'cli', args: ['--version'] });
    await assert.rejects(manager.run(sessionId, id, { operation: 'cli', args: ['run'] }),
      error => error.code === 'missing_budget');
    const waiting = manager.run(sessionId, id, { operation: 'run_script', script: 'benchmark', maxMinutes: 3, args: ['wait-for-check'] });
    waiting.catch(() => {});
    while (!waitingChannel) await new Promise(resolve => setTimeout(resolve, 5));
    let finished = false;
    waiting.finally(() => { finished = true; });
    const view = await manager.run(sessionId, id, { operation: 'dashboard' });
    assert.match(view.url, /^http:\/\/127\.0\.0\.1:\d+\/$/u);
    assert.equal((await (await fetch(view.url + 'api/state')).json()).dashboard, true);
    assert.equal((await manager.run(sessionId, id, { operation: 'dashboard' })).url, view.url);
    clock.advance(120001);
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(finished, false, 'the script was still capped at the old two-minute timeout');
    assert.equal((await (await fetch(view.url + 'api/state')).json()).dashboard, true);
    await assert.rejects(manager.run(sessionId, id, { operation: 'write', path: 'source.py', content: 'blocked' }),
      error => error.code === 'connection_busy');
    delayDashboard = true;
    const dashboardAbort = new AbortController();
    const cancelledDashboard = manager.run(sessionId, id, { operation: 'dashboard', path: 'campaign' }, dashboardAbort.signal);
    setTimeout(() => dashboardAbort.abort(), 50);
    await assert.rejects(cancelledDashboard, error => error.code === 'cancelled');
    waitingChannel.write('completed\n');
    waitingChannel.exit(0);
    waitingChannel.end();
    assert.equal((await waiting).exitCode, 0, 'cancelling dashboard interrupted the benchmark');
    delayDashboard = false;
    const finalView = await manager.run(sessionId, id, { operation: 'dashboard' });
    async function pendingCommand(request, signal) {
      waitingChannel = null;
      const result = manager.run(sessionId, id, request, signal);
      result.catch(() => {});
      while (!waitingChannel) await new Promise(resolve => setTimeout(resolve, 5));
      return { result, closed: new Promise(resolve => waitingChannel.once('close', resolve)) };
    }
    const longCli = await pendingCommand({ operation: 'cli', args: ['collect', 'wait-for-check'], maxMinutes: 3 });
    clock.advance(120001);
    waitingChannel.write('completed\n');
    waitingChannel.exit(0);
    waitingChannel.end();
    assert.equal((await longCli.result).exitCode, 0, 'the explicit CLI budget was ignored');
    for (const [request, deadline] of [
      [{ operation: 'run_script', script: 'benchmark', maxMinutes: 1, args: ['wait-for-check'] }, 60000],
      [{ operation: 'cli', args: ['run', '--max-minutes', '3', 'wait-for-check'], maxMinutes: 1 }, 60000],
      [{ operation: 'cli', args: ['run', '--max-minutes=1', 'wait-for-check'], maxMinutes: 3 }, 90000],
      [{ operation: 'cli', args: ['run', '--max-minutes', '1', 'wait-for-check'] }, 90000],
    ]) {
      const timed = await pendingCommand(request);
      let expired = false;
      timed.result.catch(() => { expired = true; });
      clock.advance(deadline - 1);
      await new Promise(resolve => setImmediate(resolve));
      assert.equal(expired, false, 'the command ended before its selected deadline');
      clock.advance(1);
      await assert.rejects(timed.result, error => error.code === 'timeout');
      await timed.closed;
      await new Promise(resolve => setImmediate(resolve));
      assert.equal((await (await fetch(finalView.url + 'api/state')).json()).dashboard, true);
      assert.equal((await manager.run(sessionId, id, { operation: 'cli', args: ['--version'] })).exitCode, 0);
      assert.equal((await manager.run(sessionId, id, { operation: 'read', path: 'source.py' })).status, 'ok');
    }
    const commandAbort = new AbortController();
    const cancelledCommand = await pendingCommand({ operation: 'run_script', script: 'benchmark',
      maxMinutes: 3, args: ['wait-for-check'] }, commandAbort.signal);
    commandAbort.abort();
    await assert.rejects(cancelledCommand.result, error => error.code === 'cancelled');
    await cancelledCommand.closed;
    await new Promise(resolve => setImmediate(resolve));
    assert.equal((await (await fetch(finalView.url + 'api/state')).json()).dashboard, true);
    assert.equal((await manager.run(sessionId, id, { operation: 'cli', args: ['--version'] })).exitCode, 0);
    for (const timeoutFirst of [false, true]) {
      holdNextClose = true;
      deferredClose = null;
      const errored = await pendingCommand({ operation: 'run_script', script: 'benchmark',
        maxMinutes: 1, args: ['wait-for-check'] });
      const closed = new Promise(resolve => controlledChannel.once('close', resolve));
      if (timeoutFirst) {
        clock.advance(60000);
        await assert.rejects(errored.result, error => error.code === 'timeout');
      }
      controlledChannel.emit('error', new Error('synthetic channel failure'));
      await assert.rejects(errored.result,
        error => error.code === (timeoutFirst ? 'timeout' : 'execution_failed'));
      assert.equal(typeof deferredClose, 'function', 'the errored channel was not asked to close');
      await assert.rejects(manager.run(sessionId, id, { operation: 'read', path: 'source.py' }),
        error => error.code === 'connection_busy');
      assert.equal((await (await fetch(finalView.url + 'api/state')).json()).dashboard, true);
      deferredClose();
      await closed;
      assert.equal((await manager.run(sessionId, id, { operation: 'cli', args: ['--version'] })).exitCode, 0);
    }
    manager.closeSession(sessionId);
    await assert.rejects(manager.run(sessionId, id, { operation: 'list' }), error => error.code === 'connection_unavailable');
    await assert.rejects(fetch(finalView.url), 'disposed tunnel remained available');
    const keyed = await manager.test({ ...options, authType: 'key', privateKey: userKey, password: undefined,
      fingerprint }, { sessionId });
    assert.equal(keyed.status, 'connected');
    manager.close(sessionId, keyed.connectionId);
    delayPlatform = true;
    const aborter = new AbortController();
    const cancelled = manager.test({ ...options, fingerprint }, { sessionId, signal: aborter.signal });
    setTimeout(() => aborter.abort(), 150);
    await assert.rejects(cancelled, error => error.code === 'cancelled');
    console.log('DSH_REMOTE_CHECK_OK');
  } finally {
    manager.dispose();
    for (const peer of peers) peer.end();
    await new Promise(resolve => server.close(resolve));
    await new Promise(resolve => dashboardServer.close(resolve));
    assert.equal(path.dirname(directory), path.resolve(os.tmpdir()));
    await rm(directory, { recursive: true, force: true });
  }
}

main().catch(error => {
  console.error(error.name, error.code || 'check_failed');
  process.exitCode = 1;
});
