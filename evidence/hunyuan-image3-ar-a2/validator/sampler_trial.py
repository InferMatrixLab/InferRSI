"""Measure the Hunyuan MRv2 logits transform separately from the base sampler."""
import argparse
import ast
import hashlib
import json
import statistics
import time
from pathlib import Path
from types import SimpleNamespace

import torch
import torch_npu  # registers the NPU backend

SOURCE = Path("vllm_omni/model_executor/models/hunyuan_image3/ar_sampler.py")
def load_call(repo):
    # Extract the unmodified method to avoid loading engine workers for this operator trial.
    path = repo / SOURCE
    cls = next(n for n in ast.parse(path.read_text()).body if isinstance(n, ast.ClassDef) and n.name == "HunyuanImage3ARSampler")
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "__call__")
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), method], type_ignores=[])
    ns = {"torch": torch}
    exec(compile(ast.fix_missing_locations(module), str(path), "exec"), ns)
    return ns["__call__"]

def main():
    p = argparse.ArgumentParser()
    p.add_argument("repo", type=Path)
    p.add_argument("weights", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--validate", action="store_true")
    args = p.parse_args()
    fn = load_call(args.repo)
    config = json.loads((args.weights / "config.json").read_text())
    tokens = {v["content"]:v["id"] for v in json.loads((args.weights/"tokenizer.json").read_text())["added_tokens"]}
    names = ["<boi>", "<eoi>", "<cfg>", "<img>", "<timestep>", "<joint_img_sep>", f"<img_size_{config.get('image_base_size',1024)}>"]
    ids = sorted({tokens[name] for name in names} | {tokens[f"<img_ratio_{i}>"] for i in range(37)})
    device = torch.device("npu:0")
    torch.npu.set_device(device)
    cases = {}
    for rows in ([1, 4, 8, 16, 31] if args.validate else [8, 16]):
        state = SimpleNamespace(model=SimpleNamespace(_is_comprehension=True), _blocked_ids=torch.tensor(ids,device=device),
                                _comprehension=torch.ones(rows+3,device=device,dtype=torch.bool), base_sampler=lambda logits,batch:logits)
        batch=SimpleNamespace(idx_mapping=torch.arange(rows-1,-1,-1,device=device))
        torch.manual_seed(731 + rows)
        cpu = torch.randn(rows,config["vocab_size"]).float()
        inp = cpu.to(device)
        expected = cpu.clone()
        expected[:,ids] = torch.finfo(expected.dtype).min
        got=fn(state,inp,batch)
        assert torch.equal(got.cpu(),expected)
        if args.validate:
            cases[str(rows)]={"exact_logits": True, "exact_argmax":torch.equal(expected.argmax(-1),got.argmax(-1).cpu())}
            assert cases[str(rows)]["exact_argmax"]
            continue
        for _ in range(40): fn(state,inp,batch)
        times=[]
        for _ in range(11):
            torch.npu.synchronize()
            start=time.perf_counter_ns()
            for _ in range(200): fn(state,inp,batch)
            torch.npu.synchronize()
            times.append((time.perf_counter_ns()-start)/200/1000)
        cases[str(rows)]={"batch_us":statistics.median(times),"samples_us":times}
    out={"cases":cases,"blocked_count":len(ids),"source_sha256":hashlib.sha256((args.repo/SOURCE).read_bytes()).hexdigest()}
    if not args.validate:
        out["sampler_rows_per_s"]=24e6 / sum(case["batch_us"] for case in cases.values())
    args.out.write_text(json.dumps(out,indent=2))
    print(out.get("sampler_rows_per_s","validated"))
if __name__=="__main__":
    main()
