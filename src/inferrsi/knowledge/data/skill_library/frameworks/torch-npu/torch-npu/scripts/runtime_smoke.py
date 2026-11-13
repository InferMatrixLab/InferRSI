"""Small public-API examples. No execution or imports of torch without --run."""

import argparse
import json
import os
from datetime import timedelta
from pathlib import Path


def run_case(args, torch, torch_npu):
    if args.case == "streams":
        producer = torch.npu.current_stream()
        consumer = torch.npu.Stream()
        x = torch.ones(8, device="npu")
        consumer.wait_stream(producer)
        with torch.npu.stream(consumer):
            y = x * 3
            x.record_stream(consumer)
        producer.wait_stream(consumer)
        torch.npu.synchronize()
        torch.testing.assert_close(y.cpu(), torch.full((8,), 3.0))
    elif args.case == "graph":
        x = torch.ones((2, 2), device="npu")
        warmup = torch.npu.Stream()
        warmup.wait_stream(torch.npu.current_stream())
        with torch.npu.stream(warmup):
            for _ in range(3):
                _ = x + x
        torch.npu.current_stream().wait_stream(warmup)
        graph = torch.npu.NPUGraph()
        with torch.npu.graph(graph):
            y = x + x
        for value in (2.0, 3.0):
            x.fill_(value)
            graph.replay()
            torch.npu.synchronize()
            torch.testing.assert_close(y.cpu(), torch.full((2, 2), value * 2))
    elif args.case == "amp":
        model = torch.nn.Linear(4, 2).npu()
        optimizer = torch.optim.SGD(model.parameters(), lr=0.01)
        scaler = torch.npu.amp.GradScaler()
        if not scaler.is_enabled():
            raise RuntimeError("AMP scaler disabled")
        x = torch.ones((2, 4), device="npu")
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast("npu", dtype=torch.float16):
            loss = model(x).float().square().mean()
        scaler.scale(loss).backward()
        scaler.unscale_(optimizer)
        assert all(torch.isfinite(p.grad).all().item() for p in model.parameters())
        scaler.step(optimizer)
        scaler.update()
        torch.npu.synchronize()
        assert torch.isfinite(loss).item()
    elif args.case == "hccl":
        import torch.distributed as dist

        rank = int(os.environ["RANK"])
        size = int(os.environ["WORLD_SIZE"])
        local_rank = int(os.environ["LOCAL_RANK"])
        if size < 2 or local_rank >= torch.npu.device_count():
            raise ValueError("HCCL requires at least two ranks and valid local devices")
        torch.npu.set_device(local_rank)
        dist.init_process_group("hccl", timeout=timedelta(seconds=60))
        try:
            x = torch.tensor([float(rank + 1)], device=f"npu:{local_rank}")
            work = dist.all_reduce(x, async_op=True)
            work.wait()
            torch.npu.synchronize()
            torch.testing.assert_close(x.cpu(), torch.tensor([float(size * (size + 1) // 2)]))
        finally:
            dist.destroy_process_group()
    else:
        if args.output is None:
            raise ValueError("profile case requires --output pointing to a new directory")
        args.output.mkdir(parents=True, exist_ok=False)
        x = torch.ones((8, 8), device="npu")
        with torch_npu.profiler.profile(
            activities=[
                torch_npu.profiler.ProfilerActivity.CPU,
                torch_npu.profiler.ProfilerActivity.NPU,
            ],
            schedule=torch_npu.profiler.schedule(wait=0, warmup=1, active=2, repeat=1),
            on_trace_ready=torch_npu.profiler.tensorboard_trace_handler(
                str(args.output), worker_name="example-worker"
            ),
            record_shapes=True,
            profile_memory=True,
            with_stack=True,
        ) as profiler:
            for _ in range(3):
                _ = x @ x
                profiler.step()
        torch.npu.synchronize()
        if not any(path.is_file() for path in args.output.rglob("*")):
            raise RuntimeError("no trace artifacts were created")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case", required=True, choices=("streams", "graph", "amp", "hccl", "profile")
    )
    parser.add_argument(
        "--run", action="store_true", help="Explicitly execute the selected NPU case"
    )
    parser.add_argument("--output", type=Path, help="New trace directory for profile case only")
    args = parser.parse_args()
    if not args.run:
        print(
            json.dumps(
                {
                    "case": args.case,
                    "status": "NOT_RUN",
                    "required_backend": "Ascend NPU + CANN; HCCL needs multiple ranks",
                }
            )
        )
        return 0
    try:
        import torch
        import torch_npu
    except (ImportError, OSError, RuntimeError) as error:
        print(
            json.dumps(
                {
                    "case": args.case,
                    "status": "BLOCKED_REQUIRED_BACKEND",
                    "phase": "import",
                    "error_type": type(error).__name__,
                }
            )
        )
        return 2
    try:
        if not torch.npu.is_available():
            print(json.dumps({"case": args.case, "status": "BLOCKED_REQUIRED_BACKEND"}))
            return 2
        run_case(args, torch, torch_npu)
    except Exception as error:
        print(
            json.dumps(
                {"case": args.case, "status": "NATIVE_FAIL", "error_type": type(error).__name__}
            )
        )
        return 1
    print(json.dumps({"case": args.case, "status": "PASS", "scope": "tiny API example only"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
