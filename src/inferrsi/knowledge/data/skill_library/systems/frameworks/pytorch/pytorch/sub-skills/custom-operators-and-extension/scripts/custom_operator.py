#!/usr/bin/env python3
"""Tiny fresh-output operator, fake and gradient registration diagnostic.

Adapted from torch.library docs; --check-registration adds public opcheck.
"""
import argparse
import json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-registration", action="store_true")
    args = parser.parse_args()
    try:
        import torch
    except (ImportError, OSError):
        print("MISSING_PACKAGE: select an installed torch environment.")
        return 2

    @torch.library.custom_op("inferrsi_diagnostic::scale", mutates_args=())
    def scale(x: torch.Tensor, factor: float) -> torch.Tensor:
        return x * factor

    @scale.register_fake
    def fake_scale(x, factor):
        return torch.empty_like(x)

    def setup_context(ctx, inputs, output):
        ctx.factor = inputs[1]

    def backward(ctx, grad):
        return grad * ctx.factor, None

    scale.register_autograd(backward, setup_context=setup_context)
    x = torch.tensor([1., 2.], dtype=torch.double, requires_grad=True)
    torch.testing.assert_close(scale(x, 3.0), x * 3)
    assert torch.autograd.gradcheck(lambda t: scale(t, 3.0), (x,))
    registration = None
    if args.check_registration:
        registration = torch.library.opcheck(scale, (x, 3.0))
    print(json.dumps({"scope": "tiny_cpu_custom_op", "gradcheck": True,
                      "registration": registration, "native_kernel_qualified": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
