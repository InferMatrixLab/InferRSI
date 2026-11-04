"""Bounded integration probe; comparisons are diagnostic, not quality gates."""
import argparse
import hashlib
import importlib.metadata
import inspect
import json
import os
from pathlib import Path

import torch
from nanovllm.qwen38.quant import FP8Linear

p = argparse.ArgumentParser()
p.add_argument('--output', required=True)
args = p.parse_args()
torch.manual_seed(670032)
assert torch.cuda.device_count() == 1
rows = []
for m, k, n in ((1, 128, 64), (31, 128, 64), (32, 128, 64),
                (1, 5120, 5120), (1, 5120, 17408), (1, 17408, 5120)):
    os.environ['NANOVLLM_FP8_GEMM'] = 'flashinfer'
    candidate = FP8Linear(k, n, device='cuda')
    os.environ['NANOVLLM_FP8_GEMM'] = 'triton'
    control = FP8Linear(k, n, device='cuda')
    candidate.weight.data.copy_(torch.randn(n, k, device='cuda').clamp(-4, 4).to(torch.float8_e4m3fn))
    candidate.weight_scale_inv.data.fill_(0.125)
    control.weight.data.copy_(candidate.weight)
    control.weight_scale_inv.data.copy_(candidate.weight_scale_inv)
    x = torch.randn(m, k, device='cuda', dtype=torch.bfloat16)
    with torch.inference_mode():
        a, b = control(x), candidate(x)
        assert torch.isfinite(a).all() and torch.isfinite(b).all()
        nrmse = ((a.float()-b.float()).square().mean().sqrt()/a.float().square().mean().sqrt()).item()
        # Warm on a side stream, capture, then replay after changing input bytes.
        stream = torch.cuda.Stream()
        stream.wait_stream(torch.cuda.current_stream())
        with torch.cuda.stream(stream):
            for _ in range(3): candidate(x)
        torch.cuda.current_stream().wait_stream(stream)
        graph = torch.cuda.CUDAGraph()
        with torch.cuda.graph(graph):
            captured = candidate(x)
        exact = []
        for _ in range(2):
            x.copy_(torch.randn_like(x))
            eager = candidate(x)
            graph.replay()
            torch.cuda.synchronize()
            exact.append(torch.equal(eager, captured))
        assert all(exact), 'Graph replay differs from eager for changed inputs'
        timing = {}
        for name, module in [('triton', control), ('flashinfer', candidate)]:
            for _ in range(3): module(x)
            start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
            start.record()
            for _ in range(20): module(x)
            end.record(); end.synchronize()
            timing[name] = start.elapsed_time(end)/20
        row = dict(shape=[m, k, n], diagnostic_nrmse=nrmse, graph_changed_inputs_exact=exact,
                   kernel_calls=candidate.kernel_calls, milliseconds=timing)
        rows.append(row)
        print(json.dumps(row), flush=True)
    del graph, candidate, control, x, a, b, captured, eager
    torch.cuda.empty_cache()

from flashinfer.gemm import fp8_blockscale_gemm_sm90
implementation = Path(inspect.getfile(inspect.unwrap(fp8_blockscale_gemm_sm90)))
result = dict(scope='operator_integration_not_model_quality_or_service_acceptance', rows=rows,
              versions={name: importlib.metadata.version(name) for name in ['torch', 'triton', 'flashinfer-python']},
              flashinfer_source_sha256=hashlib.sha256(implementation.read_bytes()).hexdigest())
Path(args.output).write_text(json.dumps(result, indent=2)+'\n')
