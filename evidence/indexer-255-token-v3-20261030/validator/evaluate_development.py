import gzip, hashlib, json, sys
from pathlib import Path
root, prep, out, arm = map(Path, sys.argv[1:])
root=root.resolve()
sys.path.insert(0, str(root/'src'))
from inferrsi.knowledge_operations import KnowledgeReader
from inferrsi._skill_selection import indexed_skill
rows=[]
for filename in ('development.json','negative-controls.json'):
    for case in json.loads((prep/'semantic-cases'/filename).read_text())['cases']:
        reader=KnowledgeReader()
        for path, expected in case.get('source_sha256',{}).items():
            assert hashlib.sha256((root/path).read_bytes()).hexdigest()==expected
        options=dict(query=case['query'],relevance=case['relevance'],limit=case['limit'],context_bytes=case['context_bytes'],**case['filters'])
        if str(arm)=='token': options['relevance_method']='weighted-token-v3'
        result=reader.collect(**options)
        ids=[i['id'] for i in result['items']]
        rank=next((i+1 for i,x in enumerate(ids) if x in case['relevant_ids']),None)
        complete=[]
        for context in result['contexts']:
            bundle=reader.read(context['ref'],revision=context['revision'])
            view={**bundle.view(),'authority':'package'}
            _,required,_=indexed_skill(reader.records()[view['id']],view,bundle.content)
            emitted={r['path']:r for r in context['resources']}
            assert all(p in emitted for p in required)
            assert all(r['content'].encode()==bundle.content[p] and r['sha256']==hashlib.sha256(bundle.content[p]).hexdigest() for p,r in emitted.items())
            if view['id'] in case['relevant_ids']: complete.append(view['id'])
        raw=json.dumps(result,ensure_ascii=False,sort_keys=True).encode()
        (out/(str(arm)+'-'+case['id']+'.json.gz')).write_bytes(gzip.compress(raw,mtime=0))
        rows.append(dict(id=case['id'],rank=rank,ids=ids,complete_relevant=complete,output_bytes=len(raw),context_bytes=result['context_bytes'],context_omissions=result['context_omissions'],sha256=hashlib.sha256(raw).hexdigest()))
(out/(str(arm)+'-summary.json')).write_text(json.dumps(rows,indent=2)+'\n')
print(json.dumps([{'id':r['id'],'rank':r['rank'],'complete':len(r['complete_relevant'])} for r in rows]))
