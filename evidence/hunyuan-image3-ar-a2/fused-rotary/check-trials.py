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
