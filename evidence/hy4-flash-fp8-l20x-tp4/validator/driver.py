import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request

from lifecycle import run_service, drain

phase, candidate_arg, receipt_arg, result_arg = sys.argv[1:5]
candidate = Path(candidate_arg).resolve()
receipt = Path(receipt_arg)
result_path = Path(result_arg)
attempt = receipt.parent
request = json.loads(Path(os.environ['INFERRSI_ATTEMPT_REQUEST']).read_text())
root = Path(os.environ['HY4_CAMPAIGN'])
inputs = root / 'inputs'
venv = Path(os.environ['HY4_ENGINE_VENV'])
install = venv.parent
model_path = Path(os.environ['HY4_WEIGHTS'])
private_dir = attempt / 'measurements'
private_dir.mkdir(exist_ok=True)
model_name = 'hy4-' + request['service_id']

def write(path, body):
    temp = path.with_suffix('.pending')
    temp.write_text(json.dumps(body, ensure_ascii=False))
    temp.replace(path)

def append(path, body):
    with path.open('a') as f:
        f.write(json.dumps(body, ensure_ascii=False) + '\n')
        f.flush()

def serve():
    # Preserve the harness snapshot, linking its tracked sources into an import tree.
    # Native extensions and generated build dependencies come from the calibrated venv.
    mirror = attempt / 'runtime'
    def link(src, dst):
        os.symlink(str(Path(src).resolve()), dst)
    shutil.copytree(candidate / 'vllm', mirror/'vllm', copy_function=link)
    tracked = set(subprocess.check_output(['git','-C',str(install),'ls-files','-z','vllm']).decode().split('\0'))
    for parent, dirs, files in os.walk(install / 'vllm'):
        dirs[:] = [d for d in dirs if d != '__pycache__' and not d.startswith('.')]
        for name in files:
            path = Path(parent)/name
            relative = path.relative_to(install)
            # The ABI3 wheel ships a Python _C facade backed by _C_extension.
            # A leftover legacy pybind from an older editable build shadows that facade.
            if relative.parent.as_posix() == 'vllm/third_party/deep_gemm' and name.startswith('_C.cpython-') and name.endswith('.so'):
                continue
            dest = mirror / relative
            if name.endswith('.pyc') or relative.as_posix() in tracked or dest.exists() or path.is_symlink() and not path.exists():
                continue
            dest.parent.mkdir(exist_ok=True, parents=True)
            link(path, dest)
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
    opts = list(request['effective_config']['baseline_flags'])
    flags_file = candidate / 'examples/deployment/hy4-flash-options.json'
    if flags_file.is_file():
        opts.extend(json.loads(flags_file.read_text())['extra_flags'])
    env = dict(os.environ, PYTHONPATH=str(mirror), PYTHONNOUSERSITE='1',
               NCCL_DEBUG='INFO', NCCL_DEBUG_SUBSYS='INIT,GRAPH,P2P',
               CUDA_HOME='/usr/local/cuda', PATH='/usr/local/cuda/bin:'+str(venv/'bin')+':'+os.environ['PATH'])
    # Verify that Python resolves the executed package to the revision-bound snapshot.
    probe = subprocess.check_output([str(venv/'bin/python'),'-c',
        'import vllm; from pathlib import Path; print(Path(vllm.__file__).resolve())'],
        cwd=mirror, env=env, text=True).splitlines()[-1]
    if Path(probe) != candidate/'vllm/__init__.py':
        raise RuntimeError('import root does not match the candidate')
    rev = request['revision']
    expected = subprocess.check_output(['git','-C',os.environ['HY4_SOURCE'],'rev-parse',rev+':vllm/__init__.py'],text=True).strip()
    actual = subprocess.check_output(['git','hash-object',probe],text=True).strip()
    assert expected == actual
    argv = [str(venv/'bin/python'),'-m','vllm.entrypoints.cli.main','serve',str(model_path),
            '--host','127.0.0.1','--port',str(port),'--served-model-name',model_name,*opts]
    info = dict(pid=os.getpid(), port=port, name=model_name, flags=opts, loaded_root=str(candidate),
                loaded_revision=rev, binding=request)
    raise SystemExit(run_service(argv, mirror, env, receipt, info))

def fetch(url, data=None, timeout=30):
    headers = {'Content-Type':'application/json'}
    payload = json.dumps(data,separators=(',',':')).encode() if data is not None else None
    req = urllib.request.Request(url,data=payload,headers=headers)
    try:
        return urllib.request.urlopen(req,timeout=timeout)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'HTTP {exc.code}: {exc.read(1536).decode(errors="replace")}') from exc

def bind():
    until = time.monotonic() + (2700 if phase == 'ready' else 10)
    while time.monotonic() < until:
        if receipt.exists():
            info = json.loads(receipt.read_text())
            os.kill(info['pid'], 0)
            if Path(f"/proc/{info['pid']}/stat").read_text().rsplit(')', 1)[1].strip().split()[0] == 'Z':
                raise RuntimeError('service exited before readiness')
            url = f"http://127.0.0.1:{info['port']}"
            try:
                with fetch(url+'/v1/models', timeout=5) as response:
                    models=json.load(response)['data']
                assert info['binding'] == request and models[0]['id'] == model_name
                return info,url
            except (OSError, RuntimeError):
                if phase != 'ready': raise
        time.sleep(1)
    raise TimeoutError('service readiness did not complete')

def performance(url):
    all_rows = [json.loads(s) for s in (inputs/'requests.jsonl').read_text().splitlines()]
    n = 64 if phase == 'warmup' else 1024
    rows = all_rows[:1] if phase == 'warmup' else all_rows
    result=[]
    for row in rows:
        ids=row['prompt']
        assert len(ids)==130048
        body=dict(model=model_name,prompt=ids,temperature=0.,max_tokens=n,ignore_eos=True,
                  return_token_ids=True,stream=True,stream_options={'include_usage':True})
        events=[]; tokens=[]; usage=None; done=False; finish=None
        start=time.perf_counter_ns()
        with fetch(url+'/v1/completions',body,timeout=1800) as response:
            for raw in response:
                now=time.perf_counter_ns()
                if not raw.startswith(b'data:'): continue
                data=raw[5:].strip()
                if data==b'[DONE]':
                    done=True; break
                event=json.loads(data)
                if 'error' in event: raise RuntimeError(str(event['error'])[:600])
                usage=event.get('usage') or usage
                for ch in event['choices']:
                    if ch.get('prompt_token_ids') is not None:
                        assert ch['prompt_token_ids']==ids
                    chunk=ch.get('token_ids') or []
                    if chunk:
                        events.append((now-start,len(chunk)))
                        tokens.extend(chunk)
                    finish=ch.get('finish_reason') or finish
        assert done and finish=='length' and usage['prompt_tokens']==130048 and usage['completion_tokens']==len(tokens)==n
        tpot=(events[-1][0]-events[0][0])/1e6/(n-1)
        rec=dict(id=row['id'],tpot_ms=tpot,ttft_ms=events[0][0]/1e6,events_ns_and_counts=events,
                 output_ids=tokens,usage=usage)
        append(private_dir/(phase+'.jsonl'),rec)
        print(row['id'],round(tpot,4),flush=True); result.append(tpot)
    return {'scenarios':{'longbench':{'workload':'longbench-127k-1k','requests':len(rows),'successes':len(result),
            'tpot':statistics.median(result),'units':{'tpot':'ms/token'}}}}

if phase=='precheck':
    assert hashlib.sha256((inputs/'requests.jsonl').read_bytes()).hexdigest()=='3bd0c87cab8f132cb64350b308a454f21f43c2c83daa6d9b6543660909bf94ac'
    assert (model_path/'model.safetensors.index.json').is_file()
    subprocess.run([str(root/'scorer/bin/python'),str(Path(__file__).with_name('quality.py')),'check'],
                   env=dict(os.environ,PYTHONNOUSERSITE='1',CUDA_VISIBLE_DEVICES='',HF_DATASETS_OFFLINE='1',HF_HUB_OFFLINE='1'), check=True)
    write(result_path,{'status':'completed','passed':True})
elif phase=='service':
    serve()
elif phase=='stop':
    info=json.loads(receipt.read_text())
    assert info['binding']==request
    drain(receipt, info)
    write(result_path,{'status':'completed','binding':info['binding'],'cleanup_complete':True})
else:
    info,url=bind()
    if phase=='ready':
        body=dict(ready=True,ownership='local_process_domain',owner_pid=info['pid'],loaded_root=info['loaded_root'],loaded_revision=info['loaded_revision'])
    elif phase in ('measure','warmup'):
        body=performance(url)
    elif phase=='quality':
        output=private_dir/'accuracy.json'
        subprocess.run([str(root/'scorer/bin/python'),str(Path(__file__).with_name('quality.py')),url,model_name,str(output)],
            env=dict(os.environ,PYTHONNOUSERSITE='1',CUDA_VISIBLE_DEVICES='',HF_DATASETS_OFFLINE='1',HF_HUB_OFFLINE='1'),check=True)
        body=json.loads(output.read_text())
    else: raise ValueError(phase)
    write(result_path,{'status':'completed','binding':info['binding'],**body})
