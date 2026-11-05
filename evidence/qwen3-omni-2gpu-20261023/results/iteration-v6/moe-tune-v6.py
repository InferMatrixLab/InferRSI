#!<PATH_27> python3
"""L0/L1 synthetic BF16 MoE tile screen. NOT model quality or service evidence.
Native API and timing inspiration: vllm-project/vllm @
5df63a7203cdb9328d824a27b682e77c7b9928be,
benchmarks/kernels/benchmark_moe.py and fused_moe/fused_moe.py.
No installed files changed. Candidate output is for separate L3/L4 qualification.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import time


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--models', nargs='+', choices=['talker', 'thinker'], default=['talker', 'thinker'])
    p.add_argument('--batches', nargs='+', type=int, default=[1,2,4,8,16,32,64,128])
    p.add_argument('--rounds', type=int, default=9)
    p.add_argument('--replays', type=int, default=20)
    p.add_argument('--seed', type=int, default=20261024)
    a = p.parse_args()
    if a.output.exists():
        p.error('output must be new; never overwrite evidence')
    if a.rounds < 3 or a.replays < 1 or any(m < 1 for m in a.batches):
        p.error('invalid repeat or shape configuration')
    a.output.mkdir(parents=True)
    config_dir = a.output / 'candidate-configs'
    config_dir.mkdir()
    os.environ['VLLM_TUNED_CONFIG_FOLDER'] = str(config_dir.resolve())
    import torch
    import torch.nn.functional as F
    import vllm
    from vllm.model_executor.layers.fused_moe import override_config
    from vllm.model_executor.layers.fused_moe import fused_moe as fm
    torch.set_grad_enabled(False)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.cuda.set_device(0)  # caller must restrict visibility to the allocated GPU
    source = Path(fm.__file__)
    expected_source_sha256 = '21860340e4b409b01666e2ba0f0edae66b0f97b859756b174b573bab895cfaf7'
    if hashlib.sha256(source.read_bytes()).hexdigest() != expected_source_sha256:
        raise RuntimeError('Installed fused_moe source differs from reviewed pinned upstream')
    report = dict(status='INCONCLUSIVE', level='L0/L1', service_gain_claim=False,
                  source_url='https://github.com/vllm-project/vllm/blob/5df63a7203cdb9328d824a27b682e77c7b9928be/vllm/model_executor/layers/fused_moe/fused_moe.py',
                  source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  torch=torch.__version__, vllm=vllm.__version__, device=torch.cuda.get_device_name(),
                  cuda=torch.version.cuda, seed=a.seed, rounds=a.rounds, replays=a.replays,
                  tolerance={'rtol':0.02,'atol':0.02}, rows=[],
                  limits=['Synthetic weights/routes; not checkpoint or service evidence',
                          'CUDA graph steady state; excludes routing selection and host overhead',
                          'Winner selection on screening samples requires fresh confirmation'])
    def save():
        (a.output/'results.json').write_text(json.dumps(report, indent=2)+'\n')
    save()
    def capture(fn):
        stream = torch.cuda.Stream()
        stream.wait_stream(torch.cuda.current_stream())
        with torch.cuda.stream(stream):
            for _ in range(3): fn()
        torch.cuda.current_stream().wait_stream(stream)
        torch.cuda.synchronize()
        graph = torch.cuda.CUDAGraph()
        with torch.cuda.graph(graph, stream=stream):
            for _ in range(10): out = fn()
        for _ in range(5): graph.replay()
        torch.cuda.synchronize()
        return graph, out
    def timing(graph):
        start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
        start.record()
        for _ in range(a.replays): graph.replay()
        end.record(); end.synchronize()
        return start.elapsed_time(end)*1000/(10*a.replays)
    for model in a.models:
        E,K,N,topk = (128,1024,384,6) if model=='talker' else (128,2048,768,8)
        gen = torch.Generator(device='cuda').manual_seed(a.seed)
        w1=torch.randn((E,2*N,K), device='cuda',dtype=torch.bfloat16,generator=gen)/math.sqrt(K)
        w2=torch.randn((E,K,N), device='cuda',dtype=torch.bfloat16,generator=gen)/math.sqrt(N)
        selections={}
        for M in a.batches:
            base=fm.get_default_config(M,E,N,K,topk,None)
            candidates=[base]
            # Bounded tile/stage shortlist; identical native arithmetic and precision.
            for bm,bn,bk,warps,stages in [(16,64,64,4,3),(16,64,128,4,3),(16,128,64,4,3),
                    (16,128,128,4,3),(16,64,128,4,4),(32,64,64,4,3),(32,128,64,4,3),
                    (32,64,128,4,3),(64,64,64,4,3),(64,128,64,4,3),(16,128,64,8,3)]:
                c=dict(BLOCK_SIZE_M=bm,BLOCK_SIZE_N=bn,BLOCK_SIZE_K=bk,GROUP_SIZE_M=1,SPLIT_K=1,
                       num_warps=warps,num_stages=stages)
                if c not in candidates: candidates.append(c)
            scores={i:[] for i in range(len(candidates))}
            for route in ['uniform','concentrated']:
                gen.manual_seed(a.seed+M+(0 if route=='uniform' else 10000))
                x=torch.randn((M,K), device='cuda',dtype=torch.bfloat16,generator=gen)
                logits=torch.randn((M,E),device='cuda',generator=gen)
                if route=='concentrated': logits[:, :topk]+=10
                vals,ids=logits.topk(topk,dim=-1)
                ids=ids.to(torch.int32); weights=vals.softmax(-1)
                # Independent reference preserves native BF16 intermediate rounding.
                refparts=torch.zeros((M,topk,K),device='cuda',dtype=torch.bfloat16)
                for e in ids.unique().tolist():
                    tokens,slots=torch.where(ids==e)
                    gu=(x[tokens].float()@w1[e].float().T).to(torch.bfloat16).float()
                    h=(F.silu(gu[:,:N])*gu[:,N:]).to(torch.bfloat16)
                    down=h.float()@w2[e].float().T
                    refparts[tokens,slots]=(down*weights[tokens,slots,None]).to(torch.bfloat16)
                ref=refparts.float().sum(1).to(torch.bfloat16)
                def fn(c):
                    with override_config(c):
                        return fm.fused_experts(x,w1,w2,weights,ids)
                baseline=fn(base)
                torch.testing.assert_close(baseline,ref,rtol=.02,atol=.02)
                bg,bo=capture(lambda: fn(base))
                for i,c in enumerate(candidates):
                    row=dict(model=model,M=M,E=E,K=K,N=N,topk=topk,route=route,config=c,
                             baseline_config=base,candidate_index=i)
                    try:
                        out=fn(c)
                        torch.testing.assert_close(out,ref,rtol=.02,atol=.02)
                        torch.testing.assert_close(out,baseline,rtol=.02,atol=.02)
                        row['max_abs_reference']=float((out.float()-ref.float()).abs().max())
                        row['max_abs_baseline']=float((out.float()-baseline.float()).abs().max())
                        cg,co=capture(lambda: fn(c))
                        bs,cs=[],[]
                        for r in range(a.rounds):
                            if r%2==0: b,t=timing(bg),timing(cg)
                            else: t,b=timing(cg),timing(bg)
                            bs.append(b); cs.append(t)
                        cg.reset(); del co,cg
                        ratio=[b/t for b,t in zip(bs,cs)]
                        row.update(status='PASS',baseline_us=bs,candidate_us=cs,
                                   paired_speedup=ratio,median_speedup=statistics.median(ratio))
                        scores[i].append(statistics.median(ratio))
                    except Exception as exc:
                        # CUDA corruption cannot safely be recovered in this process.
                        row.update(status='FAIL',error=repr(exc))
                        report['rows'].append(row); save()
                        raise
                    report['rows'].append(row); save()
                    print(json.dumps({k:row[k] for k in ['model','M','route','candidate_index','status','median_speedup']}),flush=True)
                bg.reset(); del bo,bg
            # Conservative screen selector: best worst-route ratio; baseline retained below 1.
            best=max(scores,key=lambda i:min(scores[i]) if len(scores[i])==2 else -1)
            if min(scores[best]) <= 1: best=0
            selections[str(M)]=candidates[best]
        filename=fm.get_config_file_name(E,N,None)
        (config_dir/filename).write_text(json.dumps(selections,indent=2)+'\n')
        del w1,w2
        torch.cuda.empty_cache()
    report['status']='PASS'
    report['scope']='Synthetic L0/L1 completed; candidate configs require independent confirmation and L3/L4'
    save()

if __name__=='__main__': main()
