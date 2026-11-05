const { createHash, randomBytes, timingSafeEqual } = require('node:crypto');
const { readFile } = require('node:fs/promises');
const net = require('node:net');
const path = require('node:path');

const OUTPUT_LIMIT = 256 * 1024;
const FILE_LIMIT = 1024 * 1024;
const CHECK_TIMEOUT = 15000;
const BOOTSTRAP = String.raw`
import argparse, base64, io, json, os, shlex, signal, subprocess, sys, tempfile, zipfile
from pathlib import Path

child = None
def interrupted(signum, frame):
    raise KeyboardInterrupt()
for signum in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
    signal.signal(signum, interrupted)
try:
    payload = json.load(sys.stdin)
    root = os.path.realpath(payload['repository'])
    if root != payload['repository'] or not os.path.isdir(root):
        raise ValueError('repository changed')
    os.chdir(root)
    sys.dont_write_bytecode = True
    if payload['mode'] == 'script':
        script = os.path.realpath(payload['script'])
        if not script.startswith(root + '/') or not os.path.isfile(script):
            raise ValueError('script outside repository')
        interpreter = 'python3' if script.endswith('.py') else 'bash'
        child = subprocess.Popen([interpreter, script] + payload['args'], stdin=subprocess.DEVNULL,
                                 start_new_session=True)
        sys.exit(child.wait())
    with tempfile.TemporaryDirectory(prefix='inferrsi-runtime-') as directory:
        data = base64.b64decode(payload['archive'], validate=True)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
            if len(members) > 20000 or sum(item.file_size for item in members) > 134217728:
                raise ValueError('runtime archive exceeds limit')
            names = set()
            for item in members:
                name = item.filename
                parts = name.split('/')
                if (name in names or name.startswith('/') or '\\' in name or
                    any(part in ('', '.', '..') for part in parts) or
                    (parts[0] != 'inferrsi' and name != 'manifest.json') or
                    ((item.external_attr >> 16) & 0o170000) == 0o120000):
                    raise ValueError('invalid runtime archive')
                names.add(name)
            archive.extractall(directory)
        sys.path.insert(0, directory)
        from inferrsi.arguments import parser
        argument_parser = parser()
        def exact_options(current):
            current.allow_abbrev = False
            for action in current._actions:
                if isinstance(action, argparse._SubParsersAction):
                    for child_parser in action.choices.values():
                        exact_options(child_parser)
        exact_options(argument_parser)
        parsed = argument_parser.parse_args(payload['args'])
        path_fields = {'repo', 'candidate_repo', 'output_dir', 'directory', 'input', 'output',
                       'template', 'context_file', 'file', 'details_json', 'profile', 'store',
                       'skill_root', 'root', 'translations', 'agent_trace', 'optimization_trace'}
        for field, value in vars(parsed).items():
            if value is None or not (isinstance(value, Path) or field in path_fields):
                continue
            resolved = os.path.realpath(str(value))
            if resolved != root and not resolved.startswith(root + '/'):
                raise ValueError('path outside repository')
        if getattr(parsed, 'python', 'python3') not in ('python', 'python3', sys.executable):
            raise ValueError('unsupported interpreter')
        for field in ('baseline_command', 'candidate_command', 'validation_command'):
            command = getattr(parsed, field, None)
            if command is None:
                continue
            argv = shlex.split(command)
            if len(argv) < 2 or argv[0] not in ('python', 'python3', 'bash', 'sh'):
                raise ValueError('a repository script is required')
            baseline = getattr(parsed, 'repo', root)
            candidate = getattr(parsed, 'candidate_repo', None) or baseline
            cwd = baseline if field == 'baseline_command' else candidate
            script = os.path.realpath(os.path.join(cwd, argv[1]))
            if (argv[1].startswith('-') or not script.startswith(root + '/') or
                    not os.path.isfile(script)):
                raise ValueError('script outside repository')
        from inferrsi.cli import main
        sys.exit(main(payload['args']))
except KeyboardInterrupt:
    sys.exit(130)
except Exception:
    print('Remote operation failed.', file=sys.stderr)
    sys.exit(2)
finally:
    if child is not None and child.poll() is None:
        try:
            os.killpg(child.pid, signal.SIGTERM)
            child.wait(timeout=3)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
`;
const BOOTSTRAP_COMMAND = "python3 -I -u -c '" + BOOTSTRAP.replaceAll("'", "'\\''") + "'";

class RemoteError extends Error {
  constructor(code) {
    super(`Remote operation failed (${code}).`);
    this.name = 'RemoteError';
    this.code = code;
  }
}

function fail(code) {
  throw new RemoteError(code);
}

function checkedString(value, limit = 4096) {
  if (typeof value !== 'string' || value.length > limit || /[\0\r\n]/u.test(value)) {
    fail('invalid_input');
  }
  return value;
}

function checkedArgs(value = []) {
  if (!Array.isArray(value) || value.length > 128) fail('invalid_arguments');
  const args = value.map(item => checkedString(item));
  if (Buffer.byteLength(JSON.stringify(args)) > 65536) fail('invalid_arguments');
  return args;
}

function fingerprintOf(key) {
  return 'SHA256:' + createHash('sha256').update(key).digest('base64').replace(/=+$/u, '');
}

function expectedFingerprint(value) {
  if (!value) return null;
  checkedString(value, 80);
  if (!/^SHA256:[A-Za-z0-9+/]{43}=?$/u.test(value)) fail('invalid_fingerprint');
  return value.replace(/=+$/u, '');
}

function sameFingerprint(actual, expected) {
  const first = Buffer.from(actual);
  const second = Buffer.from(expected);
  return first.length === second.length && timingSafeEqual(first, second);
}

function io(target, method, ...args) {
  return new Promise((resolve, reject) => {
    target[method](...args, (error, value) => {
      if (error?.code === 1 && method === 'readdir') resolve(false);
      else if (error) reject(new RemoteError(error.code === 2 ? 'not_found' : 'remote_io'));
      else resolve(value);
    });
  });
}

function inside(root, candidate) {
  return candidate === root || candidate.startsWith(root + '/');
}

function scopedPath(root, value = '.') {
  checkedString(value);
  if (!value || value.includes('\\') || value.split('/').includes('..')) fail('path_outside_repository');
  const resolved = path.posix.resolve(root, value);
  if (!inside(root, resolved)) fail('path_outside_repository');
  return resolved;
}

async function canonicalPath(entry, value, create = false) {
  const candidate = scopedPath(entry.repository, value);
  if (create) {
    const parent = await io(entry.sftp, 'realpath', path.posix.dirname(candidate));
    if (!inside(entry.repository, parent)) fail('path_outside_repository');
    try {
      const real = await io(entry.sftp, 'realpath', candidate);
      if (!inside(entry.repository, real)) fail('path_outside_repository');
      return real;
    } catch (error) {
      if (error.code !== 'not_found') throw error;
      return path.posix.join(parent, path.posix.basename(candidate));
    }
  }
  const real = await io(entry.sftp, 'realpath', candidate);
  if (!inside(entry.repository, real)) fail('path_outside_repository');
  return real;
}

function clearCredentials(config) {
  for (const key of ['password', 'passphrase', 'privateKey']) {
    if (Buffer.isBuffer(config[key])) config[key].fill(0);
    config[key] = undefined;
  }
}

function createRemoteManager({
  runtimeDir = path.join(__dirname, 'runtime'), Client,
  timers = { setTimeout, clearTimeout },
} = {}) {
  const ClientClass = Client || require('./vendor/ssh2.cjs').Client;
  const connections = new Map();
  const closedReceipts = new Map();
  const pending = new Set();

  function closeDashboard(entry) {
    const dashboard = entry.dashboard;
    if (!dashboard || dashboard.closing) return;
    dashboard.closing = true;
    try {
      dashboard.server?.close();
      for (const socket of dashboard.sockets) socket.destroy();
      try { dashboard.channel?.signal('TERM'); } catch { /* The channel may already be closed. */ }
      dashboard.channel?.close();
      if (entry.dashboard === dashboard) entry.dashboard = null;
    } finally {
      dashboard.closing = false;
    }
  }

  function destroy(entry) {
    if (entry.destroyed || entry.destroying) return;
    entry.closed = true;
    entry.destroying = true;
    try {
      closeDashboard(entry);
      for (const channel of entry.channels) {
        try { channel.signal('TERM'); } catch { /* The SSH peer may already be gone. */ }
        channel.close();
      }
      entry.sftp?.end();
      entry.client.destroy();
      entry.destroyed = true;
      pending.delete(entry);
      // Keep only opaque, owner-scoped receipts after complete local teardown.
      // A failed teardown retains its entry so its owner can retry close.
      if (connections.delete(entry.id)) closedReceipts.set(entry.id, entry.sessionId);
    } finally {
      entry.destroying = false;
    }
  }

  async function bounded(entry, operation, signal, timeout = CHECK_TIMEOUT, cleanup = () => destroy(entry)) {
    if (entry.closed) fail('connection_closed');
    if (signal?.aborted) fail('cancelled');
    let timer;
    let abort;
    const controller = new AbortController();
    const cancelled = new Promise((resolve, reject) => {
      abort = () => {
        controller.abort();
        cleanup();
        reject(new RemoteError('cancelled'));
      };
      signal?.addEventListener('abort', abort, { once: true });
      timer = timers.setTimeout(() => {
        controller.abort();
        cleanup();
        reject(new RemoteError('timeout'));
      }, timeout);
    });
    try {
      return await Promise.race([operation(controller.signal), cancelled]);
    } catch (error) {
      throw error instanceof RemoteError ? error : new RemoteError('remote_io');
    } finally {
      timers.clearTimeout(timer);
      signal?.removeEventListener('abort', abort);
    }
  }

  function execute(entry, command, payload, signal, owner) {
    return new Promise((resolve, reject) => {
      if (signal?.aborted) return reject(new RemoteError('cancelled'));
      let channel;
      const abort = () => {
        if (!channel) return;
        try { channel.signal('TERM'); } catch { /* The command may already have exited. */ }
        channel.close();
      };
      const finished = () => {
        signal?.removeEventListener('abort', abort);
        if (owner) {
          owner.pending = false;
          if (entry.busy === owner) entry.busy = false;
        }
      };
      if (owner) owner.pending = true;
      signal?.addEventListener('abort', abort, { once: true });
      entry.client.exec(command, (error, opened) => {
        if (error) {
          finished();
          return reject(new RemoteError('execution_unavailable'));
        }
        channel = opened;
        entry.channels.add(channel);
        const stdout = [];
        const stderr = [];
        let bytes = 0;
        let truncated = false;
        const append = (target, chunk) => {
          const retained = chunk.subarray(0, Math.max(0, OUTPUT_LIMIT - bytes));
          if (retained.length) target.push(retained);
          bytes += retained.length;
          truncated ||= retained.length < chunk.length;
        };
        channel.on('data', chunk => append(stdout, chunk));
        channel.stderr.on('data', chunk => append(stderr, chunk));
        channel.once('error', () => {
          abort();
          reject(new RemoteError('execution_failed'));
        });
        channel.once('close', exitCode => {
          finished();
          entry.channels.delete(channel);
          if (!Number.isInteger(exitCode)) return reject(new RemoteError('execution_failed'));
          resolve({ status: 'ok', exitCode,
            stdout: Buffer.concat(stdout).toString('utf8'),
            stderr: Buffer.concat(stderr).toString('utf8'), truncated });
        });
        if (signal?.aborted || entry.closed) {
          abort();
          return;
        }
        channel.end(payload === undefined ? undefined : JSON.stringify(payload));
      });
    });
  }

  async function test(options, { sessionId, signal } = {}) {
    checkedString(sessionId, 256);
    if (!sessionId || !options || !net.isIP(options.host)) fail('invalid_connection');
    const port = Number(options.port === undefined || options.port === '' ? 22 : options.port);
    if (!Number.isInteger(port) || port < 1 || port > 65535) fail('invalid_connection');
    const username = checkedString(options.user, 128);
    const repository = checkedString(options.repository);
    if (!username || !repository.startsWith('/') || repository === '/' || repository.includes('\\') ||
        repository.split('/').includes('..')) fail('invalid_connection');
    const expected = expectedFingerprint(options.fingerprint);
    const config = { host: options.host, port, username, readyTimeout: CHECK_TIMEOUT,
      keepaliveInterval: 15000, keepaliveCountMax: 3 };
    if (options.authType === 'password') {
      if (!options.password) fail('missing_credentials');
      config.password = checkedString(options.password, 8192);
    } else if (options.authType === 'key') {
      if (typeof options.privateKey !== 'string' || !options.privateKey ||
          Buffer.byteLength(options.privateKey) > 65536) fail('missing_credentials');
      config.privateKey = Buffer.from(options.privateKey);
      if (options.passphrase) config.passphrase = checkedString(options.passphrase, 8192);
    } else fail('invalid_authentication');
    const entry = { id: randomBytes(24).toString('base64url'), sessionId,
      client: new ClientClass(), channels: new Set(), repository, closed: false,
      scripts: { benchmark: options.benchmark || '', quality: options.quality || '' } };
    pending.add(entry);
    let fingerprint;
    config.hostVerifier = key => {
      fingerprint = fingerprintOf(key);
      return expected !== null && sameFingerprint(fingerprint, expected);
    };
    const connected = () => new Promise((resolve, reject) => {
      entry.client.once('ready', resolve);
      entry.client.on('error', () => reject(new RemoteError('connection_failed')));
      entry.client.once('close', () => {
        destroy(entry);
        reject(new RemoteError('connection_closed'));
      });
      try { entry.client.connect(config); }
      catch { reject(new RemoteError('connection_failed')); }
    });
    try {
      try {
        await bounded(entry, connected, signal);
      } catch (error) {
        if (error.code === 'cancelled' || error.code === 'timeout') throw error;
        if (fingerprint && !expected) return { status: 'verify_host', fingerprint };
        if (fingerprint && expected && !sameFingerprint(fingerprint, expected)) fail('host_key_mismatch');
        throw error;
      } finally {
        clearCredentials(config);
        if (entry.client.config) clearCredentials(entry.client.config);
      }
      await bounded(entry, async () => {
        const platform = await execute(entry, 'uname -s');
        if (platform.exitCode !== 0 || platform.stdout.trim() !== 'Linux') fail('linux_required');
        entry.sftp = await io(entry.client, 'sftp');
        entry.sftp.on('error', () => destroy(entry));
        entry.repository = await io(entry.sftp, 'realpath', repository);
        if (entry.repository === '/' || !entry.repository.startsWith('/')) fail('repository_unavailable');
        const attributes = await io(entry.sftp, 'stat', entry.repository);
        if (!attributes.isDirectory()) fail('repository_unavailable');
      }, signal);
      connections.set(entry.id, entry);
      pending.delete(entry);
      return { status: 'connected', connectionId: entry.id, fingerprint };
    } finally {
      if (!connections.has(entry.id)) destroy(entry);
    }
  }

  function connection(sessionId, id) {
    const entry = connections.get(id);
    if (!entry || entry.sessionId !== sessionId || entry.closed) fail('connection_unavailable');
    return entry;
  }

  async function runtimePayload(entry, args) {
    let archive;
    try { archive = await readFile(path.join(runtimeDir, '..', 'remote-runtime.zip')); }
    catch { fail('runtime_unavailable'); }
    if (archive.length > 32 * 1024 * 1024) fail('runtime_unavailable');
    return { mode: 'cli', repository: entry.repository, args, archive: archive.toString('base64') };
  }

  async function dashboard(entry, request, signal, token) {
    const directory = await canonicalPath(entry, request.path || '.');
    if (signal.aborted || entry.closed) fail('cancelled');
    if (entry.dashboard?.directory === directory && entry.dashboard.url) {
      return { status: 'ok', url: entry.dashboard.url };
    }
    closeDashboard(entry);
    const payload = await runtimePayload(entry,
      ['dashboard', '--input', directory, '--live', '--port', '0']);
    if (signal.aborted || entry.closed) fail('cancelled');
    const view = { directory, sockets: new Set(), token };
    entry.dashboard = view;
    try {
      const remotePort = await new Promise((resolve, reject) => {
        entry.client.exec(BOOTSTRAP_COMMAND, (error, channel) => {
          if (error) return reject(new RemoteError('dashboard_unavailable'));
          if (signal.aborted || entry.closed || entry.dashboard !== view) {
            channel.close();
            return reject(new RemoteError('cancelled'));
          }
          view.channel = channel;
          entry.channels.add(channel);
          let text = '';
          let ready = false;
          channel.on('data', chunk => {
            if (ready || text.length > 65536) return;
            text += chunk.toString('utf8');
            if (text.length > 65536) return reject(new RemoteError('dashboard_unavailable'));
            for (const line of text.split('\n').slice(0, -1)) {
              try {
                const match = /^http:\/\/127\.0\.0\.1:([0-9]+)\/$/u.exec(JSON.parse(line).dashboard);
                if (match && Number(match[1]) > 0 && Number(match[1]) <= 65535) {
                  ready = true;
                  text = '';
                  resolve(Number(match[1]));
                  break;
                }
              } catch { /* Startup may emit a line before the dashboard URL. */ }
            }
          });
          channel.stderr.resume();
          channel.once('error', () => reject(new RemoteError('dashboard_unavailable')));
          channel.once('close', () => {
            entry.channels.delete(channel);
            if (entry.dashboard === view) closeDashboard(entry);
            reject(new RemoteError('dashboard_unavailable'));
          });
          channel.end(JSON.stringify(payload));
        });
      });
      if (signal.aborted || entry.closed || entry.dashboard !== view) fail('cancelled');
      view.server = net.createServer(socket => {
        view.sockets.add(socket);
        socket.on('error', () => socket.destroy());
        socket.once('close', () => view.sockets.delete(socket));
        entry.client.forwardOut('127.0.0.1', 0, '127.0.0.1', remotePort, (error, stream) => {
          if (error || socket.destroyed) {
            stream?.close();
            socket.destroy();
            return;
          }
          stream.on('error', () => socket.destroy());
          socket.once('close', () => stream.close());
          stream.once('close', () => socket.destroy());
          socket.pipe(stream).pipe(socket);
        });
      });
      await new Promise((resolve, reject) => {
        view.server.once('error', () => reject(new RemoteError('dashboard_unavailable')));
        view.server.listen({ port: 0, host: '127.0.0.1', signal }, resolve);
      });
      view.url = `http://127.0.0.1:${view.server.address().port}/`;
      return { status: 'ok', url: view.url };
    } catch (error) {
      if (entry.dashboard === view) closeDashboard(entry);
      throw error;
    }
  }

  async function perform(entry, request, signal, token) {
    if (!request || typeof request !== 'object') fail('invalid_operation');
    if (request.operation === 'dashboard') return dashboard(entry, request, signal, token);
    if (request.operation === 'list') {
      const directory = await canonicalPath(entry, request.path || '.');
      const handle = await io(entry.sftp, 'opendir', directory);
      const entries = [];
      try {
        while (entries.length <= 500) {
          const batch = await io(entry.sftp, 'readdir', handle);
          if (!batch) break;
          entries.push(...batch.slice(0, 501 - entries.length));
        }
      } finally { await io(entry.sftp, 'close', handle); }
      return { status: 'ok', entries: entries.slice(0, 500).map(item => ({ name: item.filename,
        directory: item.attrs.isDirectory(), symlink: item.attrs.isSymbolicLink(), size: item.attrs.size })),
      truncated: entries.length > 500 };
    }
    if (request.operation === 'read') {
      const file = await canonicalPath(entry, request.path);
      const attributes = await io(entry.sftp, 'stat', file);
      if (!attributes.isFile() || attributes.size > FILE_LIMIT) fail('file_limit');
      const handle = await io(entry.sftp, 'open', file, 'r');
      try {
        const buffer = Buffer.alloc(FILE_LIMIT + 1);
        let offset = 0;
        while (offset < buffer.length) {
          const length = await new Promise((resolve, reject) => {
            entry.sftp.read(handle, buffer, offset, buffer.length - offset, offset,
              (error, count) => error && error.code !== 1 ? reject(new RemoteError('remote_io')) : resolve(count || 0));
          });
          if (!length) break;
          offset += length;
        }
        if (offset > FILE_LIMIT) fail('file_limit');
        return { status: 'ok', content: buffer.subarray(0, offset).toString('utf8') };
      } finally { await io(entry.sftp, 'close', handle); }
    }
    if (request.operation === 'write') {
      if (typeof request.content !== 'string' || Buffer.byteLength(request.content) > FILE_LIMIT) fail('file_limit');
      const file = await canonicalPath(entry, request.path, true);
      let mode = 0o600;
      try {
        const attributes = await io(entry.sftp, 'stat', file);
        if (!attributes.isFile()) fail('not_regular_file');
        mode = attributes.mode & 0o777;
      } catch (error) {
        if (error.code !== 'not_found') throw error;
      }
      const temporary = path.posix.join(path.posix.dirname(file), '.inferrsi-' + randomBytes(12).toString('hex'));
      const handle = await io(entry.sftp, 'open', temporary, 'wx', mode);
      try {
        try {
          const buffer = Buffer.from(request.content);
          await io(entry.sftp, 'write', handle, buffer, 0, buffer.length, 0);
          await io(entry.sftp, 'fchmod', handle, mode);
        } finally { await io(entry.sftp, 'close', handle); }
        try {
          await io(entry.sftp, 'ext_openssh_rename', temporary, file);
        } catch {
          await io(entry.sftp, 'rename', temporary, file);
        }
      } finally {
        await io(entry.sftp, 'unlink', temporary).catch(() => {});
      }
      return { status: 'ok' };
    }
    if (request.operation === 'run_script') {
      if (!['benchmark', 'quality'].includes(request.script)) fail('script_unconfigured');
      const selected = entry.scripts[request.script];
      if (!selected) fail('script_unconfigured');
      const script = await canonicalPath(entry, selected);
      if (!/\.(?:py|sh)$/u.test(script)) fail('unsupported_script');
      return execute(entry, BOOTSTRAP_COMMAND, { mode: 'script', repository: entry.repository,
        script, args: checkedArgs(request.args) }, signal, token);
    }
    if (request.operation === 'cli') {
      const args = checkedArgs(request.args);
      if (!args.length || !['doctor', 'knowledge', 'collect', 'read', 'resource', 'context', 'skills',
        'plan', 'run', 'status', 'report', 'campaign', '--help', '-h', '--version'].includes(args[0])) fail('invalid_cli');
      return execute(entry, BOOTSTRAP_COMMAND, await runtimePayload(entry, args), signal, token);
    }
    fail('invalid_operation');
  }

  async function run(sessionId, id, request, signal) {
    const entry = connection(sessionId, id);
    if (!request || typeof request !== 'object') fail('invalid_operation');
    const exclusive = request.operation !== 'dashboard';
    if (exclusive && entry.busy) fail('connection_busy');
    if (request.operation === 'dashboard' && entry.dashboardStarting) fail('connection_busy');
    let timeout = 120000;
    if (request.maxMinutes !== undefined) {
      const value = request.maxMinutes;
      if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0 || value > 7 * 24 * 60) {
        fail('invalid_budget');
      }
      timeout = value * 60000;
    } else if (request.operation === 'run_script') {
      fail('missing_budget');
    }
    if (request.operation === 'cli' && request.args?.[0] === 'run' &&
        !request.args.includes('--help') && !request.args.includes('-h')) {
      const args = checkedArgs(request.args);
      const index = args.findLastIndex(value => value === '--max-minutes' || value.startsWith('--max-minutes='));
      if (index < 0) fail('missing_budget');
      const value = Number(args[index].includes('=') ? args[index].split('=')[1] : args[index + 1]);
      if (!Number.isFinite(value) || value <= 0 || value > 7 * 24 * 60) fail('invalid_budget');
      const runTimeout = value * 60000 + 30000;
      timeout = request.maxMinutes === undefined ? runTimeout : Math.min(timeout, runTimeout);
    }
    const token = {};
    if (exclusive) entry.busy = token;
    if (request.operation === 'dashboard') entry.dashboardStarting = true;
    const execution = request.operation === 'run_script' || request.operation === 'cli';
    const cleanup = execution ? () => {} : exclusive ? () => destroy(entry) : () => {
      if (entry.dashboard?.token === token) closeDashboard(entry);
    };
    try {
      return await bounded(entry, activeSignal => perform(entry, request, activeSignal, token),
        signal, timeout, cleanup);
    }
    finally {
      if (exclusive && !token.pending && entry.busy === token) entry.busy = false;
      if (request.operation === 'dashboard') entry.dashboardStarting = false;
    }
  }

  return {
    test,
    run,
    close(sessionId, id) {
      const entry = connections.get(id);
      if (entry) {
        if (entry.sessionId !== sessionId) fail('connection_unavailable');
        if (entry.destroying) fail('connection_closing');
        destroy(entry);
        return { status: 'closed' };
      }
      if (closedReceipts.has(id) && closedReceipts.get(id) === sessionId) {
        return { status: 'already_closed' };
      }
      fail('connection_unavailable');
    },
    closeSession(sessionId) {
      try {
        for (const entry of connections.values()) if (entry.sessionId === sessionId) destroy(entry);
        for (const entry of pending) if (entry.sessionId === sessionId) destroy(entry);
      } finally {
        for (const [id, owner] of closedReceipts) if (owner === sessionId) closedReceipts.delete(id);
      }
    },
    dispose() {
      try {
        for (const entry of connections.values()) destroy(entry);
        for (const entry of pending) destroy(entry);
      } finally {
        closedReceipts.clear();
      }
    },
  };
}

module.exports = { createRemoteManager, RemoteError };
