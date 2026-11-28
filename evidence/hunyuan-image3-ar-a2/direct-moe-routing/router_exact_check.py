import json,sys,torch
from pathlib import Path
from vllm_omni.model_executor.models.hunyuan_image3.hunyuan_image3 import _hunyuan_image3_topk
device=sys.argv[1]; w=Path(__file__).resolve().parent; gen=torch.Generator().manual_seed(323)
count=0;rows=0
for n in (1,8,17,128,1243,2048):
 for dtype in (torch.bfloat16,torch.float16,torch.float32):
  for k in (1,8):
   for edge in ("random","ties","strided"):
    x=torch.randn(n,128 if edge=="strided" else 64,generator=gen).to(device)
    if edge=="strided":x=x[:,::2]
    if edge=="ties":
     x[0].zero_()
     if n>1:x[1,:k+1]=torch.linspace(10.,10.001,k+1,device=device)
    h=torch.empty(n,32,dtype=dtype,device=device)
    g=torch.softmax(x,dim=-1,dtype=torch.float32);val,ids=torch.topk(g,k,dim=-1)
    val=(val/val.sum(dim=-1,keepdim=True).clamp(min=1e-8)).to(dtype)
    packed=torch.cat((val.float(),ids.float()),dim=-1)
    expected=(packed[:,:k].contiguous(),packed[:,k:].to(torch.int32))
    res=_hunyuan_image3_topk(h,x,k,False)
    assert all(a.dtype==b.dtype and torch.equal(a.contiguous().view(torch.uint8),b.contiguous().view(torch.uint8)) for a,b in zip(expected,res)),(n,k,edge,dtype)
    count+=1;rows+=n
(w/("operator-"+device.replace(":","")+".json")).write_text(json.dumps(dict(cases=count,token_rows=rows,device=device,weight_bytes_and_expert_ids_exact=True)))
print(device,count,rows,"exact")
