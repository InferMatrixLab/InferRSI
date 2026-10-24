"""Fixed retrieval baseline qualification; proposed gates remain unactivated."""
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


def score_response(text, expected):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result: raise ValueError('duplicate_key')
            result[key]=value
        return result
    body=text.strip()
    if body.startswith('```json\n') and body.endswith('\n```'):
        body=body[8:-4].strip()
    try:
        parsed=json.loads(body,object_pairs_hook=unique)
        shape_valid=isinstance(parsed,dict) and set(parsed)==set(expected) and all(isinstance(v,str) for v in parsed.values())
    except (ValueError,TypeError):
        parsed={};shape_valid=False
    matches=[shape_valid and parsed.get(key)==value for key,value in expected.items()]
    return {'shape_valid':shape_valid,'position_matches':matches,'complete':all(matches)}


async def main():
    p = argparse.ArgumentParser()
    for name in ('model', 'fixture', 'output'):
        p.add_argument('--' + name, required=True)
    args = p.parse_args()
    fixture_digest = '285ddc88444b082236aa11cc0469f9112b93225c660ed9cdc4a079316ca35db1'
    client_digest = 'f31fae8c573ecc4bf8e31dae03823502e71404333e8111f4b535432758302b29'
    assert digest(args.fixture) == fixture_digest
    assert digest(client.__file__) == client_digest
    assert digest(Path(args.model)/'config.json') == '74227dd615bf1ea975aa676bdf355a0379858c12f394b5365cd9dfa5fc2c70bc'
    assert importlib.metadata.version('vllm') == '0.32.0'
    cases = [json.loads(line) for line in Path(args.fixture).read_text().splitlines()]
    assert len(cases) == 30
    assert [r['input_tokens'] for r in cases] == [8192]*10+[65536]*10+[131072]*10
    for row in cases:
        assert len(row['input_ids']) == row['input_tokens']
        assert hashlib.sha256(json.dumps(row['input_ids'],separators=(',',':')).encode()).hexdigest() == row['input_ids_sha256']
    out = Path(args.output); out.mkdir(parents=True, exist_ok=False)
    with (out/'observations.jsonl').open('x') as stream:
        def emit(**row):
            stream.write(json.dumps(row)+'\n'); stream.flush()
            print(json.dumps({k: v for k, v in row.items() if k not in ('token_ids', 'itl')}), flush=True)
        emit(phase='protocol', observer_sha256=digest(__file__), fixture_sha256=fixture_digest,
             client_sha256=client_digest, cases=[r['id'] for r in cases], verdict='INCONCLUSIVE',
             scope='retrieval_baseline_qualification_no_candidate_or_activated_gates',
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
                    for index, case in enumerate(cases):
                        prompt = case['input_ids']; length=case['input_tokens']; cap=case['max_output_tokens'];chunks=[]
                        request = client.RequestFuncInput(
                            prompt=prompt, api_url=url+'/v1/completions', prompt_len=length,
                            output_len=cap, model='qwen38-fp8', ignore_eos=False,
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
                                 and terminal in (['length'], ['stop']) and b'data: [DONE]' in wire
                                 and len(usage) == 1 and 0 < len(tokens) <= cap and len(tokens) == result.output_tokens
                                 and usage[0]['completion_tokens'] == len(tokens)
                                 and usage[0]['prompt_tokens'] == length == result.prompt_len
                                 and len(result.itl) == len(tokens)-1 and len(choices) == len(tokens)
                                 and all(len(c.get('token_ids', [])) == 1 for c in choices))
                        score = score_response(result.generated_text, case['expected'])
                        emit(phase='request', index=index, case=case['id'], score=score, generated_text=result.generated_text, input_tokens=length,
                             requested_output_tokens=cap, output_tokens=len(tokens), token_ids=tokens,
                             terminal=terminal, usage=usage, valid=valid,
                             client_success=result.success, client_error=bool(result.error),
                             wire_sha256=hashlib.sha256(wire).hexdigest(),
                             prompt_sha256=hashlib.sha256(json.dumps(prompt).encode()).hexdigest(),
                             ttft_s=result.ttft, latency_s=result.latency, itl=result.itl,
                             tpot_s=(result.latency-result.ttft)/(len(tokens)-1) if len(tokens)>1 else None)
                        if not valid:
                            raise RuntimeError('baseline_framing_or_accounting_invalid')
            except BaseException as exc:
                emit(phase='error', exception=type(exc).__name__, reason=str(exc) if isinstance(exc, (RuntimeError, TimeoutError)) else 'see_private_log')
                raise
            finally:
                emit(phase='cleanup', **terminate_owned(process))
        emit(phase='complete', verdict='INCONCLUSIVE', scope='retrieval_baseline_qualification_only', elapsed_s=time.monotonic()-start)


if __name__=='__main__':
    asyncio.run(main())
