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
    for name in ('model', 'fixture', 'output', 'source'):
        p.add_argument('--'+name, required=True)
    args = p.parse_args()
    assert digest(args.fixture) == '4f4256cc4edc9a23f55f66151738a1ecef07eb752c695e7b7fbdfa17e01d6aa9'
    assert digest(client.__file__) == 'f31fae8c573ecc4bf8e31dae03823502e71404333e8111f4b535432758302b29'
    samples = {r['id']: r['input_ids'] for r in json.loads(Path(args.fixture).read_text())['samples']}
    prompt = samples['n8192-s0']
    assert len(prompt) == 8192
    out = Path(args.output); out.mkdir(parents=True, exist_ok=False)
    with (out/'observations.jsonl').open('x') as stream:
        def emit(**row):
            stream.write(json.dumps(row)+'\n'); stream.flush()
            print(json.dumps({k:v for k,v in row.items() if k not in ('token_ids','itl')}), flush=True)
        emit(phase='protocol', scope='single_case_feasibility_not_formal_acceptance', verdict='INCONCLUSIVE',
             arms=['triton', 'flashinfer', 'vllm'], cases=[['warmup',8192,16],['measurement',8192,2048]],
             observer_sha256=digest(__file__), fixture_sha256=digest(args.fixture),
             client_sha256=digest(client.__file__),
             source_hashes={str(f.relative_to(args.source)):digest(f) for f in sorted(Path(args.source).glob('nanovllm/qwen38/*.py'))},
             versions={k:importlib.metadata.version(k) for k in ('vllm','torch','triton','flashinfer-python','transformers')})
        for arm in ('triton','flashinfer','vllm'):
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
            url=f'http://127.0.0.1:{port}'
            ready=out/f'{arm}-ready.json'; shutdown=out/f'{arm}-shutdown.json'
            env=dict(os.environ, PYTHONPATH=args.source, NANOVLLM_FP8_GEMM=arm, NANOVLLM_CUDA_GRAPH='1')
            if arm=='vllm':
                env.pop('PYTHONPATH',None)
                command=[sys.executable,'-u','-m','vllm.entrypoints.openai.api_server',
                         '--model',args.model,'--host','127.0.0.1','--port',str(port),
                         '--served-model-name','qwen38-fp8','--max-model-len','10240',
                         '--no-enable-prefix-caching','--language-model-only']
            else:
                command=[sys.executable,'-u','-m','nanovllm.qwen38.server','--model',args.model,
                         '--port',str(port),'--max-context-tokens','10240','--max-active-requests','1',
                         '--ready-file',str(ready),'--shutdown-file',str(shutdown)]
            (out/f'{arm}-command.private.json').write_text(json.dumps(command)+'\n')
            with (out/f'{arm}-server.private.log').open('x') as log:
                start=time.monotonic()
                process=subprocess.Popen(command,cwd=args.source,env=env,stdout=log,stderr=log,start_new_session=True)
                try:
                    while True:
                        if process.poll() is not None: raise RuntimeError('server_exited_before_readiness')
                        try:
                            with urllib.request.urlopen(url+'/health',timeout=2) as response:
                                assert response.status==200
                                health=json.load(response) if arm!='vllm' else {}
                            break
                        except (OSError,AssertionError):
                            if time.monotonic()-start>600: raise TimeoutError('startup_timeout')
                            await asyncio.sleep(0.5)
                    model_id=health.get('model_id','qwen38-fp8')
                    emit(phase='ready',arm=arm,startup_s=time.monotonic()-start,
                         loader_report=health.get('loader_report'),graph_prewarm=health.get('graph_prewarm'))
                    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=500)) as session:
                        for index,(purpose,cap) in enumerate((('warmup',16),('measurement',2048))):
                            chunks=[]
                            request=client.RequestFuncInput(prompt=prompt,api_url=url+'/v1/completions',prompt_len=8192,
                                output_len=cap,model=model_id,ignore_eos=True,extra_body={'temperature':0,'return_token_ids':True})
                            result=await client.async_request_openai_completions(request,RecordingSession(session,chunks))
                            wire=b''.join(chunks)
                            (out/f'{arm}-{index}.sse').write_bytes(wire)
                            (out/f'{arm}-{index}-client.json').write_text(json.dumps(dataclasses.asdict(result),indent=2)+'\n')
                            payloads=[line[5:].strip() for line in wire.splitlines() if line.startswith(b'data:')]
                            framing=(payloads.count(b'[DONE]')==1 and payloads[-1:]==[b'[DONE]'])
                            events=[json.loads(payload) for payload in payloads if payload!=b'[DONE]']
                            choices=[c for e in events for c in e.get('choices',[])]
                            tokens=[t for c in choices for t in c.get('token_ids',[])]
                            usage=[e['usage'] for e in events if e.get('usage')]
                            echoes=[c['prompt_token_ids'] for c in choices if c.get('prompt_token_ids') is not None]
                            terminal=[c['finish_reason'] for c in choices if c.get('finish_reason')]
                            valid=(result.success and not result.error and not any('error' in e for e in events)
                                and echoes==[prompt] and terminal==['length'] and framing
                                and len(usage)==1 and len(tokens)==cap==result.output_tokens
                                and usage[0]['completion_tokens']==cap and usage[0]['prompt_tokens']==8192==result.prompt_len
                                and len(result.itl)==len([e for e in events if e.get('choices')])-1)
                            emit(phase='request',arm=arm,purpose=purpose,input_tokens=8192,output_tokens=len(tokens),
                                 valid=valid,token_ids=tokens,usage=usage,terminal=terminal,
                                 chunk_token_counts=[len(c.get('token_ids',[])) for c in choices],
                                 client_error=bool(result.error),ttft_s=result.ttft,latency_s=result.latency,itl=result.itl,
                                 tpot_s=(result.latency-result.ttft)/(cap-1),wire_sha256=hashlib.sha256(wire).hexdigest())
                            if not valid: raise RuntimeError('HTTP_accounting_failed')
                    if arm!='vllm':
                        with urllib.request.urlopen(url+'/stats',timeout=10) as response: stats=json.load(response)
                        with urllib.request.urlopen(url+'/health',timeout=10) as response: health=json.load(response)
                        (out/f'{arm}-health.private.json').write_text(json.dumps(health,indent=2)+'\n')
                        emit(phase='postflight',arm=arm,active_requests=stats['active_requests'],
                             runner_state_count=stats['runner_state_count'],fp8_execution=health['fp8_execution'])
                        assert not stats['active_requests'] and not stats['runner_state_count']
                except BaseException as exc:
                    emit(phase='error',arm=arm,exception=type(exc).__name__)
                    raise
                finally:
                    cleanup=terminate_owned(process)
                    emit(phase='cleanup',arm=arm,**cleanup)
                    assert cleanup['owned_group_remaining']==0
        emit(phase='complete',verdict='INCONCLUSIVE',scope='single_case_feasibility_not_formal_acceptance')

asyncio.run(main())
