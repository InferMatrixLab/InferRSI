#!/usr/bin/env python3
"""Tiny torchrun all-reduce/DDP check on trusted launcher-assigned ranks.

Adapted from the DDP public recipe; launches no subprocess or public service itself.
"""
import argparse
import json
import os
from datetime import timedelta


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("gloo", "nccl"), default="gloo")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    args = parser.parse_args()
    if args.backend == "nccl" and args.device != "cuda":
        parser.error("NCCL requires --device cuda")
    required_env = ("LOCAL_RANK", "RANK", "WORLD_SIZE", "MASTER_ADDR", "MASTER_PORT")
    if not all(key in os.environ for key in required_env):
        parser.error("Run under torch.distributed.run with trusted rendezvous settings")
    try:
        import torch
        import torch.distributed as dist
    except (ImportError, OSError):
        print("MISSING_PACKAGE: select an installed torch environment.")
        return 2
    if not dist.is_available() or not dist.is_backend_available(args.backend):
        print(json.dumps({"status": "BLOCKED_REQUIRED_BACKEND", "backend": args.backend}))
        return 3
    local_rank = int(os.environ["LOCAL_RANK"])
    if args.device == "cuda":
        if not torch.cuda.is_available() or local_rank >= torch.cuda.device_count():
            print(json.dumps({"status": "BLOCKED_REQUIRED_BACKEND",
                              "required": "assigned CUDA device"}))
            return 3
        torch.cuda.set_device(local_rank)
        device = torch.device("cuda", local_rank)
    else:
        device = torch.device("cpu")
    dist.init_process_group(args.backend, timeout=timedelta(seconds=30))
    try:
        rank, size = dist.get_rank(), dist.get_world_size()
        value = torch.tensor([float(rank + 1)], device=device)
        work = dist.all_reduce(value, async_op=True)
        work.wait()
        torch.testing.assert_close(value, torch.tensor([size * (size + 1) / 2.0], device=device))
        torch.manual_seed(0)
        model = torch.nn.Linear(2, 1).to(device)
        ddp = torch.nn.parallel.DistributedDataParallel(
            model, device_ids=[local_rank] if args.device == "cuda" else None)
        optimizer = torch.optim.SGD(ddp.parameters(), lr=0.01)
        optimizer.zero_grad(set_to_none=True)
        ddp(torch.ones(2, 2, device=device) * (rank + 1)).square().mean().backward()
        optimizer.step()
        for parameter in ddp.parameters():
            average = parameter.detach().clone()
            dist.all_reduce(average)
            torch.testing.assert_close(parameter, average / size)
        if rank == 0:
            print(json.dumps({"scope": "tiny_ddp_rank_contract", "ranks": size,
                              "backend": args.backend, "device": args.device}))
    finally:
        dist.destroy_process_group()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
