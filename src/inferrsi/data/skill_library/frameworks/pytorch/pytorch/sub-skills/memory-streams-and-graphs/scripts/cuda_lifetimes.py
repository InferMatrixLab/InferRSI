#!/usr/bin/env python3
"""Tiny CUDA stream/address diagnostic; absence of CUDA is an explicit block.

Adapted from CUDA semantics and test_record_stream patterns, not a benchmark.
"""
import argparse
import json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("streams", "graph"), default="streams")
    args = parser.parse_args()
    try:
        import torch
    except (ImportError, OSError):
        print("MISSING_PACKAGE: select an installed torch environment.")
        return 2
    if not torch.cuda.is_available() or torch.version.hip is not None:
        print(json.dumps({"status": "BLOCKED_REQUIRED_BACKEND", "required": "NVIDIA CUDA"}))
        return 3
    x = torch.arange(8., device="cuda")
    main_stream = torch.cuda.current_stream()
    worker = torch.cuda.Stream()
    worker.wait_stream(main_stream)
    with torch.cuda.stream(worker):
        x.record_stream(worker)
        y = x.square()
    main_stream.wait_stream(worker)
    y.record_stream(main_stream)
    torch.testing.assert_close(y, x.square())
    if args.mode == "graph":
        static_x = torch.zeros(8, device="cuda")
        worker.wait_stream(main_stream)
        with torch.cuda.stream(worker):
            for _ in range(3):
                static_y = static_x.sin() + 1
        main_stream.wait_stream(worker)
        graph = torch.cuda.CUDAGraph()
        with torch.cuda.graph(graph):
            static_y = static_x.sin() + 1
        for value in (0.5, 1.5):
            static_x.fill_(value)
            graph.replay()
            torch.testing.assert_close(static_y, static_x.sin() + 1)
    torch.cuda.synchronize()
    print(json.dumps({"scope": "tiny_cuda_lifetime", "mode": args.mode,
                      "torch": torch.__version__, "performance_claim": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
