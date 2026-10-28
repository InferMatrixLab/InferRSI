"""Bounded baseline feasibility; no performance acceptance or candidate search."""
import argparse
import asyncio
import dataclasses
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.request

import aiohttp
import vllm.benchmarks.lib.endpoint_request_func as client


class RecordingResponse:
    def __init__(self, response, chunks):
        self.response, self.chunks = response, chunks
        self.status, self.reason, self.content = response.status, response.reason, self

    async def iter_any(self):
        async for chunk in self.response.content.iter_any():
            self.chunks.append(chunk)
            yield chunk


class RecordingContext:
    def __init__(self, context, chunks):
        self.context, self.chunks = context, chunks

    async def __aenter__(self):
        return RecordingResponse(await self.context.__aenter__(), self.chunks)

    async def __aexit__(self, *args):
        return await self.context.__aexit__(*args)


class RecordingSession:
    def __init__(self, session, chunks):
        self.session, self.chunks = session, chunks

    def post(self, *args, **kwargs):
        return RecordingContext(self.session.post(*args, **kwargs), self.chunks)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def group_members(pgid):
    rows = subprocess.check_output(['ps', '-eo', 'pid=,pgid='], text=True)
    return [int(pid) for pid, group in (r.split() for r in rows.splitlines())
            if int(group) == pgid]


def terminate_owned(process):
    forced = False
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        forced = True
    if group_members(process.pid):
        forced = True
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=10)
    return {'exit_code': process.returncode, 'forced': forced,
            'owned_group_remaining': len(group_members(process.pid))}


async def main():
    p = argparse.ArgumentParser()
    for name in ('model', 'fixture', 'output'):
        p.add_argument('--' + name, required=True)
    args = p.parse_args()
    fixture_digest = '4f4256cc4edc9a23f55f66151738a1ecef07eb752c695e7b7fbdfa17e01d6aa9'
    client_digest = 'f31fae8c573ecc4bf8e31dae03823502e71404333e8111f4b535432758302b29'
    assert digest(args.fixture) == fixture_digest
    assert digest(client.__file__) == client_digest
    assert digest(Path(args.model)/'config.json') == '74227dd615bf1ea975aa676bdf355a0379858c12f394b5365cd9dfa5fc2c70bc'
    assert importlib.metadata.version('vllm') == '0.32.0'
    data = json.loads(Path(args.fixture).read_text())
    samples = {r['id']: r['input_ids'] for r in data['samples']}
    cases = [('warmup', 32, 8), ('framing', 32, 8), ('feasibility', 8192, 32),
             ('feasibility', 65536, 8), ('feasibility', 131072, 8)]
    for _, length, _ in cases:
        assert len(samples[f'n{length}-s0']) == length
    out = Path(args.output); out.mkdir(parents=True, exist_ok=False)
    with (out/'observations.jsonl').open('x') as stream:
        def emit(**row):
            stream.write(json.dumps(row)+'\n'); stream.flush()
            print(json.dumps({k: v for k, v in row.items() if k not in ('token_ids', 'itl')}), flush=True)
        emit(phase='protocol', observer_sha256=digest(__file__), fixture_sha256=fixture_digest,
             client_sha256=client_digest, cases=cases, verdict='INCONCLUSIVE',
             scope='single_baseline_feasibility_no_candidate_no_formal_matrix',
             versions={k: importlib.metadata.version(k) for k in
                       ('vllm', 'torch', 'transformers', 'flashinfer-python', 'triton', 'aiohttp')},
             server_settings={'max_model_len': 133120, 'prefix_caching': False,
                              'language_model_only': True, 'other_optimization_flags': 'defaults'})
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        url = f'http://127.0.0.1:{port}'
        command = [sys.executable, '-u', '-m', 'vllm.entrypoints.openai.api_server',
                   '--model', args.model, '--host', '127.0.0.1', '--port', str(port),
                   '--served-model-name', 'qwen38-fp8', '--max-model-len', '133120',
                   '--no-enable-prefix-caching', '--language-model-only']
        (out/'command.private.json').write_text(json.dumps(command)+'\n')
        with (out/'server.private.log').open('x') as log:
            start = time.monotonic()
            process = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
            try:
                while True:
                    if process.poll() is not None:
                        raise RuntimeError('server_exited_before_readiness')
                    try:
                        with urllib.request.urlopen(url+'/health', timeout=2) as response:
                            assert response.status == 200
                        break
                    except (OSError, AssertionError):
                        if time.monotonic()-start > 1200:
                            raise TimeoutError('startup_timeout')
                        await asyncio.sleep(1)
                emit(phase='ready', startup_s=time.monotonic()-start)
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180)) as session:
                    for index, (purpose, length, cap) in enumerate(cases):
                        prompt = samples[f'n{length}-s0']; chunks = []
                        request = client.RequestFuncInput(
                            prompt=prompt, api_url=url+'/v1/completions', prompt_len=length,
                            output_len=cap, model='qwen38-fp8', ignore_eos=True,
                            extra_body={'temperature': 0, 'return_token_ids': True})
                        result = await client.async_request_openai_completions(request, RecordingSession(session, chunks))
                        wire = b''.join(chunks)
                        (out/f'{index}.sse').write_bytes(wire)
                        (out/f'{index}-client.json').write_text(json.dumps(dataclasses.asdict(result), indent=2)+'\n')
                        events = [json.loads(line[5:].strip()) for line in wire.splitlines()
                                  if line.startswith(b'data:') and line[5:].strip() != b'[DONE]']
                        choices = [c for e in events for c in e.get('choices', [])]
                        tokens = [t for c in choices for t in c.get('token_ids', [])]
                        usage = [e['usage'] for e in events if e.get('usage')]
                        echoes = [c['prompt_token_ids'] for c in choices if c.get('prompt_token_ids') is not None]
                        terminal = [c['finish_reason'] for c in choices if c.get('finish_reason')]
                        errors = [e for e in events if 'error' in e]
                        valid = (result.success and not result.error and not errors and echoes == [prompt]
                                 and terminal == ['length'] and b'data: [DONE]' in wire
                                 and len(usage) == 1 and len(tokens) == cap == result.output_tokens
                                 and usage[0]['completion_tokens'] == cap
                                 and usage[0]['prompt_tokens'] == length == result.prompt_len
                                 and len(result.itl) == cap-1 and len(choices) == cap
                                 and all(len(c.get('token_ids', [])) == 1 for c in choices))
                        emit(phase='request', index=index, purpose=purpose, input_tokens=length,
                             requested_output_tokens=cap, output_tokens=len(tokens), token_ids=tokens,
                             terminal=terminal, usage=usage, valid=valid,
                             client_success=result.success, client_error=bool(result.error),
                             wire_sha256=hashlib.sha256(wire).hexdigest(),
                             prompt_sha256=hashlib.sha256(json.dumps(prompt).encode()).hexdigest(),
                             ttft_s=result.ttft, latency_s=result.latency, itl=result.itl,
                             tpot_s=(result.latency-result.ttft)/(cap-1))
                        if not valid:
                            raise RuntimeError('baseline_framing_or_accounting_invalid')
            except BaseException as exc:
                emit(phase='error', exception=type(exc).__name__, reason=str(exc) if isinstance(exc, (RuntimeError, TimeoutError)) else 'see_private_log')
                raise
            finally:
                emit(phase='cleanup', **terminate_owned(process))
        emit(phase='complete', verdict='INCONCLUSIVE', scope='feasibility_only', elapsed_s=time.monotonic()-start)


asyncio.run(main())
