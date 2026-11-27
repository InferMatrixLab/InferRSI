"""One side of an isolated InferRSI trial on HunyuanImage-3.0."""
import argparse
import json
import statistics
import time
from pathlib import Path
from types import SimpleNamespace

import torch

from exact_ops import from_checkout


def measure(call, synchronize, repeats):
    for _ in range(3):
        call()
    synchronize()
    samples = []
    for _ in range(9):
        start = time.perf_counter()
        for _ in range(repeats):
            call()
        synchronize()
        samples.append((time.perf_counter()-start)/repeats)
    return samples


def run_positions(tree):
    fn=from_checkout(tree, "HunyuanImage3ForConditionalGeneration", "get_mrope_input_positions")
    model=SimpleNamespace(_mrope_img_token_id=11, _mrope_boi_token_id=12, _mrope_eoi_token_id=13,
                          _mrope_joint_img_sep_token_id=14, _timestep_token_id=15)
    prompts=[[77]*n for n in (1243,1241,1241,1240,1238,1242,1243,1239)]
    def call():
        for prompt in prompts:
            fn(model,prompt)
    times=measure(call,lambda:None,60)
    return {"component_rate":8/statistics.median(times),"seconds_per_eight_prompts":times}


def run_rope(tree, side):
    import torch_npu
    torch.manual_seed(197)
    op=from_checkout(tree, "HunyuanImage3RotaryEmbedding")(128).to("npu")
    cases={}
    for size in (8,1243):
        idx=torch.arange(size,device="npu",dtype=torch.long)
        positions=torch.stack([idx,idx,idx])
        q=torch.randn(size,8*128,device="npu",dtype=torch.bfloat16)
        k=torch.randn(size,2*128,device="npu",dtype=torch.bfloat16)
        def call():
            coords=op.cos_sin(positions) if side=="candidate" else positions
            for _ in range(32):
                op(coords,q,k)
        cases[str(size)]=measure(call,torch.npu.synchronize,3)
    seconds=sum(statistics.median(s) for s in cases.values())
    return {"component_rate":(8+1243)/seconds,"seconds_per_32_layers_by_size":cases}


if __name__=="__main__":
    p=argparse.ArgumentParser()
    for name in ("operation","tree","side","out"):
        p.add_argument(name)
    a=p.parse_args()
    with torch.inference_mode():
        result=run_positions(a.tree) if a.operation=="positions" else run_rope(a.tree,a.side)
    Path(a.out).write_text(json.dumps(result))
