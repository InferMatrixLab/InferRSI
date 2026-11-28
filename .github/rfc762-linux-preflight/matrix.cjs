const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const { createHash, generateKeyPairSync } = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

const python = process.argv[2];
assert.equal(process.platform, 'linux');
const build = path.resolve(process.env.P762_MATRIX_BUILD);
const run = path.join(path.resolve(process.env.P762_RESULTS), 'matrix');
fs.mkdirSync(run);
const oldPackage = path.join(build, 'old', 'package');
const newPackage = path.join(build, 'dsh', 'package');
const archiveName = 'remote-runtime.zip';
const { Server, utils } = require(path.join(oldPackage, 'vendor', 'ssh2.cjs'));
const password = 'local-test-fixture-only';
const hostKey = generateKeyPairSync('rsa', { modulusLength: 2048 }).privateKey
  .export({ type: 'pkcs1', format: 'pem' });
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const shaOf = file => digest(fs.readFileSync(file));
const fingerprint = 'SHA256:' + createHash('sha256').update(utils.parseKey(hostKey).getPublicSSH())
  .digest('base64').replace(/=+$/u, '');
const sftpAttributes = { mode: 0o40755, size: 0, uid: 0, gid: 0, atime: 1, mtime: 1 };
const prefix = "python3 -I -u -c '";
const peers = new Set();
const report = {
  environment: {
    os: os.type(),
    kernel: os.release(),
    connection: 'Loopback SSH/SFTP running the packaged bootstrap on Linux with a Python audit hook',
  },
  packages: {
    old: { git: '01333d70e3c8b33f940b844b8569d96b39388a83' },
    new: { git: process.env.P762_DELIVERY_SOURCE, candidate: true },
  },
  cases: {},
};
const metadata = (folder, archive) => ({
  plugin: JSON.parse(fs.readFileSync(path.join(folder, 'package.json'), 'utf8')).version,
  pluginRemoteSha256: shaOf(path.join(folder, 'remote.cjs')),
  zipSha256: shaOf(path.join(folder, archiveName)),
  tgzSha256: shaOf(archive),
});
Object.assign(report.packages.old, metadata(oldPackage, path.join(build, 'old.tgz')));
Object.assign(report.packages.new, metadata(newPackage, path.join(build, 'dsh.tgz')));

function openPeer(root, received) {
  const virtualRoot = fs.realpathSync(root);
  const server = new Server({ hostKeys: [hostKey] }, client => {
    peers.add(client);
    client.on('error', () => {});
    client.once('close', () => peers.delete(client));
    client.on('authentication', entry => {
      if (entry.method === 'password' && entry.username === 'fixture' && entry.password === password) entry.accept();
      else entry.reject();
    });
    client.on('ready', () => {
      client.on('session', accept => {
        const session = accept();
        session.on('sftp', acceptSftp => {
          const sftp = acceptSftp();
          sftp.on('REALPATH', (id, target) => {
            if (target === virtualRoot) sftp.name(id, [{ filename: target, attrs: sftpAttributes }]);
            else sftp.status(id, utils.sftp.STATUS_CODE.NO_SUCH_FILE);
          });
          sftp.on('STAT', (id, target) => {
            if (target === virtualRoot) sftp.attrs(id, sftpAttributes);
            else sftp.status(id, utils.sftp.STATUS_CODE.NO_SUCH_FILE);
          });
        });
        session.on('exec', (acceptExec, reject, info) => {
          if (info.command === 'uname -s') {
            const channel = acceptExec();
            channel.write(os.type() + '\n');
            channel.exit(0);
            channel.end();
            return;
          }
          if (!(info.command.startsWith(prefix) && info.command.endsWith("'"))) {
            reject();
            return;
          }
          const channel = acceptExec();
          const chunks = [];
          channel.on('data', chunk => chunks.push(chunk));
          channel.on('end', () => {
            try {
              const request = JSON.parse(Buffer.concat(chunks).toString('utf8'));
              assert.equal(request.repository, virtualRoot);
              assert.equal(request.mode, 'cli');
              const archive = Buffer.from(request.archive, 'base64');
              const wire = { args: request.args, bytes: archive.length, zipSha256: digest(archive),
                entryProtocol: request.entry_protocol ?? null };
              received.push(wire);
              const bootstrap = info.command.slice(prefix.length, -1).replaceAll("'\\''", "'");
              const result = spawnSync(python, ['-X', 'utf8', '-I', '-S', '-u', path.join(__dirname, 'bridge.py'), root],
                { input: JSON.stringify({ bootstrap, request }), maxBuffer: 8 * 1024 * 1024 });
              if (result.error) throw result.error;
              channel.write(result.stdout);
              const marker = '__DSH_PREFLIGHT_AUDIT__ ';
              const diagnostics = [];
              for (const line of result.stderr.toString('utf8').split(/\r?\n/u)) {
                if (line.startsWith(marker)) wire.audit = JSON.parse(line.slice(marker.length));
                else diagnostics.push(line);
              }
              channel.stderr.write(diagnostics.join('\n'));
              channel.exit(result.status ?? 98);
            } catch (error) {
              channel.stderr.write(String(error) + '\n');
              channel.exit(99);
            }
            channel.end();
          });
        });
      });
    });
  });
  return server;
}

function snapshot(root) {
  const files = {};
  function visit(dir) {
    for (const item of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const itemPath = path.join(dir, item.name);
      const rel = path.relative(root, itemPath).split(path.sep).join('/');
      if (item.isDirectory()) {
        files[rel + '/'] = 'directory';
        visit(itemPath);
      } else {
        files[rel] = shaOf(itemPath);
      }
    }
  }
  visit(root);
  return files;
}

function writeJson(file, value) {
  fs.writeFileSync(file, JSON.stringify(value, null, 2) + '\n');
}

function writeStagedInputs(root) {
  const context = {
    state: 'complete', text: '', queries: ['fixture query'],
    sources: [{ ref: 'package:example', revision: 'sha256:example', locator: 'core' }], missing_reason: '',
  };
  writeJson(path.join(root, 'template.json'), {
    schema_version: 1, reviewed_by_caller: true, campaign_id: 'campaign',
    candidate_id: 'candidate-a', round: 1, context,
    search_space: { state: 'complete', items: [{ id: 'option-a', description: 'Test option A' }], missing_reason: '' },
    steps: {
      state: 'complete', items: [{ sequence: 1, kind: 'attempt', action: 'Measure option A',
        motivation: 'Check the hypothesis', outcome: 'failed', result: 'Local fixture only', search_id: 'option-a' }],
      missing_reason: '',
    },
    summary: { state: 'partial', successes: [], failures: ['Fixture failed quality'],
      limitations: ['One option'], missing_reason: 'Remaining options were not run' },
  });
  fs.writeFileSync(path.join(root, 'reviewed-context.txt'), 'Synthetic reviewed context for DSH preflight.\n');
}


const ref = 'package:inferrsi.common.skills.cgroup_resource_controls';
const create = ['evidence', 'init', '--directory', 'campaign', '--id', 'campaign', '--synthetic'];
const legacyInit = ['campaign', ...create.slice(1)];
const collect = ['collect', '--json', '--id', ref, '--archive', 'campaign', '--capture-id', 'snapshot'];

function seedManual(root) {
  const target = path.join(root, 'campaign');
  fs.mkdirSync(target);
  writeJson(path.join(target, 'campaign.json'), { campaign_id: 'campaign', synthetic: true });
}

async function paired(label, pluginKey, runtimeKey, body) {
  const root = fs.mkdtempSync(path.join(run, label + '-'));
  const plugin = pluginKey === 'old' ? oldPackage : newPackage;
  const runtime = runtimeKey === 'old' ? oldPackage : newPackage;
  const destDir = fs.mkdtempSync(path.join(run, 'archive-'));
  fs.copyFileSync(path.join(runtime, archiveName), path.join(destDir, archiveName));
  const archiveHash = shaOf(path.join(destDir, archiveName));
  const state = { plugin: pluginKey, runtime: runtimeKey, archiveHash, commands: [] };
  report.cases[label] = state;
  const received = [];
  const server = openPeer(root, received);
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  let fetchRoute;
  let remoteTool;
  let dispose;
  const { installRemote } = require(path.join(plugin, 'remote-host.cjs'));
  installRemote({
    effect: effect => { dispose = effect(); },
    on: () => {},
    connection: { fetch: { register: route => { fetchRoute = route; } } },
    tools: { register: tool => { remoteTool = tool; } },
  }, path.join(destDir, 'runtime'));
  const sessionId = 'dsh-preflight-' + label;
  try {
    const response = await fetchRoute.fetch(new Request('http://localhost/api/inferrsi/connection', {
      method: 'POST',
      body: JSON.stringify({
        action: 'test', sessionId, options: {
          host: '127.0.0.1', port: server.address().port, user: 'fixture',
          authType: 'password', password, fingerprint, repository: fs.realpathSync(root),
        },
      }),
    }));
    const connection = await response.json();
    assert.equal(connection.status, 'connected', JSON.stringify(connection));
    async function call(args, expected = 0, { noEffects = false, guidance, noWorkspaceWrites = false } = {}) {
      const before = snapshot(root);
      const offset = received.length;
      let actual;
      try {
        actual = await remoteTool.execute({ connectionId: connection.connectionId, operation: 'cli', args },
          { agent: { id: sessionId }, signal: new AbortController().signal });
      } catch (error) {
        assert.equal(error.name, 'RemoteError');
        actual = { pluginError: error.code, message: error.message };
      }
      const wire = received.slice(offset);
      const key = state.commands.length + 1;
      const workspaceUnchanged = JSON.stringify(snapshot(root)) === JSON.stringify(before);
      const detail = {
        args, expected, exitCode: actual.exitCode ?? null, pluginError: actual.pluginError ?? null,
        diagnostic: actual.pluginError ? actual.message : actual.stderr.trim().split(/\r?\n/u).at(-1) || null,
        truncated: actual.truncated ?? null, wire, workspaceUnchanged,
      };
      state.commands.push(detail);
      writeJson(path.join(run, label + '-' + key + '.json'), { ...detail, actual });
      console.log(label, key, detail.exitCode ?? detail.pluginError, args.slice(0, 3).join(' '),
        detail.diagnostic || '');
      if (typeof expected === 'string') {
        assert.equal(actual.pluginError, expected);
        assert.equal(wire.length, 0);
      } else {
        assert.equal(actual.exitCode, expected, actual.stderr || actual.stdout);
        assert.equal(actual.truncated, false);
        assert.equal(wire.length, 1);
        assert.equal(wire[0].zipSha256, archiveHash);
        assert.deepEqual(wire[0].args, args);
        assert.ok(wire[0].audit);
      }
      if (guidance) assert.match(detail.diagnostic, guidance);
      if (noEffects || noWorkspaceWrites) {
        assert.equal(workspaceUnchanged, true, 'workspace snapshot changed');
        for (const entry of wire) assert.equal(entry.audit.workspaceWrites, 0,
          JSON.stringify(entry.audit.workspaceWriteSamples));
      }
      if (noEffects) for (const entry of wire) assert.deepEqual(entry.audit.launches, []);
      return { ...actual, audit: wire[0]?.audit };
    }
    await body({ root, state, call });
  } finally {
    await dispose();
    for (const peer of peers) peer.end();
    await new Promise(resolve => server.close(resolve));
    writeJson(path.join(run, 'summary.json'), report);
  }
}

function localFixture(root, args) {
  const result = spawnSync(python, ['-B', '-X', 'utf8', path.join(__dirname, 'delivery-fixture.py'), ...args],
    { cwd: root, encoding: 'utf8' });
  assert.ifError(result.error);
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return JSON.parse(result.stdout);
}

async function projectGate({ root, state, call }) {
  const start = localFixture(root, ['seed']);
  const prepared = await call([...start, '--prepare-intake']);
  const pending = JSON.parse(prepared.stdout);
  assert.equal(pending.execution, 'not started');
  assert.ok(pending.task_brief.id);
  assert.equal(fs.existsSync(path.join(root, 'managed')), false);
  assert.ok(!prepared.audit.launches.some(item => /measure\.py|quality\.py/u.test(item.command)));
  const beforeApproval = snapshot(root);
  const rejected = await call(start, 2);
  assert.deepEqual(snapshot(root), beforeApproval);
  const blocked = JSON.parse(rejected.stdout);
  assert.equal(blocked.execution, 'not started');
  assert.equal(blocked.status, 'blocked');
  assert.deepEqual(rejected.audit.launches, []);
  assert.equal(fs.existsSync(path.join(root, 'managed')), false);
  localFixture(root, ['approve', pending.task_brief.id]);
  const oldStart = ['campaign', 'start', '--directory', ...start.slice(4)];
  await call(oldStart, 2, { noEffects: true, guidance: /Use inferrsi session start project/u });
  const approvedPath = path.join(root, 'managed.intake.json');
  const approvedBytes = fs.readFileSync(approvedPath);
  assert.ok(!approvedBytes.includes(Buffer.from('\r\n')), 'the new record must use LF');
  const started = await call(start);
  assert.deepEqual(fs.readFileSync(approvedPath), approvedBytes);
  const startedView = JSON.parse(started.stdout);
  assert.equal(startedView.state, 'active');
  assert.equal(startedView.next_action, 'record_bottleneck_diagnosis');
  assert.deepEqual(started.audit.launches, []);
  const managed = path.join(root, 'managed');
  const planBytes = fs.readFileSync(path.join(managed, 'plan.json'));
  const plan = JSON.parse(planBytes);
  const receipt = startedView.intake;
  assert.equal(receipt.gate, 'ready');
  assert.equal(receipt.brief_id, pending.task_brief.id);
  const intakeBytes = fs.readFileSync(path.join(managed, receipt.record));
  const rawIntakeSha256 = digest(intakeBytes);
  const canonicalIntakeSha256 = digest(intakeBytes.toString('utf8').replaceAll('\r\n', '\n'));
  assert.equal(canonicalIntakeSha256, receipt.sha256);
  assert.equal(rawIntakeSha256, receipt.sha256);
  assert.deepEqual(intakeBytes, approvedBytes);
  assert.equal(plan.intake_receipt, `plan/intake-${receipt.sha256}.json`);
  const frozenReceiptBytes = fs.readFileSync(path.join(managed, plan.intake_receipt));
  assert.deepEqual(JSON.parse(frozenReceiptBytes), receipt);
  const status = await call(['session', 'status', '--session', 'managed'], 0, { noWorkspaceWrites: true });
  const statusView = JSON.parse(status.stdout);
  assert.equal(statusView.state, 'active');
  assert.equal(statusView.next_action, startedView.next_action);
  state.intake = {
    prepared: pending.execution, withoutApproval: blocked.status, approved: startedView.next_action,
    briefId: receipt.brief_id, approvedIntakeSha256: receipt.sha256, rawIntakeSha256,
    approvedBytes: approvedBytes.length, frozenPlanSha256: digest(planBytes),
    frozenReceiptPath: plan.intake_receipt, frozenReceiptSha256: digest(frozenReceiptBytes),
    status: statusView.state,
  };
}

function writeRollout(root, output) {
  const cwd = root.replaceAll('\\', '/');
  const argv = ['inferrsi', ...collect];
  const events = [
    { type: 'session_meta', payload: { id: 'dsh-cutover-fixture', cwd } },
    { type: 'response_item', payload: { type: 'function_call', name: 'exec_command', call_id: 'capture',
      arguments: JSON.stringify({ cmd: argv.join(' '), workdir: cwd }) } },
    { type: 'event_msg', payload: { type: 'item_completed', item: { type: 'CommandExecution', id: 'capture',
      cwd: pathToFileURL(root).href, command: argv, exit_code: 0, aggregated_output: output } } },
    { type: 'response_item', payload: { type: 'function_call_output', call_id: 'capture',
      output: 'Output:\n' + output } },
  ];
  fs.writeFileSync(path.join(root, 'fixture-rollout.jsonl'), events.map(item => JSON.stringify(item)).join('\n') + '\n');
}

async function evidenceFlow({ root, state, call }) {
  await call(legacyInit, 2, { noEffects: true, guidance: /Use inferrsi evidence init/u });
  await call(create);
  const legacyCapture = ['campaign', 'capture-context', '--directory', 'campaign',
    '--id', 'snapshot', '--id-ref', ref];
  await call(legacyCapture, 2, { noEffects: true, guidance: /Use inferrsi collect --archive/u });
  const captured = await call(collect);
  const receipt = JSON.parse(captured.stdout);
  const captureFile = path.join(root, 'campaign', receipt.reference.path);
  assert.equal(shaOf(captureFile), receipt.reference.sha256);
  const material = receipt.context.items.find(item => item.ref === ref);
  assert.ok(material?.revision);
  assert.match(material.revision, /^sha256:[0-9a-f]{64}$/u);
  assert.deepEqual(receipt.context, JSON.parse(fs.readFileSync(captureFile, 'utf8')));
  assert.deepEqual(receipt.context.request.ids, [ref]);
  writeRollout(root, captured.stdout);
  const search = ['evidence', 'import-search', '--directory', 'campaign', '--round', '1',
    '--trace', 'fixture-rollout.jsonl', '--lines', '2', '4',
    '--knowledge-root', root, '--complete', '--context-id', 'snapshot'];
  await call(search);
  const ledger = path.join(root, 'campaign', 'search', 'round-1.json');
  const ledgerHash = shaOf(ledger);
  const record = JSON.parse(fs.readFileSync(ledger, 'utf8'));
  assert.equal(record.coverage, 'complete');
  assert.equal(record.events.length, 1);
  const event = record.events[0];
  assert.equal(event.delivery.state, 'visible');
  assert.equal(event.delivery.return_line, 4);
  assert.equal(event.sha256, receipt.reference.sha256);
  assert.equal(event.source, receipt.reference.path);
  assert.ok(event.materials.some(item => item.ref === ref && item.revision === material.revision));
  assert.deepEqual(record.counts, { searches: 0, hits: 0, unique_hits: 0, used: 0 });
  assert.equal(record.adoption.direct_reads.read_only, 1);
  assert.equal(record.adoption.direct_reads.adopted, 0);
  await call([...search, '--context-id', 'snapshot']);
  assert.equal(shaOf(ledger), ledgerHash);
  assert.equal(shaOf(captureFile), receipt.reference.sha256);
  state.search = {
    captureSha256: receipt.reference.sha256, ledgerSha256: ledgerHash,
    revision: material.revision, ref, counts: record.counts,
    coverage: record.coverage, source: event.source, returnedOn: event.delivery.return_line,
    directReads: record.adoption.direct_reads, repeatedImportIdentical: true,
  };

  writeStagedInputs(root);
  const assemble = ['evidence', 'assemble-trace', '--directory', 'campaign',
    '--template', 'template.json', '--context-file', 'reviewed-context.txt', '--output', 'optimization.json'];
  await call(assemble);
  const target = path.join(root, 'campaign');
  const traceFile = path.join(target, 'optimization.json');
  const traceHash = shaOf(traceFile);
  const index = path.join(target, 'rounds.jsonl');
  assert.equal(fs.existsSync(index), false);
  assert.equal(fs.existsSync(path.join(target, 'candidates', 'candidate-a', 'candidate.json')), false);
  const recordCommand = candidate => ['evidence', 'record', '--directory', 'campaign',
    '--candidate', candidate, '--run-id', 'run-a', '--round', '1', '--title', 'Fixture',
    '--optimization-trace', 'optimization.json'];
  await call(recordCommand('candidate-a'), 2, { noEffects: true, guidance: /run/i });
  const retainedRun = path.join(target, 'runs', 'run-a');
  fs.mkdirSync(retainedRun, { recursive: true });
  writeJson(path.join(retainedRun, 'run.lock.json'), { workload_id: 'fixture' });
  await call(recordCommand('wrong-candidate'), 2, { noEffects: true, guidance: /identity_mismatch/u });
  await call(['campaign', ...recordCommand('candidate-a').slice(1)], 2,
    { noEffects: true, guidance: /Use inferrsi evidence record/u });
  await call(recordCommand('candidate-a'));
  const candidate = JSON.parse(fs.readFileSync(path.join(target, 'candidates', 'candidate-a', 'candidate.json'), 'utf8'));
  assert.equal(candidate.optimization_trace_ref.sha256, traceHash);
  assert.equal(shaOf(traceFile), traceHash);
  await call(['evidence', 'decide', '--directory', 'campaign', '--candidate', 'candidate-a',
    '--round', '1', '--outcome', 'rejected']);
  const decisions = fs.readFileSync(index, 'utf8').trim().split(/\r?\n/u).map(JSON.parse);
  assert.equal(decisions.length, 1);
  assert.deepEqual(decisions[0].decision, { candidate_id: 'candidate-a', outcome: 'rejected' });
  state.stagedEvidence = { traceHash, candidateTraceHash: candidate.optimization_trace_ref.sha256,
    decision: decisions[0].decision, badInputsLeftWorkspaceUnchanged: true };
}

async function newNew(context) {
  const { state, call } = context;
  const version = await call(['--version'], 0, { noEffects: true });
  assert.equal(version.stdout.trim(), process.env.P762_DELIVERY_RUNTIME_VERSION ?? '0+unknown');
  const help = await call(['--help'], 0, { noEffects: true });
  assert.match(help.stdout, /[{,]session[,}]/u);
  assert.match(help.stdout, /[{,]evidence[,}]/u);
  assert.doesNotMatch(help.stdout, /[{,]campaign[,}]/u);
  state.runtimeVersion = version.stdout.trim();
  await evidenceFlow(context);
  await projectGate(context);
}

async function oldNew({root, call}) {
  seedManual(root);
  await call(['session', 'start', 'project'], 'invalid_cli', { noEffects: true });
  await call(collect, 2, { noEffects: true, guidance: /plugin\/runtime version mismatch.*(together|bundled runtime)/u });
  await call(['--version'], 2, { noEffects: true, guidance: /plugin\/runtime version mismatch/u });
  await call(['campaign', ...create.slice(1, 3), 'legacy', ...create.slice(4)], 2,
    { noEffects: true, guidance: /Use inferrsi evidence init/u });
  await call(['campaign', 'capture-context', '--directory', 'campaign', '--id', 'legacy', '--id-ref', ref], 2,
    { noEffects: true, guidance: /Use inferrsi collect --archive/u });
}

async function newOld({root, call}) {
  seedManual(root);
  const rejected = { noEffects: true, guidance: /plugin\/runtime version mismatch.*bundled runtime/u };
  for (const args of [collect, create, ['session', 'start', 'project'], legacyInit]) {
    await call(args, 'runtime_mismatch', rejected);
  }
}

async function oldControl({root, state, call}) {
  const version = await call(['--version'], 0, { noEffects: true });
  const result = await call(legacyInit);
  assert.ok(result.audit.workspaceWrites > 0, 'audit missed a known legacy write');
  assert.ok(fs.existsSync(path.join(root, 'campaign', 'campaign.json')));
  state.runtimeVersion = version.stdout.trim();
}

async function main() {
  console.log('Local evidence:', run);
  for (const [label, plugin, runtime, body] of [
    ['old-control', 'old', 'old', oldControl],
    ['new-old', 'new', 'old', newOld],
    ['old-new', 'old', 'new', oldNew],
    ['new-new', 'new', 'new', newNew],
  ]) {
    if (process.argv[3] && process.argv[3] !== label) continue;
    try {
      await paired(label, plugin, runtime, body);
    } catch (error) {
      process.exitCode = 1;
      report.cases[label].failure = String(error.stack || error);
      console.error(label, error.stack || error);
      writeJson(path.join(run, 'summary.json'), report);
    }
  }
}
main().catch(error => { console.error(error.stack); process.exitCode = 1; });
