"""PRIVATE GPU DIAGNOSTIC, NOT LAUNCHED BY AUTHOR.
Requires exactly one assigned visible GPU. Real predictor weights; generated
inputs are explicitly synthetic unless --inputs supplies captured CPU tensors.
No serving/quality/performance claim. --compile is optional and expensive.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--expected-sha', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--inputs', type=Path, help='torch file: hidden[64,H], layer0_embed[64,H], optional history[64,15]')
    parser.add_argument('--compile', action='store_true')
    parser.add_argument('--cpu-load-smoke', action='store_true', help='CPU-only construction/loading and B1 interface smoke; no CUDA calls')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--graph', action='store_true')
    parser.add_argument('--iterations', type=int, default=20)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Refusing overwrite')
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=args.repo, text=True).strip()
    if subprocess.check_output(['git','status','--porcelain'],cwd=args.repo,text=True).strip():
        raise ValueError('Source checkout dirty before diagnostic')
    source_file = Path(__file__).resolve()
    script_sha = digest(source_file)
    if actual != args.expected_sha:
        raise ValueError('Unexpected source revision')
    visible = os.environ.get('CUDA_VISIBLE_DEVICES', '')
    if not args.cpu_load_smoke and (not visible or ',' in visible):
        raise ValueError('Set exactly one reserved CUDA_VISIBLE_DEVICES explicitly')
    import sys
    sys.path.insert(0, str(args.repo))
    import torch
    from safetensors import safe_open
    from transformers.models.qwen3_omni_moe.configuration_qwen3_omni_moe import Qwen3OmniMoeTalkerCodePredictorConfig
    from vllm_omni.model_executor.models.common.qwen3_code_predictor import CodePredictorWrapper, CodePredictorWrapperConfig
    if not args.cpu_load_smoke and torch.cuda.device_count() != 1:
        raise ValueError('Exactly one visible GPU required')
    torch.manual_seed(args.seed)
    cfg = json.loads((args.checkpoint / 'config.json').read_text())['talker_config']['code_predictor_config']
    cp = Qwen3OmniMoeTalkerCodePredictorConfig(**cfg)
    vcfg = SimpleNamespace(model_config=SimpleNamespace(stage_connector_config={'extra': {}}),
                           scheduler_config=SimpleNamespace(max_num_seqs=64), additional_config={})
    # CPU construction avoids allocating any full Talker/Thinker weights.
    wrapper = CodePredictorWrapper(vllm_config=vcfg, cp_config=cp,
                                   wrapper_config=CodePredictorWrapperConfig()).to(dtype=torch.bfloat16)
    weights = []
    names = []
    for shard in sorted(args.checkpoint.glob('*.safetensors')):
        with safe_open(shard, framework='pt', device='cpu') as stream:
            for name in stream.keys():
                if name.startswith('talker.code_predictor.'):
                    tensor = stream.get_tensor(name)
                    names.append({'name': name, 'shape': list(tensor.shape), 'dtype': str(tensor.dtype),
                                  'sha256': hashlib.sha256(tensor.contiguous().view(torch.uint8).numpy().tobytes()).hexdigest()})
                    weights.append((name.removeprefix('talker.code_predictor.'), tensor))
    if not weights:
        raise ValueError('No predictor weights found')
    weight_manifest_digest = hashlib.sha256(json.dumps(names,sort_keys=True).encode()).hexdigest()
    loaded = wrapper.load_weights(weights)
    missing = set(dict(wrapper.named_parameters())) - set(loaded)
    if missing:
        raise ValueError('Unloaded predictor parameters: ' + repr(sorted(missing)))
    del weights
    if args.cpu_load_smoke:
        torch.set_num_threads(1)
        wrapper.eval()
        wrapper._kv_cache_enabled = True
        wrapper._ensure_buffers(torch.device('cpu'), torch.bfloat16, 1)
        wrapper._ensure_kv_steps(torch.device('cpu'))
        with torch.inference_mode():
            ids = torch.zeros(1, dtype=torch.long)
            embedding = wrapper.model.codec_embedding[0](ids)
            inputs = torch.zeros(1, 17, cp.hidden_size, dtype=torch.bfloat16)
            inputs[:, 1] = embedding
            full = wrapper.model(inputs, torch.arange(17)[None])
            positions, mask = wrapper._kv_steps[1]
            cached = wrapper.model.forward_cached(inputs[:, :2], positions[None],
                                                  wrapper._kv_views(1), positions, mask)
            logits = wrapper.lm_head[0](cached[:, -1])
        result = {'status': 'CPU_LOAD_INTERFACE_SMOKE', 'source_sha': actual,
                  'loaded_parameter_count': len(loaded), 'missing_parameters': sorted(missing),
                  'checkpoint_tensors': names, 'embedding_shape': list(embedding.shape),
                  'full_shape': list(full.shape), 'cached_shape': list(cached.shape),
                  'logits_shape': list(logits.shape), 'dtype': str(full.dtype),
                  'finite': bool(torch.isfinite(full).all() and torch.isfinite(cached).all() and torch.isfinite(logits).all()),
                  'scope': 'CPU actual predictor weight loading/interface only; no GPU or numerical equivalence qualification'}
        if subprocess.check_output(['git','status','--porcelain'],cwd=args.repo,text=True).strip():
            raise ValueError('Source checkout dirty after CPU smoke')
        if subprocess.check_output(['git','rev-parse','HEAD'],cwd=args.repo,text=True).strip() != actual:
            raise ValueError('Source changed during CPU smoke')
        result.update(script_sha256=script_sha, seed=args.seed, weight_manifest_sha256=weight_manifest_digest)
        args.output.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps({k: v for k, v in result.items() if k != 'checkpoint_tensors'}))
        return
    wrapper = wrapper.cuda().eval()
    wrapper._kv_cache_enabled = True
    wrapper._model_dtype = torch.bfloat16
    wrapper._ensure_buffers(torch.device('cuda'), torch.bfloat16, 64)
    wrapper._ensure_kv_steps(torch.device('cuda'))
    for layer in wrapper.model.layers:
        layer.self_attn.use_short_kv_attention = False
    full_forward = wrapper.model.forward
    kv_forward = wrapper.model.forward_cached
    if args.compile:
        torch._dynamo.config.cache_size_limit = max(128, torch._dynamo.config.cache_size_limit)
        full_forward = torch.compile(full_forward, dynamic=False, options={'epilogue_fusion': False})
        kv_forward = torch.compile(kv_forward, dynamic=False, options={'epilogue_fusion': False})
    if args.inputs:
        supplied = torch.load(args.inputs, map_location='cpu', weights_only=True)
        hidden, embed = supplied['hidden'], supplied['layer0_embed']
        history = supplied.get('history')
    else:
        gen = torch.Generator(device='cpu').manual_seed(args.seed)
        hidden = torch.randn(64, cp.hidden_size, generator=gen)
        embed = torch.randn(64, cp.hidden_size, generator=gen)
        history = None
    if hidden.shape != (64, cp.hidden_size) or embed.shape != hidden.shape:
        raise ValueError('Require64 fixed rows; C1 uses the first identical row')
    hidden, embed = hidden.cuda().bfloat16(), embed.cuda().bfloat16()
    if history is not None:
        if history.shape != (64, 15) or bool(((history < 0) | (history >= cp.vocab_size)).any()):
            raise ValueError('Invalid supplied code history')
        history = history.cuda().long()
    import statistics
    if args.iterations < 3:
        raise ValueError('Require at least3 retained iterations')
    if history is None:
        gen = torch.Generator(device='cpu').manual_seed(args.seed + 1)
        history = torch.randint(cp.vocab_size, (64,15), generator=gen).cuda()
    report = {'status':'COMPONENT_TIMING_ONLY', 'source_sha':actual,
              'compiled':args.compile, 'cuda_graph':args.graph,
              'input_source':'captured' if args.inputs else 'synthetic fixed Gaussian hidden/embed and random teacher codes',
              'scope':'Device-only predictor transformer,15 heads and output torch.stack allocation/materialization; teacher-history embedding assembly, KV cache reset, sampler, Talker and codec excluded. Not service latency or quality.',
              'config_sha256':digest(args.checkpoint/'config.json'), 'rows':[]}
    with torch.inference_mode():
        for batch in (1,64):
            buf = torch.zeros(batch,17,cp.hidden_size,device='cuda',dtype=torch.bfloat16)
            buf[:,0] = hidden[:batch]
            buf[:,1] = embed[:batch]
            for step in range(1,15):
                buf[:,step+1] = wrapper.model.codec_embedding[step-1](history[:batch,step-1])
            pos = {length:torch.arange(length,device='cuda')[None].expand(batch,-1) for length in range(2,18)}
            caches = wrapper._kv_views(batch)
            for mode in ('full','prefix','kv'):
                def forward():
                    logits=[]
                    for step in range(1,16):
                        if mode == 'kv':
                            positions,mask=wrapper._kv_steps[step]
                            lo=0 if step==1 else step
                            states=kv_forward(buf[:,lo:step+1],positions[None].expand(batch,-1),caches,positions,mask)[:,-1]
                        else:
                            length=17 if mode=='full' else step+1
                            states=full_forward(buf[:,:length],pos[length])[:,step]
                        logits.append(wrapper.lm_head[step-1](states))
                    return torch.stack(logits,1)
                for _ in range(3):
                    wrapper._kv_buf.zero_()
                    result=forward()
                torch.cuda.synchronize()
                graph=None
                if args.graph:
                    wrapper._kv_buf.zero_()
                    graph=torch.cuda.CUDAGraph()
                    with torch.cuda.graph(graph):
                        result=forward()
                    launch=graph.replay
                else:
                    launch=forward
                timings=[]
                for _ in range(args.iterations):
                    wrapper._kv_buf.zero_() # state restoration outside event interval
                    start,end=torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True)
                    start.record()
                    latest=launch()
                    end.record()
                    end.synchronize()
                    timings.append(start.elapsed_time(end))
                if graph is None:
                    result=latest
                report['rows'].append({'batch':batch,'path':mode,'milliseconds':timings,
                                       'median_ms':statistics.median(timings),
                                       'finite':bool(torch.isfinite(result).all()),
                                       'output_shape':list(result.shape)})
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=args.repo,text=True).strip()!=actual:
        raise ValueError('Source changed during diagnostic')
    if subprocess.check_output(['git','status','--porcelain'],cwd=args.repo,text=True).strip():
        raise ValueError('Source checkout dirty after diagnostic')
    if digest(source_file) != script_sha:
        raise ValueError('Diagnostic script changed during run')
    report.update(script_sha256=script_sha, seed=args.seed, weight_manifest_sha256=weight_manifest_digest, input_sha256=digest(args.inputs) if args.inputs else None)
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')

if __name__ == '__main__':
    main()
