import json
import sys
from pathlib import Path
w=Path(sys.argv[1]); group=sys.argv[2]
d=next((w/f"runs-{group}").glob("*/*/trial-001/result.json")).parents[2]
def read(p): return json.loads(p.read_text())
cal=read(w/"anchor-1.json")
target=cal["round_tokens"][0]
held=cal["held_out_token_ids"]
assert len(target)==8 and len(held)==1 and all(len(t)==32 for t in [*target.values(),*held.values()])
files=sorted(d.glob("*/trial-*/result.json"))
assert len(files)==6
for p in files:
    row=read(p)
    assert len(row["samples"])==3 and row["round_tokens"]==[target]*5 and row["held_out_token_ids"]==held,p
print("30/30 full batches and 6/6 held-outs identical to the independent RoPE calibration")
control=2048
expected={"budget1024":1024,"budget4096":4096,"prefix":2048}[group]
for path in files:
    rec=read(path); candidate=path.parent.parent.name=="candidate"
    assert rec["token_budget"]==(expected if candidate else control)
    assert bool(rec["cache_enabled"])==(candidate and group=="prefix")
    if group=="prefix":
        assert len(rec["prefix_batches"])==5
        for batch in rec["prefix_batches"]:
            if candidate:
                assert batch["prime_cached"]==0,batch
                assert all(isinstance(x,int) and 0<x<=rec["prefix_length"] for x in batch["cached"]),batch
            else:
                assert all(x in (0,None) for x in [batch["prime_cached"],*batch["cached"]])
