#!/usr/bin/env python3
"""Bounded CPU model/DataLoader update adapted from the upstream module recipe.

Example: python tiny_training.py --steps 2. No downloads or persistent writes.
"""
import argparse
import json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.steps <= 8:
        parser.error("--steps must be in [1, 8] for this bounded diagnostic")
    try:
        import torch
        from torch.utils.data import DataLoader, TensorDataset
    except (ImportError, OSError):
        print("MISSING_PACKAGE: select an installed torch environment.")
        return 2
    torch.manual_seed(0)
    x = torch.arange(16, dtype=torch.float32).reshape(8, 2) / 16
    y = x.sum(dim=1, keepdim=True)
    loader = DataLoader(TensorDataset(x, y), batch_size=4, num_workers=0)
    model = torch.nn.Linear(2, 1)
    before = model.weight.detach().clone()
    optimizer = torch.optim.SGD(model.parameters(), lr=0.05)
    losses = []
    model.train()
    for step in range(args.steps):
        batch_x, batch_y = list(loader)[step % len(loader)]
        optimizer.zero_grad(set_to_none=True)
        loss = torch.nn.functional.mse_loss(model(batch_x), batch_y)
        assert torch.isfinite(loss)
        loss.backward()
        assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters())
        optimizer.step()
        losses.append(loss.item())
    assert not torch.equal(before, model.weight)
    model.eval()
    with torch.no_grad():
        assert torch.isfinite(model(x)).all()
    print(json.dumps({"scope": "tiny_cpu_update", "steps": args.steps, "losses": losses,
                      "weight_changed": True, "convergence_claim": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
