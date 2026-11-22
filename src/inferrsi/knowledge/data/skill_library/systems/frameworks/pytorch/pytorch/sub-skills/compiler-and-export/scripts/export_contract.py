#!/usr/bin/env python3
"""Tiny CPU export roundtrip and shape-bound check; optional explicit compiler.

Adapted from export constraints tests. Creates and removes one temporary archive.
"""
import argparse
import json
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=int, default=3)
    parser.add_argument("--compile-backend", choices=("eager", "aot_eager", "inductor"))
    args = parser.parse_args()
    if not 2 <= args.batch <= 8:
        parser.error("--batch must be in [2, 8], the declared export range")
    try:
        import torch
    except (ImportError, OSError):
        print("MISSING_PACKAGE: select an installed torch environment.")
        return 2

    class Model(torch.nn.Module):
        def forward(self, x):
            return x.sin() + 1

    model = Model().eval()
    example = torch.arange(args.batch * 2, dtype=torch.float32).reshape(args.batch, 2)
    ep = torch.export.export(model, (example,),
                             dynamic_shapes={"x": {0: torch.export.Dim("batch", min=2, max=8)}})
    with tempfile.TemporaryDirectory(prefix="torch-export-contract-") as directory:
        archive = Path(directory) / "tiny.pt2"
        torch.export.save(ep, archive)
        loaded = torch.export.load(archive).module()
        for size in (args.batch, 2 if args.batch != 2 else 3):
            x = torch.zeros(size, 2)
            torch.testing.assert_close(loaded(x), model(x))
        try:
            loaded(torch.zeros(9, 2))
        except (RuntimeError, ValueError, AssertionError) as exc:
            if "8" not in str(exc):
                raise  # Preserve an unrelated execution failure.
        else:
            raise AssertionError("Export failed to reject batch outside declared range")
    if args.compile_backend:
        compiled = torch.compile(model, backend=args.compile_backend, fullgraph=True)
        torch.testing.assert_close(compiled(example), model(example))
    print(json.dumps({"scope": "tiny_cpu_export", "roundtrip": True, "bounds_rejection": True,
                      "compile_backend": args.compile_backend,
                      "target_deployment_qualified": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
