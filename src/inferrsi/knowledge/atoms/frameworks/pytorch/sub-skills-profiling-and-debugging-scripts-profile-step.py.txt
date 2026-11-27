#!/usr/bin/env python3
"""Finite CPU profiler diagnostic adapted from upstream schedule examples.

Only --trace-file writes a caller-selected file; existing files are not replaced.
"""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace-file", type=Path)
    args = parser.parse_args()
    if args.trace_file and (args.trace_file.exists() or not args.trace_file.parent.is_dir()):
        parser.error("Trace target must be new with an existing parent directory")
    try:
        import torch
    except (ImportError, OSError):
        print("MISSING_PACKAGE: select an installed torch environment.")
        return 2
    x = torch.arange(16.).reshape(4, 4)
    traces = []

    def ready(prof):
        traces.append(len(prof.key_averages()))
        if args.trace_file:
            prof.export_chrome_trace(str(args.trace_file))

    with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU],
                                schedule=torch.profiler.schedule(
                                    wait=1, warmup=1, active=2, repeat=1),
                                on_trace_ready=ready) as prof:
        for _ in range(4):
            with torch.profiler.record_function("tiny_step"):
                y = x.square() + 1
                assert torch.isfinite(y).all()
            prof.step()
    assert len(traces) == 1 and traces[0] > 0
    print(json.dumps({"scope": "tiny_cpu_profile", "trace_cycles": len(traces),
                      "performance_claim": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
