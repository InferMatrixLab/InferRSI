import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve();sys.path.insert(0,str(root/'src'))
from inferrsi.knowledge_operations import KnowledgeReader
reader=KnowledgeReader(); cg='inferrsi.common.skills.cgroup_resource_controls'
rows=[]
for opts in ({},{'relevance':'cgroupv2','context_bytes':262144},{'query':'stat.loc','relevance':'cgroupv2'},{'relevance':'gpu','backend':'ascend'},{'ids':[cg],'relevance':'ram','context_bytes':262144},{'ids':[cg],'relevance':'ram','context_bytes':1}):
    raw=json.dumps(reader.collect(**opts),sort_keys=True,ensure_ascii=False).encode()
    rows.append({'options':opts,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})
print(json.dumps(rows,indent=2))
