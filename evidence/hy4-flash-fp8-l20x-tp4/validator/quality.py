import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import urllib.request
import urllib.error

from evalscope.api.registry import get_benchmark
from evalscope.config import TaskConfig

root=Path(os.environ['HY4_CAMPAIGN'])/'inputs'
raw=(root/'aime26/aime2026.jsonl').read_bytes()
assert hashlib.sha256(raw).hexdigest()=='52822957957a3f577d1e9706c36a66a8108a3f99b6aff424cfb72dff0094a9ee'
assert importlib.metadata.version('evalscope')=='1.15.0'
rows=[json.loads(line) for line in raw.splitlines() if line.strip()]
adapter=get_benchmark('aime26',TaskConfig(model='hy4',datasets=['aime26'],seed=42,
                        dataset_args={'aime26':{'dataset_id':str(root/'aime26')}}))
samples=adapter.load_dataset()['default']
assert len(samples)==len({r['id'] for r in rows})==30
pairs=[]
for row,s in zip(rows,samples,strict=True):
    prompt=s.input if isinstance(s.input,str) else s.input[-1].content
    assert row['problem'] in prompt and s.target==str(row['answer'])
    pairs.append((row,prompt,s.target))
if sys.argv[1]=='check': sys.exit(0)
url,model,output=sys.argv[1:]
correct=0
for row,prompt,target in pairs:
    body=dict(model=model,messages=[{'role':'user','content':prompt}],temperature=0.9,top_p=1.,top_k=-1,max_tokens=131072)
    req=urllib.request.Request(url+'/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=7200) as resp: result=json.load(resp)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'HTTP {exc.code}: {exc.read(2048)}') from exc
    choice=result['choices'][0]
    assert choice['finish_reason'] in ('stop','length') and result['model']==model and result['usage']['completion_tokens']>0
    prediction=choice['message']['content'] or ''
    extracted=adapter.extract_answer(prediction,None)
    score=adapter.match_score(prediction,extracted,target,None)
    ok=score.value['acc']
    assert ok in (0.,1.)
    correct+=int(ok)
    with Path(output).with_suffix('.jsonl').open('a') as stream:
        stream.write(json.dumps(dict(id=row['id'],correct=ok,target=target,extracted=extracted,
                         response=result, prompt=prompt),ensure_ascii=False)+'\n')
    print(row['id'],int(ok),correct,flush=True)
Path(output).write_text(json.dumps(dict(dataset='AIME2026',scorer='EvalScope-1.15.0-aime26',
                                        samples=30,correct=correct)))
