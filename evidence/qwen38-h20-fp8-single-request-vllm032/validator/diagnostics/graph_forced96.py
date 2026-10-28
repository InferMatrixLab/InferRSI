"""Fixed-history, same-model numerical diagnosis; never an acceptance oracle."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import time

import torch

from nanovllm.qwen38.loader import load_checkpoint
from nanovllm.qwen38.runner import RequestRunner


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compare(a, b):
    if torch.equal(a, b):
        return {"exact": True, "max_abs": 0., "nrmse": 0.}
    a, b = a.float(), b.float()
    return {"exact": False, "max_abs": (a-b).abs().max().item(),
            "nrmse": ((a-b).square().mean().sqrt() /
                      b.square().mean().sqrt().clamp_min(1e-30)).item()}


def state_differences(a, b, length):
    diffs = []
    for i, (x, y) in enumerate(zip(a.layers, b.layers)):
        for field in ("key", "value", "conv", "recurrent"):
            left, right = getattr(x, field), getattr(y, field)
            if left is None or right is None:
                assert left is right
                continue
            if field in ("key", "value"):
                left, right = left[:, :, :length], right[:, :, :length]
            if not torch.equal(left, right):
                diffs.append({"layer": i, "field": field, **compare(left, right)})
    return diffs


def top(logits):
    values, indices = logits.float().topk(5)
    return {"ids": indices.tolist(), "logits": values.tolist(),
            "margin": (values[0]-values[1]).item(),
            "argmax": int(logits.argmax().item())}


def main():
    p = argparse.ArgumentParser()
    for name in ("model", "fixtures", "history", "source", "output"):
        p.add_argument("--"+name, required=True)
    args = p.parse_args()
    assert digest(args.fixtures) == 'f359c66f92b69d9a92a66564d8a087809dbc45b7e8b9e916229065806c4c188c'
    assert digest(args.history) == '7fcf761c8d664f40ecf4a5f08a83fcf4b362e4127ecc4c932fd9d5c4ceb6cb54'
    assert digest(Path(args.model)/'config.json') == '74227dd615bf1ea975aa676bdf355a0379858c12f394b5365cd9dfa5fc2c70bc'
    case = 'gsm8k/test/783'
    fixture = {r['id']:r for r in map(json.loads,Path(args.fixtures).read_text().splitlines())}[case]
    records = [r for r in map(json.loads,Path(args.history).read_text().splitlines())
               if r.get('phase')=='request' and r['index']==0]
    history = next(r['token_ids'] for r in records if r['arm']=='eager')
    graph_history = next(r['token_ids'] for r in records if r['arm']=='graph')
    steps, capacity = 96, 1024
    prompt = fixture['prompt']
    assert len(history)>steps and len(prompt)==149
    os.environ['NANOVLLM_CUDA_GRAPH']='1'
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x') as stream:
        def emit(**row):
            stream.write(json.dumps(row)+'\n');stream.flush()
            print(json.dumps({k:v for k,v in row.items() if k not in
                              ('compact_buffered_state_diff','buffered_graph_state_diff')}),flush=True)
        emit(phase='protocol',case=case,steps=steps,capacity=capacity,
             fixture_sha256=digest(args.fixtures),history_sha256=digest(args.history),
             observer_sha256=digest(__file__),
             source_hashes={str(f.relative_to(args.source)):digest(f)
                            for f in sorted(Path(args.source).glob('nanovllm/qwen38/*.py'))},
             torch=torch.__version__,device=torch.cuda.get_device_name(0),
             triton=importlib.metadata.version('triton'),
             scope='fixed_eager_history_same_model_no_quality_or_performance_claim')
        started=time.monotonic()
        model,report=load_checkpoint(args.model)
        emit(phase='loaded',elapsed_s=time.monotonic()-started,report=report)
        runner=RequestRunner(model,max_context_tokens=4096)
        runner.prewarm_graphs()
        graph=runner._acquire_graph_state(capacity)
        assert graph is not None
        captured=graph.reset_request_state()
        compact,buffered=model.new_state(),model.new_state(capacity)
        compact_match,graph_prefix_match=[],[]
        with torch.inference_mode():
            inputs=torch.tensor([prompt],dtype=torch.long,device='cuda')
            a=model(inputs,state=compact)[0,-1].clone()
            b=model(inputs,state=buffered)[0,-1].clone()
            c=model(inputs,state=captured)[0,-1].clone()
            for index in range(steps):
                if index:
                    token=history[index-1]
                    inp=torch.tensor([[token]],dtype=torch.long,device='cuda')
                    a=model(inp,state=compact)[0,-1].clone()
                    b=model(inp,state=buffered)[0,-1].clone()
                    c=graph.step(token,len(prompt)+index-1)[0,-1].clone()
                length=len(prompt)+index
                aa,bb,cc=top(a),top(b),top(c)
                compact_match.append(aa['argmax']==history[index])
                if index<=81:
                    graph_prefix_match.append(cc['argmax']==graph_history[index])
                emit(phase='step',index=index,position=length-1,
                     teacher_token=None if index==0 else history[index-1],
                     compact=aa,buffered=bb,graph=cc,
                     compact_buffered=compare(a,b),buffered_graph=compare(b,c),
                     compact_buffered_state_diff=state_differences(compact,buffered,length),
                     buffered_graph_state_diff=state_differences(buffered,captured,length))
        runner._graph_busy.discard(capacity)
        emit(phase='complete',verdict='INCONCLUSIVE',
             compact_history_matches=all(compact_match),
             graph_original_prefix_matches=all(graph_prefix_match),
             compact_history_mismatches=[i for i,x in enumerate(compact_match) if not x],
             graph_prefix_mismatches=[i for i,x in enumerate(graph_prefix_match) if not x],
             seconds=time.monotonic()-started,
             scope='numerical_diagnostic_not_task_quality_or_service_acceptance')


if __name__=='__main__':
    main()
