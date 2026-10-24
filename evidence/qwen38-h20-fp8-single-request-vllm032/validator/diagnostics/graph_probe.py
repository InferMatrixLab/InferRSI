"""Bounded same-model diagnostic: compact eager / buffered eager / replay.

No benchmark or acceptance verdict. Teacher-forced inputs isolate numerical
differences from autoregressive divergence. Writes one durable row per phase.
"""
import argparse
import gc
import hashlib
import importlib.metadata
import json
import sys
import time
from pathlib import Path

import torch

from nanovllm.qwen38.graph import DecodeGraph
from nanovllm.qwen38.loader import load_checkpoint


def dependency_version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def compare(a, b):
    a, b = a.detach().float(), b.detach().float()
    return {"exact": torch.equal(a, b), "max_abs": (a - b).abs().max().item(),
            "nrmse": ((a-b).square().mean().sqrt() /
                      b.square().mean().sqrt().clamp_min(1e-30)).item()}


def state_summary(a, b, length):
    result = []
    for i, (x, y) in enumerate(zip(a.layers, b.layers)):
        for key in ("key", "value", "conv", "recurrent"):
            left, right = getattr(x, key), getattr(y, key)
            if left is None or right is None:
                assert left is right
                continue
            if key in ("key", "value"):
                left, right = left[:, :, :length], right[:, :, :length]
            item = compare(left, right)
            if not item["exact"]:
                result.append({"layer": i, "state": key, **item})
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--fixtures", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--steps", type=int, default=16)
    args = parser.parse_args()
    assert 1 <= args.steps <= 64
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x") as stream:
        def emit(**row):
            stream.write(json.dumps(row) + "\n")
            stream.flush()
            print(json.dumps({k: v for k, v in row.items()
                              if k not in ("state_diff", "layer_diff")}), flush=True)

        emit(phase="identity", python=sys.version, torch=torch.__version__,
             cuda=torch.version.cuda, device=torch.cuda.get_device_name(0),
             capability=torch.cuda.get_device_capability(0),
             dependencies={n: dependency_version(n) for n in
                           ("triton", "transformers", "flashinfer-python", "safetensors")})
        start = time.monotonic()
        model, report = load_checkpoint(args.model)
        emit(phase="loaded", seconds=time.monotonic()-start, report=report)
        fixtures = [json.loads(line) for line in Path(args.fixtures).read_text().splitlines()]
        ids = ("gsm8k/test/783", "gsm8k/test/1", "gsm8k/test/424")
        by_id = {row["id"]: row for row in fixtures}
        traces = {}
        handles = [layer.register_forward_hook(
            lambda _m, _a, y, i=i: traces.__setitem__(i, y.detach().clone()))
            for i, layer in enumerate(model.model.layers)]
        for case in ids:
            prompt = by_id[case]["prompt"]
            tokens = torch.tensor([prompt], device="cuda", dtype=torch.long)
            capacity = DecodeGraph.bucket_for(len(prompt)+256)
            compact, buffered, captured = model.new_state(), model.new_state(capacity), model.new_state(capacity)
            with torch.inference_mode():
                a = model(tokens, state=compact).clone()
                trace_a = dict(traces)
                b = model(tokens, state=buffered).clone()
                trace_b = dict(traces)
                c = model(tokens, state=captured).clone()
                emit(phase="prefill", case=case, prompt_tokens=len(prompt), capacity=capacity,
                     prompt_sha256=hashlib.sha256(json.dumps(prompt).encode()).hexdigest(),
                     compact_buffered=compare(a, b), buffered_repeated=compare(b, c),
                     top1=[int(x[0,-1].argmax()) for x in (a,b,c)],
                     layer_diff=[{"layer":i, **compare(trace_a[i], trace_b[i])}
                                 for i in trace_a if not torch.equal(trace_a[i], trace_b[i])],
                     state_diff=state_summary(compact, buffered, len(prompt)))
                graph = DecodeGraph(model, captured, len(prompt), capacity).capture()
                captured_traces = dict(traces)
                emit(phase="capture_restore", case=case,
                     state_diff=state_summary(buffered, captured, len(prompt)))
                for step in range(args.steps):
                    token = int(a[0,-1].argmax())
                    inp = torch.tensor([[token]], dtype=torch.long, device="cuda")
                    a = model(inp, state=compact).clone()
                    trace_a = dict(traces)
                    b = model(inp, state=buffered).clone()
                    trace_b = dict(traces)
                    c = graph.step(token, len(prompt)+step).clone()
                    emit(phase="decode", case=case, step=step, teacher_token=token,
                         compact_buffered=compare(a,b), buffered_graph=compare(b,c),
                         top1=[int(x[0,-1].argmax()) for x in (a,b,c)],
                         layer_diff=[{"layer":i, "compact_buffered":compare(trace_a[i], trace_b[i]),
                                      "buffered_graph":compare(trace_b[i], captured_traces[i])}
                                     for i in trace_a if not torch.equal(trace_a[i], trace_b[i])
                                     or not torch.equal(trace_b[i], captured_traces[i])],
                         state_diff=state_summary(buffered,captured,len(prompt)+step+1))
                del graph, compact, buffered, captured, a, b, c, trace_a, trace_b, captured_traces
                traces.clear()
                gc.collect()
                torch.cuda.empty_cache()
        for handle in handles:
            handle.remove()
        emit(phase="complete", scope="diagnostic_only", verdict="INCONCLUSIVE",
             seconds=time.monotonic()-start)


if __name__ == "__main__":
    main()
