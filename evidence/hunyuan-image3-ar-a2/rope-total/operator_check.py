"""Compare every output byte with the submitted shared-factor implementation."""
import ast
import hashlib
import json
import sys
from pathlib import Path
import torch

def module(tree):
    path=tree/"vllm_omni/model_executor/models/hunyuan_image3/hunyuan_image3.py"
    node=next(n for n in ast.parse(path.read_text()).body if getattr(n,"name",None)=="HunyuanImage3RotaryEmbedding")
    env={"torch":torch,"nn":torch.nn}
    exec("from __future__ import annotations\n"+ast.unparse(node),env)
    return env[node.name]

def check(a,b):
    assert a.shape==b.shape and a.dtype==b.dtype
    assert torch.equal(a.contiguous().view(torch.uint8),b.contiguous().view(torch.uint8))

w=Path(sys.argv[1]); group=sys.argv[2]; device=sys.argv[3]
if device!="cpu":
    import torch_npu
ref=module(w/("stock" if group=="stack" else "stack"))(128).to(device)
opt=module(w/group)(128).to(device)
gen=torch.Generator().manual_seed(81)
ncase=0
with torch.inference_mode():
    for n in (1,8,31,127,1243,2048):
        ids=torch.arange(n,device=device)+17
        for coord in (ids,torch.stack([ids,ids,ids]),torch.stack([ids,ids*3-131,ids//2+9])):
            for dtype in (torch.float32,torch.float16,torch.bfloat16):
                for qh,kh in ((8,2),(1,1)):
                    qsz,ksz=qh*128,kh*128
                    packed=torch.randn(n,qsz+2*ksz,generator=gen).to(dtype)
                    packed[:,0]=0.0
                    packed[:,64]=-0.0
                    packed=packed.to(device)
                    q,k,v=packed.split((qsz,ksz,ksz),dim=-1)
                    out=ref(coord,q,k) if group=="stack" else ref.apply_packed(ref.prepare_factors(coord,dtype),packed,qsz,ksz)[:2]
                    for td in {dtype,torch.float32,torch.bfloat16}:
                        prepared=opt.prepare_factors(coord,td)
                        actual=opt(prepared,q,k)
                        for a,b in zip(out,actual): check(a,b)
                        if hasattr(opt,"apply_packed"):
                            aq,ak,av=opt.apply_packed(prepared,packed,qsz,ksz)
                            for a,b in zip((*out,v),(aq,ak,av)): check(a,b)
                            assert aq.is_contiguous() and ak.is_contiguous() and av.stride()==v.stride()
                            if group=="views":
                                vq,vk,vv=opt.apply_packed(prepared,packed,qsz,ksz,allow_views=True)
                                for x,y in ((aq,vq),(ak,vk),(av,vv)): check(x,y)
                                weight=torch.linspace(.5,1.5,128).to(dtype=dtype,device=device)
                                def norm(z):
                                    zh=z.view(n,-1,128)
                                    if device=="cpu":
                                        return torch.nn.functional.rms_norm(zh,(128,),weight,1e-5)
                                    return torch_npu.npu_rms_norm(zh,weight,epsilon=1e-5)[0]
                                check(norm(aq),norm(vq)); check(norm(ak),norm(vk))
                    ncase+=1
rec={"candidate":group,"device":device,"tested_layout_position_length_dtype_combinations":ncase,"packed_qk":hasattr(opt,"apply_packed"),"all_outputs_byte_exact":True}
(w/f"exact-{group}-{device.replace(':','')}.json").write_text(json.dumps(rec,indent=2)+"\n")
print(rec)
