"""Check the changed mRoPE operators against the pinned upstream implementations."""
from __future__ import annotations

import argparse
import ast
import json
import statistics
import time
from pathlib import Path
from types import SimpleNamespace

import torch


def from_checkout(tree, name, method=None):
    source = (Path(tree) / "vllm_omni/model_executor/models/hunyuan_image3/hunyuan_image3.py").read_text()
    cls = next(item for item in ast.parse(source).body if isinstance(item, ast.ClassDef) and item.name == name)
    node = next(item for item in cls.body if getattr(item, "name", None) == method) if method else cls
    namespace = {"torch": torch, "nn": torch.nn}
    exec("from __future__ import annotations\n" + ast.unparse(node), namespace)
    return namespace[node.name]


def positions(tree, candidate):
    inputs = SimpleNamespace(_mrope_img_token_id=11, _mrope_boi_token_id=12, _mrope_eoi_token_id=13,
                             _mrope_joint_img_sep_token_id=14, _timestep_token_id=15)
    funcs = [from_checkout(t, "HunyuanImage3ForConditionalGeneration", "get_mrope_input_positions")
             for t in (tree,candidate)]
    mm = SimpleNamespace(data=SimpleNamespace(get_data=lambda: {"vae_token_grid_hw": torch.tensor([2, 2]),
                                                                 "vit_spatial_shapes": torch.tensor([2, 2])}))
    cases = [([77]*n, None) for n in (1,8,32,511,1243,2048,4096)]
    cases.extend([([11,13,14,15],None),
                  ([77,12,20,21,15,11,11,11,11,14,11,11,11,11,13,77],[mm])])
    checks = 0
    for tokens,features in cases:
        for start,end in ((0,None),(0,len(tokens)),(1,len(tokens)),(len(tokens),len(tokens))):
            a,b = [fn(inputs,tokens,features,context_len=start,seq_len=end) for fn in funcs]
            assert all(torch.equal(x,y) and x.dtype==y.dtype and x.stride()==y.stride() for x,y in zip(a,b))
            checks += 1
    return {"checked":checks,"exact_positions_delta_strides":True}


def rope(tree, candidate):
    import torch_npu
    device = torch.device("npu:0")
    ops = [from_checkout(t,"HunyuanImage3RotaryEmbedding")(128).to(device) for t in (tree,candidate)]
    torch.manual_seed(197)
    shapes = (1,8,31,127,1243,2048)
    count = 0
    for n in shapes:
        ids = torch.arange(n,dtype=torch.long,device=device) + 16
        for coords in (ids,torch.stack([ids,ids,ids]),torch.stack([ids,ids*2-5,ids//3+4])):
            for dtype in (torch.bfloat16, torch.float16, torch.float32):
                # Q/K slices mirror packed TP4 QKV projection, including noncontiguous row strides.
                packed = torch.randn(n, (8+2+2)*128, device=device, dtype=dtype)
                q, k, _ = packed.split((8*128,2*128,2*128),dim=-1)
                ref = ops[0](coords,q,k)
                factors = ops[1].cos_sin(coords)
                for out in (ops[1](coords,q,k),ops[1](factors,q,k)):
                    assert all(torch.equal(x.contiguous().view(torch.uint8),y.contiguous().view(torch.uint8))
                               for x,y in zip(ref,out))
                count += 1
    return {"checked":count,"exact_query_and_key_bytes":True}


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("operation",choices=["positions","rope"])
    ap.add_argument("baseline")
    ap.add_argument("candidate")
    ap.add_argument("out")
    args=ap.parse_args()
    with torch.inference_mode():
        result=globals()[args.operation](args.baseline,args.candidate)
    Path(args.out).write_text(json.dumps(result,indent=2))
    print(result)
