#!/usr/bin/env python3
"""Tiny CPU alias, autograd and sparse diagnostic; no files or downloads.

Adapted from pinned autograd/sparse documentation and gradcheck test patterns.
"""
import argparse
import json


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        import torch
    except (ImportError, OSError):
        print("MISSING_PACKAGE: select an installed torch environment.")
        return 2
    base = torch.arange(6.0)
    view = base[::2]
    view.add_(10)
    torch.testing.assert_close(base, torch.tensor([10., 1., 12., 3., 14., 5.]))
    x = torch.tensor([1., 2.], dtype=torch.double, requires_grad=True)
    (grad,) = torch.autograd.grad(x.square().sum(), x)
    torch.testing.assert_close(grad, 2 * x)
    assert torch.autograd.gradcheck(lambda t: t.square(), (x,))
    sparse = torch.sparse_coo_tensor([[1, 1]], [3., 4.], (3,)).coalesce()
    torch.testing.assert_close(sparse.to_dense(), torch.tensor([0., 7., 0.]))
    print(json.dumps({"scope": "tiny_cpu_contract", "alias": True, "gradient": True,
                      "sparse_duplicate_sum": True, "torch": torch.__version__}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
