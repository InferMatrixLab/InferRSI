"""Compare pinned and patched H3 image VAE tile assembly on CPU, including independent simulated decoder outputs."""
import argparse
import ast
import json
import math
import sys
from collections.abc import Sequence
from pathlib import Path

import torch


def load_functions(path):
    wanted = {"_blend", "_assemble_tiles", "_assemble_decode_rows", "_split_tiles"}
    nodes = [node for node in ast.parse(path.read_text(encoding="utf-8")).body
             if isinstance(node, ast.FunctionDef) and node.name in wanted]
    if len(nodes) != len(wanted):
        raise ValueError("Supply image_vae.py from the E8 patched source tree")
    namespace = dict(torch=torch, math=math, Sequence=Sequence, MINIMAX_H3_IMAGE_VAE_RATIO=16)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


def run_case(ns, tile_h, tile_w, oy, ox, prefix, dtype, strided):
    generator = torch.Generator(device="cpu").manual_seed(8612)
    def sample():
        shape = (*prefix, tile_h, tile_w * (2 if strided else 1))
        # Independent tiles expose wrong neighbor choices, including at corners.
        tensor = torch.randn(shape, generator=generator, device="cpu", dtype=dtype)
        return tensor[..., ::2] if strided else tensor
    rows = [[sample() for _ in range(len(ox) + 1)] for _ in range(len(oy) + 1)]
    blend = ns["_blend"]
    counts = {}
    def counted(a, b, n, dim):
        counts[key] += 1
        return blend(a, b, n, dim)
    ns["_blend"] = counted
    try:
        results = []
        for key in ("_assemble_tiles", "_assemble_decode_rows"):
            counts[key] = 0
            results.append(ns[key](rows, oy, ox))
    finally:
        ns["_blend"] = blend
    baseline, candidate = results
    bits = torch.int32 if dtype == torch.float32 else torch.int16
    if not torch.equal(baseline.view(bits), candidate.view(bits)):
        raise AssertionError(f"Byte differences for {oy=}, {ox=}, {dtype=}, {strided=}")
    return dict(grid=[len(rows),len(rows[0])], output=list(baseline.shape), dtype=str(dtype),
                strided=strided, blend_calls=list(counts.values()), byte_equal=True)


def main():
    base = Path(__file__).absolute().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("source",nargs="?",type=Path,
        default=base/"e8-cpu-check/vllm_omni/diffusion/models/minimax_h3/image_vae.py")
    args = parser.parse_args()
    torch.set_num_threads(2)
    ns = load_functions(args.source)
    cases = []
    for dtype in (torch.float32, torch.bfloat16, torch.float16):
        for oy, ox in (([], []), ([],[5,5,3]), ([6,4],[]), ([6,3,7],[5,2,7,4,4]),
                       ([13,10],[17,18,4,9]), ([3,1],[1,1,1,1,1])):
            cases.append(run_case(ns,16,24,oy,ox,(2,3,1),dtype,True))
    split = ns["_split_tiles"]
    for h,w,ch in ((608, 1008, 3), (4096, 4096, 1)):
        cases.append(run_case(ns,256,256,split(h,256,64)[2],split(w,256,64)[2],
                              (1,ch,1),torch.bfloat16,False))
    print(json.dumps(cases,indent=2))


if __name__ == "__main__":
    main()
